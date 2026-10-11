# Boreal backend

FastAPI + psycopg + PostgreSQL/PostGIS. This is a local, original synthetic-data
demonstration, not a deployed service, production identity system, or security
accreditation. The root Compose setup binds only loopback. No real facilities,
people, operational reports, or external geospatial services are used.

## Run and test

Use root Docker Compose for the PostgreSQL runtime. The API entrypoint is
`app.main:app`; it requires `DATABASE_URL` using the read-only `edip_app` login.
There is no automatic in-memory fallback.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r requirements-dev.txt
python -m unittest discover -s tests -v
```

For UI smoke tests only, the explicit test-double server is:

```sh
uvicorn app.testing:app --host 127.0.0.1 --port 8000
```

`/api/health` reports `test-memory` for this entrypoint. Its fixtures are validated
exactly as for PostgreSQL, but passing memory tests does **not** prove database
RLS, migrations, the SQL writer, or PostGIS have been exercised.

Database integration tests require the migrated disposable demo database and two
separate URLs. They replace only this synthetic snapshot; never point them at a
database containing real or valuable data.

```sh
TEST_DATABASE_URL='postgresql://edip_app:...@127.0.0.1/boreal' \
TEST_INGEST_DATABASE_URL='postgresql://edip_ingest:...@127.0.0.1/boreal' \
python -m unittest tests.test_postgres -v
```

The integration module needs runtime dependencies only, so it can run inside the
API image if the tests folder is copied. Without both test URLs its seven checks
are explicitly skipped. Apply `migrations/001_schema.sql` as the DB owner before
running them. The migration is rerunnable but is intended for this dedicated
demo database, not an existing shared schema.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Required API URL using `edip_app`, never the owner/ingest role |
| `INGEST_DATABASE_URL` | Required CLI writer URL using `edip_ingest` |
| `AS_OF` | Reproducible comparison instant; defaults to `2026-10-11T12:00:00Z` |
| `DEMO_ALLOWED_HOSTS` | Exact allowed hostnames, default `localhost,127.0.0.1` |
| `DEMO_ALLOWED_ORIGINS` | Mutation origins, default localhost and 127.0.0.1 port 8080 |
| `DEMO_SECURE_COOKIE` | Default `false` for loopback HTTP; true only with HTTPS |

The testing entrypoint additionally allows localhost/127.0.0.1 port 5173 for Vite.
No wildcard hosts or origins are accepted. The browser should call the API
through the same-origin frontend proxy; no CORS access is granted. No API keys or
cloud services are needed. No metrics/traces exporter is configured.

## Identity and isolation

- Anyone with access to this local demo can intentionally select reader or
  analyst. This is a simulation of authorization behavior, **not authentication
  of a person's actual clearance or identity**.
- Sessions are random opaque 256-bit tokens, stored server-side by token hash,
  expire after one hour, and are sent in host-only `HttpOnly; SameSite=Strict`
  cookies under `/api`. Login rotates the session; logout invalidates it.
- Mutations require an allowlisted Origin. Ask/logout also require the session's
  random CSRF token in `X-CSRF-Token`. Untrusted Host headers are rejected.
- The server ignores query/header role claims. The authorized application role
  is read only from the server-side session. Responses are `Cache-Control:
  no-store`.
- There is one in-memory session store per API process. Use **one worker**. A
  restart signs everyone out. Shared persistent identity/session infrastructure,
  rate limiting, TLS, audit review, and OIDC are outside this demo's scope.

The SQL migration creates `edip_app` and `edip_ingest` without passwords; the
root local bootstrap assigns generated passwords. Both are `NOSUPERUSER`,
`NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`. The API receives only
SELECT grants. The ingest role receives DML grants and explicit RLS writer
policies, but owns no tables. The owner only migrates.

All six data tables enable and force RLS. Sources, records, observations,
reports, and links have reader/analyst SELECT policies. Child observations and
reports require their parent record **and** source to be visible. Links require
both endpoints. The ingestion hash is not readable by the API role. Missing or
invalid application roles produce no rows. Every API load sets
`app.demo_role` with transaction-local `set_config`, inside a read-only,
repeatable-read transaction. SQL statements use bound parameters; spatial bounds
use `ST_MakeEnvelope`, `ST_Intersects`, and a GiST geometry index.

This policy protects against accidentally returning rows outside the current
application scope. It does not protect against a compromised API process that
can choose an arbitrary `app.demo_role`, stolen DB credentials, or a database
superuser. The API health/read guard rejects dangerous login attributes,
membership in other DB roles, owned tables, write privileges, missing RLS, and
missing FORCE RLS. Credentials must remain restricted to the local runtime.

## Fixtures and ingestion

`fixtures/civic_facilities.csv` is the original synthetic facility register.
`fixtures/reports.json` provides original synthetic sources, reports,
field-level observations, and relationships. These have no reuse license grant;
every source is explicitly labeled `Unlicensed synthetic demo`. Each source link
is a protected local `/api/sources/{id}` endpoint. Raw fixture files are never
served as public static content.

```sh
INGEST_DATABASE_URL='postgresql://edip_ingest:...@db/boreal' \
python -m app.ingest --fixtures fixtures
```

Ingestion first validates the full cross-file snapshot: exact unique CSV headers,
unique IDs, finite/ranged paired coordinates, timezone-aware dates, reference
integrity, source classification, and synthetic/license labels. A content hash
makes an identical current snapshot a no-op. A changed snapshot is replaced in
one transaction under a writer advisory lock. Any failure rolls back all deletes
and inserts. Stable IDs are primary keys; no duplicate rows accumulate. Loading
A, then B, then A restores A rather than skipping because A once existed.

The frozen snapshot contains 12 records: reader sees 11, analyst sees 12. Reader
has 10 map points, 3 stale records (>90 days), 1 missing update timestamp, 1 missing
coordinate record, and 1 conflicting status. Analyst sees an additional nested
status conflict and the restricted canary. The public library has a restricted
report, source, observation, and link specifically to catch nested leakage. A
second nominally public link targets a restricted record to test endpoint
visibility. Derived conflict/source fields are computed only from visible data.

## API

- `GET /api/session`: current session and CSRF token, or unauthenticated state
- `POST /api/login`: `{ "role": "reader" | "analyst" }`, requires Origin
- `POST /api/logout`: Origin + CSRF token, invalidates session
- `GET /api/records`, `/api/search`, `/api/counts`, `/api/map`: identical permitted
  query scope; filters `q`, `freshness=all|fresh|stale|missing`, optional `bbox`
- `GET /api/records/{id}`: role-filtered field provenance, source links, reports,
  and relationships; inaccessible and absent IDs both return 404
- `GET /api/sources/{id}`: authorized source and visible record references
- `POST /api/ask`: deterministic rules only; Origin + CSRF required
- `GET /api/health`: repository type, synthetic flag, frozen cutoff; no secrets
- `GET /api/openapi.json`: local API schema; no externally hosted Swagger assets

`bbox` is `west,south,east,north` in WGS84 degrees, with strict finite ordered
bounds. Dateline-crossing boxes are rejected rather than guessed. Missing
coordinates are counted in a general view but excluded from spatial queries and
map features. `freshness=missing` means missing update timestamp; missing
coordinates are a separate quality flag. Text search is a literal case-insensitive
substring of name, kind, summary, and base status, not full-text report search.

Ask accepts the four explicit question types `count facilities`, `stale
facilities`, `conflicting reports`, and `missing coordinates`, plus a small exact
allowlist of equivalent prompts. It answers only from the authorized filtered
records and returns clickable record evidence. Unsupported questions are declined
with `supported: false`; there is no model call or invented answer. Conflicting
visible status observations are shown side-by-side, never silently reconciled.
