"""
02_load_data.py
Transforms raw downloaded files and loads them into the PostGIS database.
Creates spatial indexes after loading.

AWS equivalent: Glue job 02_transform_load.py
Code change when migrating: change DB_HOST to Aurora endpoint from Secrets Manager.
"""

import os
import pathlib
import psycopg2
import psycopg2.extras
import pandas as pd
import geopandas as gpd
from dotenv import load_dotenv

load_dotenv()

RAW = pathlib.Path(os.getenv("DATA_RAW_DIR", "./data/raw"))

# US territory FIPS codes to exclude (not 50 states)
TERRITORY_FIPS = {"60", "66", "69", "72", "78"}


def get_connection():
    """
    Returns a psycopg2 connection using .env credentials.
    AWS equivalent: credentials are fetched from Secrets Manager via boto3.
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "geodb"),
        user=os.getenv("DB_USER", "gis_admin"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_hospitals(cur):
    """
    Load CMS hospital CSV.
    Filters to facilities with valid lat/lon coordinates.
    Constructs POINT geometry using ST_MakePoint(longitude, latitude).
    Note: ST_MakePoint takes X (longitude) first, then Y (latitude).
    """
    csv_path = RAW / "birthing_friendly_hospitals_geocoded.csv"
    print(f"\nLoading hospitals from {csv_path.name} ...")

    df = pd.read_csv(csv_path, low_memory=False, dtype=str)
    df.columns = df.columns.str.strip()
    print(df.columns.tolist()  )

    # Keep only rows with usable coordinates
    df = df[df["lat"].notna() & df["lon"].notna()].copy()
    df["lat"]  = pd.to_numeric(df["lat"],  errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    print(f"  {len(df)} hospitals with valid coordinates")

    sql = """
        INSERT INTO hospitals
            (facility_name, address, city, state, zip,
              latitude, longitude, geom)
        VALUES
            ( %(name)s, %(addr)s, %(city)s, %(state)s, %(zip)s,
              %(lat)s, %(lon)s,
             ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326))
        ON CONFLICT (facility_name) DO NOTHING
    """

    # Construct records for batch insertion
    records = [
        {
            "name":  row.get("name", ""),
            "addr":  row.get("addr", ""),
            "city":  row.get("city", ""),
            "state": row.get("state", ""),
            "zip":   str(row.get("zip", "")),
            "lat":   float(row["lat"]),
            "lon":   float(row["lon"]),
        }
        for _, row in df.iterrows()
    ]

    psycopg2.extras.execute_batch(cur, sql, records, page_size=500)
    print(f"  Inserted {len(records)} hospital records")


def load_census_tracts(cur):
    """
    Load Census TIGER/Line 2022 tract shapefile.
    Uses geopandas to read the shapefile and reproject to EPSG:4326 (WGS84).
    Serialises geometry to WKT for PostGIS ingestion via ST_GeomFromText.

    The 'geoid' column is an 11-digit FIPS code: state(2) + county(3) + tract(6).
    This is the universal join key across all Census products.
    """
    shp_dir = RAW / "tl_2025_us_ttract"
    shp_file = shp_dir / "tl_2025_us_ttract.shp"
    print(f"\nLoading census tracts from {shp_file.name} ...")

    gdf = gpd.read_file(shp_file)
    print(f"  Read {len(gdf)} features (including territories)")

    print(f"Actual columns found: {gdf.columns.tolist()}") # Add this line!

    # Filter to 50 states only
    gdf = gdf[~gdf["STATEFP"].isin(TERRITORY_FIPS)].copy()
    print(f"  {len(gdf)} tracts after filtering territories")

    # Ensure WGS84 — TIGER files are NAD83 (nearly identical for our purposes)
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    sql = """
        INSERT INTO census_tracts (geoid, state_fips, county_fips, aland, geom)
        VALUES (%(geoid)s, %(sfips)s, %(cfips)s, %(aland)s,
                ST_GeomFromText(%(wkt)s, 4326))
        ON CONFLICT (geoid) DO NOTHING
    """

    records = [
        {
            "geoid": row["GEOID"],
            "sfips": row["STATEFP"],
            "cfips": row["COUNTYFP"],
            "aland": int(row["ALAND"]),
            "wkt":   row["geometry"].wkt,
        }
        for _, row in gdf.iterrows()
    ]

    # Load in batches — 73k records is large enough to batch for progress visibility
    batch_size = 2000
    total = len(records)
    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        psycopg2.extras.execute_batch(cur, sql, batch, page_size=500)
        pct = min(100, int((i + batch_size) / total * 100))
        print(f"  Loading tracts: {pct}%", end="\r")

    print(f"\n  Inserted {total} census tract records")


def load_hpsa(cur):
    """
    Load HRSA HPSA primary care designations.
    This is tabular data — no geometry. The spatial join to census_tracts
    happens at analysis time using the county FIPS code.
    """
    csv_path = RAW / "hpsa_primary_care.csv"
    print(f"\nLoading HPSA data from {csv_path.name} ...")

    df = pd.read_csv(csv_path, low_memory=False, dtype=str)
    df.columns = df.columns.str.strip()

    # Keep only active designations with a score
    df = df[df["HPSA Status"] == "Designated"].copy()
    df["HPSA Score"] = pd.to_numeric(df["HPSA Score"], errors="coerce")
    df = df.dropna(subset=["HPSA Score"])

    # Normalise county FIPS — zero-pad to 5 digits (state 2 + county 3)
    df["County Equivalent Federal FIPS Code"] = (
        df["County Equivalent Federal FIPS Code"]
        .str.strip()
        .str.zfill(5)
    )

    sql = """
        INSERT INTO hpsa_designations
            (hpsa_id, hpsa_name, hpsa_score, hpsa_status,
             designation_type, state_abbr, county_fips, rural_status)
        VALUES
            (%(hid)s, %(hname)s, %(hscore)s, %(hstatus)s,
             %(dtype)s, %(state)s, %(cfips)s, %(rural)s)
        ON CONFLICT (hpsa_id) DO NOTHING
    """

    records = [
        {
            "hid":    row.get("HPSA ID", ""),
            "hname":  row.get("HPSA Name", ""),
            "hscore": int(row["HPSA Score"]),
            "hstatus":row.get("HPSA Status", ""),
            "dtype":  row.get("HPSA Designation Type", ""),
            "state":  row.get("Common State Abbreviation", ""),
            "cfips":  row.get("County Equivalent Federal FIPS Code", ""),
            "rural":  row.get("Rural Status", ""),
        }
        for _, row in df.iterrows()
    ]

    psycopg2.extras.execute_batch(cur, sql, records, page_size=500)
    print(f"  Inserted {len(records)} HPSA records")


def create_spatial_indexes(cur):
    """
    Creates GIST indexes on geometry columns.
    Without these, the nearest-hospital query scans every hospital for
    every tract — O(n*m) comparisons. With GIST indexes, the KNN operator
    (<->) performs an indexed traversal — roughly O(n log m).
    """
    print("\nCreating GIST spatial indexes ...")
    indexes = [
        ("idx_hospitals_geom",     "hospitals",     "geom"),
        ("idx_census_tracts_geom", "census_tracts", "geom"),
    ]
    for idx_name, table, col in indexes:
        cur.execute(f"""
            CREATE INDEX IF NOT EXISTS {idx_name}
            ON {table} USING GIST({col});
        """)
        print(f"  Created index: {idx_name}")


if __name__ == "__main__":
    conn = get_connection()
    cur  = conn.cursor()

    try:
        # Run setup SQL to ensure tables exist
        with open("./setup/02_create_tables.sql") as f:
            cur.execute(f.read())
        conn.commit()

        load_hospitals(cur);     conn.commit()
        load_census_tracts(cur); conn.commit()
        load_hpsa(cur);          conn.commit()
        create_spatial_indexes(cur); conn.commit()

        print("\nLoad complete. Run: python scripts/03_run_analysis.py")

    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()