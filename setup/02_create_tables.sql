-- Hospitals: one point per facility (CMS Provider of Services file)
-- changes from original
    -- geom        GEOMETRY(MULTIPOLYGON, 4326)   -- 2025: Polygon (not MultiPolygon)
    -- pct_poverty          NUMERIC(10,4) -- % of Population Below 100% Poverty (from HPSA)

DROP TABLE IF EXISTS hospitals CASCADE;

-- Hospitals: one point per CMS-certified birthing-friendly facility
-- Source: CMS Provider Data Catalog — Birthing Friendly Hospitals Geocoded
-- URL: https://data.cms.gov/provider-data/sites/default/files/resources/
--      e7f75e0803a17e22c4e26acf2183e622_1771884335/
--      Birthing_Friendly_Hospitals_Geocoded.csv
-- Columns in source: name, addr, city, state, zip, lat, lon (7 fields)
-- All facilities in this file meet the CMS Birthing Friendly designation criteria.
CREATE TABLE IF NOT EXISTS hospitals (
    id            SERIAL PRIMARY KEY,
    facility_name TEXT        NOT NULL,
    address       TEXT,
    city          TEXT,
    state         CHAR(2),
    zip           TEXT,
    latitude      NUMERIC(10, 6),
    longitude     NUMERIC(10, 6),
    geom          GEOMETRY(POINT, 4326),
    UNIQUE (facility_name, zip)         -- natural deduplication key
);

-- Census tracts: one multipolygon per tract (Census TIGER/Line 2022)
DROP TABLE IF EXISTS census_tracts CASCADE;

-- Census tracts: one polygon per tract
-- Source: Census TIGER/Line 2025 — per-state files
-- URL pattern: https://www2.census.gov/geo/tiger/TIGER2025/TRACT/tl_2025_{fips}_tract.zip
-- Schema confirmed from tl_2025_31_tract.shp (Nebraska sample):
--   STATEFP, COUNTYFP, TRACTCE, GEOID (11-digit), GEOIDFQ,
--   NAME, NAMELSAD, MTFCC, FUNCSTAT, ALAND, AWATER, INTPTLAT, INTPTLON
-- CRS: EPSG:4269 (NAD83) — reprojected to EPSG:4326 on load
-- Geometry: Polygon (2025 vintage uses Polygon, not MultiPolygon)
CREATE TABLE IF NOT EXISTS census_tracts (
    id          SERIAL PRIMARY KEY,
    geoid       TEXT UNIQUE    NOT NULL,  -- 11-digit: state(2)+county(3)+tract(6)
    state_fips  CHAR(2),
    county_fips CHAR(3),
    tract_ce    CHAR(6),                  -- raw tract code
    aland       BIGINT,                   -- land area in square metres
    awater      BIGINT,                   -- water area in square metres
    geom        GEOMETRY(MULTIPOLYGON, 4326)   -- 2025: Polygon (not MultiPolygon)
);

-- HPSA designations: shortage area polygons (HRSA BHW)
-- Note: HPSA areas are county-level or sub-county — loaded as county polygons
-- joined by FIPS code to census_tracts at analysis time
DROP TABLE IF EXISTS hpsa_designations CASCADE;

-- HPSA designations: tabular, joined to census_tracts by county FIPS at query time
-- Source: HRSA BHW — https://data.hrsa.gov/DataDownload/DD_Files/BCD_HPSA_FCT_DET_PC.csv
-- Key join field: "State and County Federal Information Processing Standard Code"
--   (5-digit FIPS, already zero-padded — no LPAD needed)
CREATE TABLE IF NOT EXISTS hpsa_designations (
    id                   SERIAL PRIMARY KEY,
    hpsa_id              TEXT UNIQUE,
    hpsa_name            TEXT,
    hpsa_score           INTEGER,    -- 0-25, higher = more severe shortage
    hpsa_status          TEXT,       -- Designated / Withdrawn
    designation_type     TEXT,       -- Geographic / Population / Facility
    state_abbr           CHAR(2),
    county_fips          TEXT,       -- 5-digit state+county FIPS (already padded)
    rural_status         TEXT,       -- Rural / Non-Rural / Partially Rural
    metropolitan_ind     TEXT,       -- Metropolitan / Non-Metropolitan
    underserved_pop      INTEGER,    -- HPSA Estimated Underserved Population
    pct_poverty          NUMERIC(10,4) -- % of Population Below 100% Poverty (from HPSA)
);



DROP TABLE IF EXISTS acs_demographics CASCADE;

-- ACS demographics: tabular, joined to census_tracts on geoid
CREATE TABLE IF NOT EXISTS acs_demographics (
    geoid             TEXT PRIMARY KEY,
    total_population  INTEGER,
    pct_below_poverty NUMERIC(5, 2),
    pct_age_65_plus   NUMERIC(5, 2),
    pct_uninsured     NUMERIC(5, 2)
);