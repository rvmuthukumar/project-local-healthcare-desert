
# Data Files Download Requirements

## Pre-Requisities

### Conventions Used

- File Download Metadata
    - File_download_site: 
        - URL Value
    - File_download_method:
        - API - needs Enpoint URL
        - SFTP - needs Host/IP and Port
        - Direct URL
    - File_download_format:
        - csv
        - txt
        - zip
    - File_download_type: 
        - Single
        - Multiple
    - File_download_prefix: 
        - NA or Not applicable as it may be single
        - "XXXXX" - prefix for muliple 
    
    - Filename_Saved: cms_birthing_friendly_hospitals_geocoded.csv
    - File_description:

### Data files we need

1. Hospitals

    - Must have all hospital locations geocoded 
        - Longitude and Latidude must be a column
    - File_download_site: "https://data.cms.gov/provider-data/sites/default/files/resources/e7f75e0803a17e22c4e26acf2183e622_1771884335/Birthing_Friendly_Hospitals_Geocoded.csv"
    - File_download_method:url
    - File_download_format:csv
    - File_download_type: Single
    - File_download_prefix: NA
    - Filename_Saved: "cms_birthing_friendly_hospitals_geocoded.csv"
    - File_description: "List of Birthing friendly hospitals with geocoding"


2. Censor Tracts
    - It is standard tracts
    - File_download_site: "https://www2.census.gov/geo/tiger/TIGER2025/TRACT/"
    - File_download_method:url
    - File_download_format:zip
    - File_download_type: Multiple
    - File_download_prefix: "https://www2.census.gov/geo/tiger/TIGER2025/TRACT/tl_2025_{fips}_tract.zip"
    - Filename_Saved: "tl_2025_{fips}_tract.zip"
    - File_description: "Shapefiles with boundaries of all the geographical area published"

3. hpsa_primary_care
    - Has Fed identified designated healthcare shortage areas with severity code"
    - refer site "https://data.hrsa.gov/data/download?hmpgtitle=hmpg-hrsa-data"
    - File_download_site: "https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv"
    - File_download_method:url
    - File_download_format:csv
    - File_download_type: Single
    - File_download_prefix: NA
    - Filename_Saved: "hpsa_primary_care.csv"
    - File_description: "HRSA Health Professional Shortage Areas — Primary Care"
    

## Download Detail Requirements

### Load Details From Files List
    - first load files from a list with Key value pair metadata for each file.
    
### Connect To URL
    - keep this modular to cheeck if the url exists 
    - if it exists then provide the valid connection object for further actions

### Download File

    #### download file from URL
        - before downloading check and if the file is there then skipcan 
        - use the connection object, and download and save file to data/raw folder
        

### Unzip 

## Main

### Connect

### Download Files
    - If single & url based use download_from_url(), then unzip if format is zip 
    - else
        - if url type
        - find list of multiple file and for each
            - download_from_url()
            - unzip if format is zip


