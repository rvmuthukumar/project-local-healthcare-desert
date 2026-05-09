"""
01_download_data.py
Downloads all four public datasets to data/raw/.
Re-running this script is safe — existing files are skipped.

AWS equivalent: Glue job 01_ingest_raw.py uploads files to S3 raw zone.
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


SOURCES = [
    {
        "name": "hpsa_primary_care.csv",
        "url": (
            "https://data.hrsa.gov/DataDownload/DD_Files/"
            "BCD_HPSA_FCT_DET_PC.csv"
        ),
        "description": "HRSA Health Professional Shortage Areas — Primary Care",
    },
    {
        "name": "cms_hospitals.csv",
        "url": (
          #  "https://data.cms.gov/provider-data/sites/default/files/resources/"
          #  "092a54b2-35ac-4b06-a72e-6f3e90e1a194/"
          #  "Hospital_General_Information.csv"
          # https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0/download?format=csv
          "https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1770163599/Hospital_General_Information.csv"
        ),
        "description": "CMS Hospital General Information (name, address, lat/lon)",
    },
    {
        "name": "tl_2025_us_ttract.zip",
        "url": (
           # "https://www2.census.gov/geo/tiger/TIGER2022/TRACT/"
            #"tl_2022_us_tract.zip"
            "https://www2.census.gov/geo/tiger/TIGER2025/TTRACT/"
            "tl_2025_us_ttract.zip"

        ),
        "description": "Census TIGER/Line 2025 — US Census Total Tract Boundaries (~500 MB)",
    },
]


def download_file(name: str, url: str, description: str) -> pathlib.Path:
    dest = RAW / name
    if dest.exists():
        print(f"  [skip] {name} already exists")
        return dest

    print(f"  [download] {description}")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status() # This line checks if the HTTP request was successful. If the server returns an error status code (like 404 or 500), raise_for_status() will throw an exception, which helps you catch issues with the download immediately instead of silently failing or saving an error page as your dataset.

    total_bytes = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(
        total=total_bytes, unit="B", unit_scale=True,
        unit_divisor=1024, leave=False, desc=name[:40]
    ) as bar:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            bar.update(len(chunk))

    return dest


def extract_zip(zip_path: pathlib.Path) -> pathlib.Path:
    extract_dir = zip_path.parent / zip_path.stem
    if extract_dir.exists():
        print(f"  [skip] {zip_path.stem}/ already extracted")
        return extract_dir

    print(f"  [extract] {zip_path.name} → {extract_dir.name}/")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)
    return extract_dir


if __name__ == "__main__":
    print(f"\nDownloading datasets to {RAW.resolve()}\n")
    for source in SOURCES:
        print(source["description"])
        dest = download_file(**source)
        if dest.suffix == ".zip":
            extract_zip(dest)

    print("\nAll source files staged to data/raw/")
    print("Run:  python scripts/02_load_data.py")