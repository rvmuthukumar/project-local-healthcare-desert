-- Hospitals: one point per facility (CMS Provider of Services file)
CREATE TABLE IF NOT EXISTS hospitals (
    id            SERIAL PRIMARY KEY,
    cms_ccn       TEXT UNIQUE,
    facility_name TEXT        NOT NULL,
    address       TEXT,
    city          TEXT,
    state         CHAR(2),
    zip           TEXT,
    hospital_type TEXT,
    latitude      NUMERIC(10, 6),
    longitude     NUMERIC(10, 6),
    geom          GEOMETRY(POINT, 4326)
);

-- Census tracts: one multipolygon per tract (Census TIGER/Line 2022)
CREATE TABLE IF NOT EXISTS census_tracts (
    id          SERIAL PRIMARY KEY,
    geoid       TEXT UNIQUE    NOT NULL,  -- 11-digit FIPS: state(2)+county(3)+tract(6)
    state_fips  CHAR(2),
    county_fips CHAR(3),
    aland       BIGINT,                   -- land area in square metres
    geom        GEOMETRY(MULTIPOLYGON, 4326)
);

-- HPSA designations: shortage area polygons (HRSA BHW)
-- Note: HPSA areas are county-level or sub-county — loaded as county polygons
-- joined by FIPS code to census_tracts at analysis time
CREATE TABLE IF NOT EXISTS hpsa_designations (
    id               SERIAL PRIMARY KEY,
    hpsa_id          TEXT UNIQUE,
    hpsa_name        TEXT,
    hpsa_score       INTEGER,             -- 0-25, higher = more severe shortage
    hpsa_status      TEXT,               -- Designated / Proposed Withdrawal
    designation_type TEXT,               -- Geographic / Population / Facility
    state_abbr       CHAR(2),
    county_fips      TEXT,
    rural_status     TEXT
);

-- ACS demographics: tabular, joined to census_tracts on geoid
CREATE TABLE IF NOT EXISTS acs_demographics (
    geoid            TEXT PRIMARY KEY,
    total_population INTEGER,
    pct_below_poverty NUMERIC(5, 2),
    pct_age_65_plus  NUMERIC(5, 2),
    pct_uninsured    NUMERIC(5, 2)
);