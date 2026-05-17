-- Step 1: Compute nearest birthing-friendly hospital distance per census tract.
-- Uses the KNN (<->) operator with CROSS JOIN LATERAL to efficiently
-- find the closest hospital using the GIST index, then computes
-- accurate mileage using ST_Distance on projected (EPSG:26986) geometry.
--
-- Why EPSG:26986?
-- ST_Distance on EPSG:4326 (lat/lon) returns degrees, not metres.
-- EPSG:26986 (NAD83 / Massachusetts Meters) is a metre-based projection
-- covering the continental US. One metre = 0.000621371 miles.

DROP TABLE IF EXISTS nearest_hospital_distance;

CREATE TABLE nearest_hospital_distance AS
SELECT
    ct.geoid,
    ct.state_fips,
    ct.county_fips,
    ct.geom,
    nearest.facility_name                        AS nearest_hospital,
    ROUND(
        (ST_Distance(
            ST_Transform(ST_Centroid(ct.geom), 26986),
            ST_Transform(nearest.geom,         26986)
        ) / 1609.344)::NUMERIC,
        2
    )                                            AS nearest_hospital_miles
FROM census_tracts ct
CROSS JOIN LATERAL (
    SELECT facility_name, geom
    FROM hospitals
    ORDER BY ST_Centroid(ct.geom) <-> geom
    LIMIT 1
) nearest;

-- Add primary key and index for the join step below
ALTER TABLE nearest_hospital_distance ADD PRIMARY KEY (geoid);

-- Step 2: Identify maternity care desert tracts.
-- Criteria: HPSA-designated primary care shortage area
--           AND >30 miles from nearest CMS birthing-friendly hospital.
--
-- HPSA join: county_fips in hpsa_designations is stored as a 5-digit string
-- (state 2 + county 3) already zero-padded by the load script.
-- Tract table stores state_fips (2) and county_fips (3) separately.
-- Concatenating them gives the same 5-digit key for a direct equality join.
DROP TABLE IF EXISTS maternity_desert_tracts;

CREATE TABLE maternity_desert_tracts AS
SELECT
    nhd.geoid,
    nhd.state_fips,
    nhd.county_fips,
    nhd.nearest_hospital                         AS nearest_birthing_hospital,
    nhd.nearest_hospital_miles,
    nhd.geom,

    -- HPSA attributes (county-level shortage designation)
    MAX(h.hpsa_score)                            AS hpsa_score,
    MAX(h.hpsa_name)                             AS hpsa_name,
    MAX(h.designation_type)                      AS hpsa_designation_type,
    MAX(h.rural_status)                          AS rural_status,

    -- Demographics (from ACS — NULL if ACS not loaded)
    COALESCE(acs.total_population,    0)         AS total_population,
    COALESCE(acs.pct_below_poverty,   0.0)       AS pct_poverty,
    COALESCE(acs.pct_uninsured,       0.0)       AS pct_uninsured,

    -- Maternity-focused vulnerability score (0-100)
    -- Weights: distance 50%, poverty 30%, uninsured 20%
    -- Rationale: distance is the primary barrier; poverty and lack of insurance
    -- prevent mothers from overcoming distance barriers through transport or cost.
    ROUND(
        (nhd.nearest_hospital_miles / 100.0 * 50.0)
      + (COALESCE(acs.pct_below_poverty, 0.0) * 0.30)
      + (COALESCE(acs.pct_uninsured,     0.0) * 0.20)
    , 2)                                         AS vulnerability_score

FROM nearest_hospital_distance nhd

-- Join to HPSA designations on 5-digit county FIPS
-- Both sides are already 5-digit zero-padded strings — no LPAD needed
JOIN hpsa_designations h
    ON  nhd.state_fips || nhd.county_fips = h.county_fips
    AND h.hpsa_status = 'Designated'

-- Outer join to ACS demographics (NULL-safe via COALESCE above)
LEFT JOIN acs_demographics acs
    ON acs.geoid = nhd.geoid

WHERE nhd.nearest_hospital_miles > 30

GROUP BY
    nhd.geoid, nhd.state_fips, nhd.county_fips,
    nhd.nearest_hospital, nhd.nearest_hospital_miles, nhd.geom,
    acs.total_population, acs.pct_below_poverty, acs.pct_uninsured

ORDER BY vulnerability_score DESC;

-- Add spatial index on output table for export queries
CREATE INDEX idx_maternity_desert_geom
    ON maternity_desert_tracts USING GIST(geom);