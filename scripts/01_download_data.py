
"""
01_download_data.py
Downloads all source datasets to data/raw/.
Re-running is safe — existing files are skipped.

Data sources:
  1. HRSA HPSA Primary Care CSV          — single file, stable URL
  2. CMS Birthing Friendly Hospitals Geocoded (name, addr, lat, lon)
  3. Census TIGER/Line 2025 tract files  — one ZIP per state (51 files)

AWS equivalent: Glue job 01_ingest_raw.py uploads each file to S3 raw zone.
Code change when migrating: add boto3.upload_file() after each download.

"""


# file and system management
import os # This is the "Swiss Army Knife" for interacting with your operating system. You’ll likely use it to check if directories exist or to handle environment variables.
import pathlib # A modern, more readable alternative to os.path. It treats file paths as objects rather than just strings, which makes it much easier to handle paths across different operating systems (Windows vs. Linux).
# data downloading and extraction
import requests # This is the standard library for making HTTP calls. In your context, it’s almost certainly used to download files (like ZIP archives or CSVs) from a remote URL or API.
import zipfile # Since datasets are often compressed to save space, this library allows your Python script to unzip those downloads automatically once they hit your local drive.
# Security and environment management
from dotenv import load_dotenv # This is a best practice for security. Instead of hardcoding your database passwords or API keys directly in the script, you put them in a hidden .env file. load_dotenv pulls those secrets into your script's memory so they stay off of GitHub or public view.
# Progress tracking - through visual feed back in the terminal
from tqdm import tqdm # This provides those satisfying progress bars in your terminal. When downloading a 2GB healthcare dataset, tqdm tells you exactly how much time is left so you aren't staring at a blank screen.


load_dotenv() # This line loads the environment variables from a .env file into your script's environment. This is crucial for keeping sensitive information like API keys or database credentials out of your codebase and version control. By using load_dotenv(), you can safely store these secrets in a .env file that is not committed to GitHub, and your script can access them via os.getenv() without exposing them in the code.
RAW = pathlib.Path(os.getenv("DATA_RAW_DIR", "./data/raw")) # This line defines a constant RAW that represents the directory where raw data files will be stored. It uses os.getenv() to check if an environment variable named DATA_RAW_DIR is set; if it is, RAW will be set to that value. If not, it defaults to "./data/raw". This allows for flexibility in where the data is stored without hardcoding the path in the script. The pathlib.Path() function converts this string into a Path object, which provides convenient methods for file system operations.
RAW.mkdir(parents=True, exist_ok=True) # This line ensures that the directory specified by RAW exists. If it doesn't exist, it will be created along with any necessary parent directories (thanks to parents=True). The exist_ok=True parameter means that if the directory already exists, no error will be raised, making it safe to run this script multiple times without worrying about directory creation issues.


# ── 50 states + DC FIPS codes (no territories) ────────────────────
# Gaps in sequence: 03,07,14,43,52 are unassigned; territories 60,66,69,72,78
STATE_FIPS = [
    "01","02","04","05","06","08","09","10","11","12","13",
    "15","16","17","18","19","20","21","22","23","24","25",
    "26","27","28","29","30","31","32","33","34","35","36",
    "37","38","39","40","41","42","44","45","46","47","48",
    "49","50","51","53","54","55","56",
]  # 51 entries: 50 states + DC (11)

# ── Simple datasets (single-file downloads) ────────────────────────
SIMPLE_SOURCES = [
    {
        "name": "hpsa_primary_care.csv",
        "url":  "https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv",
        "description": "HRSA Health Professional Shortage Areas — Primary Care",
    },
    {
        # CMS Birthing Friendly Hospitals Geocoded
        # Published by: Centers for Medicare & Medicaid Services (CMS)
        # Verified live as of May 2026. Contains only CMS-certified
        # birthing-friendly hospitals with pre-computed lat/lon.
        # Columns: name, addr, city, state, zip, lat, lon (7 fields)
        # Note: HIFLD Open Data (the original planned source for all US hospitals)
        # was permanently shut down by DHS on August 26, 2025.
        "name": "cms_birthing_hospitals.csv",
        "url":  (
            # "https://data.cms.gov/provider-data/sites/default/files/resources/"
            #"e7f75e0803a17e22c4e26acf2183e622_1778277932/"
            "https://data.cms.gov/provider-data/sites/default/files/resources/"
            "e7f75e0803a17e22c4e26acf2183e622_1771884335/"
            "Birthing_Friendly_Hospitals_Geocoded.csv"
        ),
        "description": "CMS Birthing Friendly Hospitals Geocoded (name, addr, lat, lon)",
    },
]


def download_file(name: str, url: str, description: str,
                  dest_dir: pathlib.Path = RAW) -> pathlib.Path:
    dest = dest_dir / name
    if dest.exists():
        print(f"  [skip] {name} already exists")
        return dest

    print(f"  [download] {description}")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    total_bytes = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(
        total=total_bytes, unit="B", unit_scale=True,
        unit_divisor=1024, leave=False, desc=name[:40]
    ) as bar:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            bar.update(len(chunk))

    return dest


def extract_zip(zip_path: pathlib.Path, extract_dir: pathlib.Path) -> pathlib.Path:
    if extract_dir.exists() and any(extract_dir.glob("*.shp")):
        print(f"  [skip] {extract_dir.name}/ already extracted")
        return extract_dir

    extract_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [extract] {zip_path.name} → {extract_dir.name}/")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)
    return extract_dir


def download_tiger_tracts() -> None:
    """
    Downloads 51 per-state TIGER/Line 2025 tract shapefiles.
    URL pattern: https://www2.census.gov/geo/tiger/TIGER2025/TRACT/
                 tl_2025_{fips}_tract.zip

    Each ZIP extracts to: data/raw/tracts/tl_2025_{fips}_tract/
    The load script concatenates all 51 GeoDataFrames into one.

    Why per-state files?
    Census no longer publishes a single national tract shapefile in TIGER2025.
    Each state's file is ~1-15 MB; total download is ~200-300 MB across all states.
    """
    tracts_dir = RAW / "tracts"
    tracts_dir.mkdir(exist_ok=True)

    base_url = "https://www2.census.gov/geo/tiger/TIGER2025/TRACT"
    total = len(STATE_FIPS)

    print(f"\nDownloading {total} state tract files to {tracts_dir}/")
    for i, fips in enumerate(STATE_FIPS, 1):
        name    = f"tl_2025_{fips}_tract.zip"
        url     = f"{base_url}/{name}"
        desc    = f"TIGER 2025 Census Tracts — state FIPS {fips} ({i}/{total})"
        zip_path     = download_file(name, url, desc, dest_dir=tracts_dir)
        extract_dir  = tracts_dir / f"tl_2025_{fips}_tract"
        extract_zip(zip_path, extract_dir)

    print(f"  All {total} state tract files downloaded and extracted.")


if __name__ == "__main__":
    print(f"\nDownloading datasets to {RAW.resolve()}\n")

    print("── Simple datasets ──────────────────────────────────────")
    for source in SIMPLE_SOURCES:
        download_file(**source)

    print("\n── TIGER 2025 Census Tract files ────────────────────────")
    download_tiger_tracts()

    print("\nAll source files staged to data/raw/")
    print("Run:  python scripts/02_load_data.py")