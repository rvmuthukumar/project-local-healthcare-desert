"""
03_run_analysis.py
Executes the spatial analysis SQL against the PostGIS database.
Prints a summary of results.

AWS equivalent: Glue job 03_export_report.py calls the same SQL
against the Aurora endpoint.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME", "geodb"),
        user=os.getenv("DB_USER", "gis_admin"),
        password=os.getenv("DB_PASSWORD"),
    )


if __name__ == "__main__":
    conn = get_connection()
    cur  = conn.cursor()

    print("\nRunning spatial analysis ...")
    print("Step 1 — computing nearest hospital per tract (may take 5-10 min)...")

    with open("./setup/03_spatial_analysis.sql") as f:
        sql = f.read()

    # Execute the full analysis script
    cur.execute(sql)
    conn.commit()
    print("  Analysis tables created.")

    # Print summary statistics
    print("\nResults summary:")
    print("-" * 60)

    cur.execute("SELECT COUNT(*) FROM maternity_desert_tracts;")
    count = cur.fetchone()[0]
    print(f"  Total maternity desert tracts:   {count:,}")

    cur.execute("""
        SELECT COUNT(DISTINCT state_fips)
        FROM maternity_desert_tracts;
    """)
    states = cur.fetchone()[0]
    print(f"  States with desert tracts:       {states}")

    cur.execute("""
        SELECT SUM(total_population)
        FROM maternity_desert_tracts;
    """)
    pop = cur.fetchone()[0] or 0
    print(f"  Estimated affected population:   {pop:,}")

    cur.execute("""
        SELECT ROUND(AVG(nearest_hospital_miles)::numeric, 1)
        FROM maternity_desert_tracts;
    """)
    avg_miles = cur.fetchone()[0]
    print(f"  Mean distance to birthing hosp:  {avg_miles} miles")

    cur.execute("""
        SELECT ROUND(MAX(nearest_hospital_miles)::numeric, 1)
        FROM maternity_desert_tracts;
    """)
    max_miles = cur.fetchone()[0]
    print(f"  Maximum distance to hosp:        {max_miles} miles")

    print("\nTop 10 most vulnerable tracts:")
    print(f"  {'GEOID':<13} {'State':<7} {'County':<6} "
          f"{'Miles':>7} {'HPSA Score':>11} {'Score':>8}")
    print("  " + "-" * 58)

    cur.execute("""
        SELECT geoid, state_fips, county_fips,
               nearest_hospital_miles, hpsa_score, vulnerability_score
        FROM maternity_desert_tracts
        ORDER BY vulnerability_score DESC
        LIMIT 10;
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:<13} {row[1]:<7} {row[2]:<6} "
              f"{row[3]:>7.1f} {row[4] or 0:>11} {row[5] or 0:>8.2f}")

    cur.execute("""
        SELECT state_fips, COUNT(*) AS desert_tracts
        FROM maternity_desert_tracts
        GROUP BY state_fips
        ORDER BY desert_tracts DESC
        LIMIT 5;
    """)
    print("\nStates with most desert tracts (top 5):")
    for row in cur.fetchall():
        print(f"  State FIPS {row[0]}: {row[1]} tracts")

    cur.close()
    conn.close()
    print("\nAnalysis complete. Run: python scripts/04_export_report.py")