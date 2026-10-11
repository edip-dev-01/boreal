-- Boreal, original synthetic-data local demonstration. Apply as database owner.
-- Rerunnable migration. Passwords are configured by a separate local bootstrap;
-- no credentials belong in source control. PostgreSQL 16 + PostGIS 3.4.
BEGIN;
CREATE EXTENSION IF NOT EXISTS postgis;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edip_app') THEN
        CREATE ROLE edip_app LOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'edip_ingest') THEN
        CREATE ROLE edip_ingest LOGIN;
    END IF;
END $$;
ALTER ROLE edip_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
ALTER ROLE edip_ingest NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO edip_app, edip_ingest;

CREATE TABLE IF NOT EXISTS sources (
    id text PRIMARY KEY,
    title text NOT NULL,
    type text NOT NULL CHECK (type IN ('synthetic-csv','synthetic-report')),
    license text NOT NULL CHECK (license = 'Unlicensed synthetic demo'),
    synthetic boolean NOT NULL CHECK (synthetic),
    url text NOT NULL,
    access text NOT NULL CHECK (access IN ('public','restricted'))
);
CREATE TABLE IF NOT EXISTS records (
    id text PRIMARY KEY,
    name text NOT NULL,
    kind text NOT NULL,
    geom geometry(Point,4326),
    updated_at timestamptz,
    access text NOT NULL CHECK (access IN ('public','restricted')),
    summary text NOT NULL,
    status text NOT NULL,
    source_id text NOT NULL REFERENCES sources(id),
    CHECK (geom IS NULL OR (ST_X(geom) BETWEEN -180 AND 180 AND ST_Y(geom) BETWEEN -90 AND 90))
);
CREATE INDEX IF NOT EXISTS records_geom_gix ON records USING gist (geom);
CREATE INDEX IF NOT EXISTS records_updated_idx ON records (updated_at);
CREATE TABLE IF NOT EXISTS observations (
    id text PRIMARY KEY,
    record_id text NOT NULL REFERENCES records(id),
    source_id text NOT NULL REFERENCES sources(id),
    field text NOT NULL CHECK (field IN ('name','kind','longitude','latitude','updated_at','summary','status','capacity')),
    value text NOT NULL,
    observed_at timestamptz,
    access text NOT NULL CHECK (access IN ('public','restricted'))
);
CREATE INDEX IF NOT EXISTS observations_record_idx ON observations (record_id);
CREATE TABLE IF NOT EXISTS reports (
    id text PRIMARY KEY,
    record_id text NOT NULL REFERENCES records(id),
    source_id text NOT NULL REFERENCES sources(id),
    title text NOT NULL,
    text text NOT NULL,
    observed_at timestamptz NOT NULL,
    access text NOT NULL CHECK (access IN ('public','restricted'))
);
CREATE INDEX IF NOT EXISTS reports_record_idx ON reports (record_id);
CREATE TABLE IF NOT EXISTS record_links (
    id text PRIMARY KEY,
    from_id text NOT NULL REFERENCES records(id),
    to_id text NOT NULL REFERENCES records(id),
    label text NOT NULL,
    access text NOT NULL CHECK (access IN ('public','restricted'))
);
CREATE TABLE IF NOT EXISTS ingestion_batches (
    id text PRIMARY KEY CHECK (id = 'current'),
    digest text NOT NULL,
    record_count integer NOT NULL,
    loaded_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources FORCE ROW LEVEL SECURITY;
ALTER TABLE records ENABLE ROW LEVEL SECURITY;
ALTER TABLE records FORCE ROW LEVEL SECURITY;
ALTER TABLE observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE observations FORCE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;
ALTER TABLE record_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE record_links FORCE ROW LEVEL SECURITY;
ALTER TABLE ingestion_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion_batches FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS sources_read ON sources;
CREATE POLICY sources_read ON sources FOR SELECT TO edip_app USING (
    current_setting('app.demo_role', true) IN ('reader','analyst')
    AND (access = 'public' OR current_setting('app.demo_role', true) = 'analyst')
);
DROP POLICY IF EXISTS records_read ON records;
CREATE POLICY records_read ON records FOR SELECT TO edip_app USING (
    current_setting('app.demo_role', true) IN ('reader','analyst')
    AND (access = 'public' OR current_setting('app.demo_role', true) = 'analyst')
    AND EXISTS (SELECT 1 FROM sources s WHERE s.id = source_id)
);
DROP POLICY IF EXISTS observations_read ON observations;
CREATE POLICY observations_read ON observations FOR SELECT TO edip_app USING (
    current_setting('app.demo_role', true) IN ('reader','analyst')
    AND (access = 'public' OR current_setting('app.demo_role', true) = 'analyst')
    AND EXISTS (SELECT 1 FROM records r WHERE r.id = record_id)
    AND EXISTS (SELECT 1 FROM sources s WHERE s.id = source_id)
);
DROP POLICY IF EXISTS reports_read ON reports;
CREATE POLICY reports_read ON reports FOR SELECT TO edip_app USING (
    current_setting('app.demo_role', true) IN ('reader','analyst')
    AND (access = 'public' OR current_setting('app.demo_role', true) = 'analyst')
    AND EXISTS (SELECT 1 FROM records r WHERE r.id = record_id)
    AND EXISTS (SELECT 1 FROM sources s WHERE s.id = source_id)
);
DROP POLICY IF EXISTS links_read ON record_links;
CREATE POLICY links_read ON record_links FOR SELECT TO edip_app USING (
    current_setting('app.demo_role', true) IN ('reader','analyst')
    AND (access = 'public' OR current_setting('app.demo_role', true) = 'analyst')
    AND EXISTS (SELECT 1 FROM records r WHERE r.id = from_id)
    AND EXISTS (SELECT 1 FROM records r WHERE r.id = to_id)
);

-- Writer role has only data manipulation grants, no table ownership, role admin,
-- schema creation, or bypass RLS. Its separate policies authorize fixture loading.
DO $$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['sources','records','observations','reports','record_links','ingestion_batches'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS ingest_all ON %I', table_name);
        EXECUTE format('CREATE POLICY ingest_all ON %I FOR ALL TO edip_ingest USING (true) WITH CHECK (true)', table_name);
        EXECUTE format('REVOKE ALL ON %I FROM PUBLIC, edip_app, edip_ingest', table_name);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO edip_ingest', table_name);
    END LOOP;
END $$;
GRANT SELECT ON sources, records, observations, reports, record_links TO edip_app;
COMMIT;
