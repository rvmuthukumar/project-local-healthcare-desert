-- Create a dedicated GIS role (mirrors gis_admin on Aurora PostgreSQL)
CREATE ROLE gis_admin LOGIN PASSWORD 'ChangeMe123!';

-- Create the geodatabase
CREATE DATABASE geodb OWNER gis_admin;
GRANT ALL PRIVILEGES ON DATABASE geodb TO gis_admin;

-- Connect to geodb and install PostGIS extensions
\connect geodb postgres

-- postgis is the core extension — for geometry types, spatial functions, GIST index support.
CREATE EXTENSION IF NOT EXISTS postgis; 
-- postgis_topology adds support for topological data models. 
CREATE EXTENSION IF NOT EXISTS postgis_topology;
-- fuzzystrmatch enables fuzzy string matching, useful for address standardisation. 
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
-- address_standardizer_data_us parses US postal addresses into components — used when geocoding hospitals that lack coordinates.
CREATE EXTENSION IF NOT EXISTS address_standardizer_data_us;

-- Verify
SELECT PostGIS_full_version();
