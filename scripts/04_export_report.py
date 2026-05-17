"""
04_export_report.py
Reads the analysis results from PostGIS and writes three output files:
  - maternity_desert_tracts.geojson  (open in geojson.io or QGIS)
  - maternity_summary.csv             (tabular, Excel-friendly)
  - maternity_desert_map.png          (static choropleth map)

AWS equivalent: Glue job writes outputs to S3 output zone bucket.
Code change when migrating: replace open(path, "w") with boto3.put_object().
"""

import os
import pathlib
import psycopg2
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

OUT = pathlib.Path(os.getenv("DATA_OUTPUT_DIR", "./data/output"))
OUT.mkdir(parents=True, exist_ok=True)

DB_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 5432)}"
    f"/{os.getenv('DB_NAME', 'geodb')}"
)


def export_geojson(engine):
    print("\nExporting GeoJSON ...")
    gdf = gpd.read_postgis(
        """
        SELECT
            geoid, state_fips, county_fips,
            nearest_birthing_hospital, nearest_hospital_miles,
            hpsa_score, hpsa_designation_type, rural_status,
            total_population, pct_poverty, pct_uninsured,
            vulnerability_score,
            geom
        FROM maternity_desert_tracts
        ORDER BY vulnerability_score DESC
        """,
        engine,
        geom_col="geom",
    )

    out_path = OUT / "maternity_desert_tracts.geojson"
    gdf.to_file(out_path, driver="GeoJSON")
    print(f"  {len(gdf)} features → {out_path}")
    return gdf


def export_csv(gdf):
    print("\nExporting CSV summary ...")
    df = gdf.drop(columns=["geom"])
    out_path = OUT / "maternity_summary.csv"
    df.to_csv(out_path, index=False)
    print(f"  {len(df)} rows → {out_path}")


def export_map(gdf):
    print("\nGenerating choropleth map ...")

    fig, ax = plt.subplots(1, 1, figsize=(20, 12))
    fig.patch.set_facecolor("#f8f8f0")
    ax.set_facecolor("#d4e8f0")

    # Plot desert tracts coloured by vulnerability score
    gdf.plot(
        column="vulnerability_score",
        cmap="YlOrRd",
        linewidth=0.1,
        edgecolor="0.5",
        legend=True,
        legend_kwds={
            "label":       "Vulnerability score",
            "orientation": "horizontal",
            "shrink":      0.5,
            "pad":         0.02,
        },
        ax=ax,
        missing_kwds={"color": "lightgrey", "label": "No score"},
    )

    ax.set_title(
        "US Maternity Care Access Deserts\n"
        "Census tracts in primary care shortage areas "
        "more than 30 miles from the nearest CMS-certified birthing-friendly hospital",
        fontsize=16,
        pad=20,
    )
    ax.set_xlabel("Longitude", fontsize=10)
    ax.set_ylabel("Latitude", fontsize=10)

    # Annotation
    tract_count = len(gdf)
    pop = gdf["total_population"].sum()
    ax.annotate(
        f"{tract_count:,} maternity desert tracts identified\n"
        f"Estimated {pop:,.0f} residents affected",
        xy=(0.02, 0.05),
        xycoords="axes fraction",
        fontsize=11,
        bbox=dict(boxstyle="round,pad=0.4", fc="white", alpha=0.8),
    )

    # Data sources footnote
    ax.annotate(
        "Sources: HRSA HPSA designations · CMS Birthing Friendly Hospitals Geocoded · "
        "US Census Bureau TIGER/Line 2025 · ACS 5-year estimates",
        xy=(0.5, -0.04),
        xycoords="axes fraction",
        ha="center",
        fontsize=8,
        color="grey",
    )

    plt.tight_layout()
    out_path = OUT / "maternity_desert_map.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"  Map saved → {out_path}")


if __name__ == "__main__":
    from sqlalchemy import create_engine
    engine = create_engine(DB_URL)

    gdf = export_geojson(engine)
    export_csv(gdf)
    export_map(gdf)

    print(f"\nAll outputs written to {OUT.resolve()}")
    print("\nNext steps:")
    print("  Open maternity_desert_tracts.geojson at https://geojson.io")
    print("  Open maternity_summary.csv in Excel or any spreadsheet application")
    print("  View maternity_desert_map.png for the static choropleth")