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
    Load CMS Birthing Friendly Hospitals Geocoded CSV.
    Source: CMS Provider Data Catalog (verified live May 2026)
    URL:    https://data.cms.gov/provider-data/sites/default/files/resources/
            e7f75e0803a17e22c4e26acf2183e622_1771884335/
            Birthing_Friendly_Hospitals_Geocoded.csv

    Schema (7 columns): name, addr, city, state, zip, lat, lon
    All rows are CMS-certified birthing-friendly hospitals — no status filter needed.
    Geometry: ST_MakePoint(lon, lat) — note X (longitude) before Y (latitude).

    Note on HIFLD: The HIFLD Open Data portal, which hosted the most complete
    geocoded US hospital dataset, was permanently shut down by DHS on Aug 26, 2025.
    The CMS Birthing Friendly file is the verified, stable federal alternative.
    """
    csv_path = RAW / "cms_birthing_hospitals.csv"
    print(f"\nLoading CMS birthing hospitals from {csv_path.name} ...")

    df = pd.read_csv(csv_path, low_memory=False, dtype=str)
    df.columns = df.columns.str.strip()

    # Validate coordinates
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    # Sanity-check: coordinates must be within US geographic bounds
    df = df[
        df["lon"].between(-180, -60) &
        df["lat"].between(17, 72)
    ].copy()

    print(f"  {len(df)} birthing hospitals with valid coordinates")

    sql = """
        INSERT INTO hospitals
            (facility_name, address, city, state, zip,
             latitude, longitude, geom)
        VALUES
            (%(name)s, %(addr)s, %(city)s, %(state)s, %(zip)s,
             %(lat)s, %(lon)s,
             ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326))
        ON CONFLICT (facility_name, zip) DO NOTHING
    """

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
    Load Census TIGER/Line 2025 tract shapefiles — one per state.
    Source: https://www2.census.gov/geo/tiger/TIGER2025/TRACT/
            tl_2025_{fips}_tract.zip  (51 files: 50 states + DC)

    Schema confirmed from tl_2025_31_tract.shp (Nebraska):
      STATEFP, COUNTYFP, TRACTCE, GEOID (11-digit), GEOIDFQ,
      NAME, NAMELSAD, MTFCC, FUNCSTAT, ALAND, AWATER,
      INTPTLAT, INTPTLON, geometry (Polygon)

    CRS: EPSG:4269 (NAD83) — reprojected to EPSG:4326 on load.
    Geometry type: Polygon (2025 vintage — not MultiPolygon).
    """
    tracts_dir = RAW / "tracts"
    state_dirs = sorted(tracts_dir.glob("tl_2025_*_tract"))

    if not state_dirs:
        raise FileNotFoundError(
            f"No tract directories found under {tracts_dir}. "
            "Run 01_download_data.py first."
        )

    print(f"\nLoading census tracts from {len(state_dirs)} state files ...")

    sql = """
        INSERT INTO census_tracts
            (geoid, state_fips, county_fips, tract_ce, aland, awater, geom)
        VALUES
            (%(geoid)s, %(sfips)s, %(cfips)s, %(tce)s,
             %(aland)s, %(awater)s,
             ST_GeomFromText(%(wkt)s, 4326))
        ON CONFLICT (geoid) DO NOTHING
    """

    total_inserted = 0

    for state_dir in state_dirs:
        shp_files = list(state_dir.glob("*.shp"))
        if not shp_files:
            print(f"  [warn] No .shp in {state_dir.name} — skipping")
            continue

        shp_file = shp_files[0]
        gdf = gpd.read_file(shp_file)

        # Reproject NAD83 (EPSG:4269) → WGS84 (EPSG:4326)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        records = [
            {
                "geoid":  row["GEOID"],
                "sfips":  row["STATEFP"],
                "cfips":  row["COUNTYFP"],
                "tce":    row["TRACTCE"],
                "aland":  int(row["ALAND"]),
                "awater": int(row["AWATER"]),
                "wkt":    row["geometry"].wkt,
            }
            for _, row in gdf.iterrows()
            if row["geometry"] is not None
        ]
       # print(sql, records[0])  # Debug: print first record and SQL template
        psycopg2.extras.execute_batch(cur, sql, records, page_size=500)
        cur.connection.commit()
        total_inserted += len(records)
        fips = state_dir.name.split("_")[2]
        print(f"  [loaded] FIPS {fips}: {len(records):>5} tracts  "
              f"(running total: {total_inserted:,})", end="\r")

    print(f"\n  Inserted {total_inserted:,} census tract records total")


def load_hpsa(cur):
    """
    Load HRSA HPSA primary care designations.
    Source: https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv

    This is tabular data — no geometry. The spatial join to census_tracts
    happens at analysis time using the county FIPS code.

    Key join field: 'State and County Federal Information Processing Standard Code'
    This is a 5-digit state+county FIPS code, already zero-padded in the source.
    No LPAD or padding transformation is required.

    Filter: HPSA Status == 'Designated'  (excludes Withdrawn records)
    """
    csv_path = RAW / "hpsa_primary_care.csv"
    print(f"\nLoading HPSA data from {csv_path.name} ...")

    df = pd.read_csv(csv_path, low_memory=False, dtype=str)
    df.columns = df.columns.str.strip()

    # Keep only active designated areas
    df = df[df["HPSA Status"] == "Designated"].copy()
    df["HPSA Score"] = pd.to_numeric(df["HPSA Score"], errors="coerce")
    df = df.dropna(subset=["HPSA Score"])

    print(f"  {len(df)} Designated HPSA records")

    # The 5-digit FIPS join field (already padded — no transformation needed)
    fips_col = "State and County Federal Information Processing Standard Code"

    sql = """
        INSERT INTO hpsa_designations
            (hpsa_id, hpsa_name, hpsa_score, hpsa_status,
             designation_type, state_abbr, county_fips,
             rural_status, metropolitan_ind,
             underserved_pop, pct_poverty)
        VALUES
            (%(hid)s, %(hname)s, %(hscore)s, %(hstatus)s,
             %(dtype)s, %(state)s, %(cfips)s,
             %(rural)s, %(metro)s,
             %(underserved)s, %(poverty)s)
        ON CONFLICT (hpsa_id) DO NOTHING
    """

    def safe_int(v):
        try:
            return int(float(v)) if v and str(v).strip() not in ("", "nan") else None
        except (ValueError, TypeError):
            return None

    def safe_float(v):
        try:
            return float(v) if v and str(v).strip() not in ("", "nan") else None
        except (ValueError, TypeError):
            return None

    records = [
        {
            "hid":        str(row.get("HPSA ID", "")),
            "hname":      row.get("HPSA Name", ""),
            "hscore":     int(row["HPSA Score"]),
            "hstatus":    row.get("HPSA Status", ""),
            "dtype":      row.get("Designation Type", ""),
            "state":      row.get("Common State Abbreviation", ""),
            "cfips":      str(row.get(fips_col, "")).strip().zfill(5),
            "rural":      row.get("Rural Status", ""),
            "metro":      row.get("Metropolitan Indicator", ""),
            "underserved":safe_int(row.get("HPSA Estimated Underserved Population")),
            "poverty":    safe_float(row.get("% of Population Below 100% Poverty")),
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