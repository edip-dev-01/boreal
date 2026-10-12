# Boreal

An original geospatial discovery demonstrator: explore synthetic community facilities, inspect conflicting evidence, and ask a small set of evidence-backed questions.

**Local demonstration only. Every facility and report is fictional. The map is a schematic illustration, not real geography or an operational map.** No real personal, government, operational, or restricted data is included. “Restricted” labels are synthetic test cases. Boreal is not affiliated with or endorsed by any organization.

## What it demonstrates

- Linked MapLibre map, searchable records, and a record-detail panel
- Text, bounding-box, and freshness filters
- Source-level and field-level provenance, missing values, and conflicting reports
- Server-side demo sessions and reader/analyst visibility applied to lists, map features, counts, details, source references, related records, and Q&A evidence
- Transactional, validated, idempotent fixture ingestion into PostgreSQL/PostGIS
- Deterministic evidence Q&A with supported question templates; **no LLM is used**
- Local map geometry and bundled client code with no external map tiles, fonts, API keys, or model service

## Easiest Windows start

1. Install the current [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) if needed, then open it and wait for its engine to start. Boreal needs **Linux containers**.
2. On this repository's GitHub page, choose **Code → Download ZIP**, then **Extract All** to a local folder. Keep the entire extracted folder together.
3. Double-click **`start-boreal.cmd`** in that folder. The first build may take several minutes. Your browser opens only after Boreal and its database are ready.

The launcher needs no Git, Python, administrator prompt, or PowerShell execution-policy change. It uses Windows PowerShell 5.1, included with Windows. If Windows or an organization policy blocks it, follow your administrator's approved process; do not disable security protections.

The launcher checks Docker Desktop, creates unique disposable credentials only when `.env` is absent, and keeps an existing `.env` and database volume unchanged. New credentials are written with a Windows ACL granting access only to your current account. It never displays the credentials or raw configuration. Only local Docker contexts and their built-in Docker image builder are accepted; the UI stays on `127.0.0.1`. Builder selection applies only to this launch process, without changing your saved Docker settings. It uses the bundled `compose.yaml` and the `.env` beside the launcher, not Compose override files or inherited shell values for the demo's settings.

Choose **Demo reader** or **Demo analyst** in the browser. Closing the launch window leaves the demo running. To stop without deleting data, open **Docker Desktop → Containers** and stop the **boreal** group. To start again, double-click the launcher in the **same folder**. Keep that folder's `.env` with your existing demo data.

### Windows troubleshooting

- **Docker missing or not ready:** install/open Docker Desktop, wait for its engine, then try again. Update Docker Desktop if Compose is missing/older than 2.20 or its builder checks fail. The builder check requires a recent Buildx with JSON listing support (0.27 or newer). If needed, use Docker Desktop's menu to switch to Linux containers.
- **Remote context, custom builder, or custom `DOCKER_HOST`:** the launcher refuses remote Docker engines/builders. Select a local Docker Desktop context yourself, or ask your Docker administrator for help. It does not change your saved Docker settings.
- **Port already in use:** edit only `BOREAL_PORT=8080` in `.env`, for example to `BOREAL_PORT=8081`, save, and launch again. Leave the three generated password lines unchanged. Do not share `.env`.
- **Invalid or incomplete `.env`:** the launcher leaves it untouched. Check its required entries against `.env.example`; restore your original credentials if you already have a database. A missing `.env` alongside an existing Boreal data volume is deliberately blocked so that new credentials do not lock you out of your data.
- **Build/startup or health timeout:** look at the **boreal** containers in Docker Desktop. Check available disk space, internet access for the first download, and the port. The launcher waits up to 180 seconds for container readiness after the build, then up to 90 seconds for Boreal's HTTP health check. It keeps the error window open and never resets your database. Rerunning the same launcher is safe.
- **Browser did not open:** if the launcher says Boreal is ready, open the local address it prints manually.

Startup messages show stages rather than raw Docker logs, which can contain configuration values. Review any container logs locally before sharing them.

## Start with Docker Compose (other platforms or manual use)

Prerequisites: Docker with the Compose v2 plugin, Python 3, and internet access for the initial image/dependency downloads. Application requests need no external services after the build.

```sh
python3 scripts/setup_env.py
docker compose up --build -d
# Once containers are ready:
# Open http://127.0.0.1:8080
```

The setup script generates unique disposable database credentials in an ignored `.env` file with owner-only permissions. It will not overwrite an existing file. Do not reuse these credentials or expose this stack publicly.

Choose **Demo reader** or **Demo analyst** in the UI. There are no usernames or passwords: both roles are intentionally selectable by anyone using the demo. Reader sees public synthetic records; analyst also sees restricted synthetic examples. This is a permission-filtering demonstration, not a real identity or authorization system.

Compose starts the database, runs the owner-only schema migration, ingests fixtures through a separate writer account, then starts the read-only API and UI. Only the web service is exposed, on `127.0.0.1:8080`. Neither PostgreSQL nor the API publishes a host port. Change `BOREAL_PORT` in `.env` before startup if 8080 is occupied. Freshness is evaluated against the explicit fixture clock in `AS_OF`, initially 2026-10-11 12:00 UTC; it is not a live data feed.

```sh
docker compose ps
docker compose logs migrate ingest api web
# Revalidate/re-ingest identical fixtures (no duplicate rows):
docker compose run --rm ingest
# Shut down while preserving data:
docker compose down
```

### Reset local demo data

The following command deletes this demo's local database volume. Do not run it against anything you want to retain.

```sh
docker compose down -v
docker compose up --build -d
```

Keep `.env` unchanged when restarting an existing volume. To rotate local demo credentials cleanly, stop and delete the disposable volume first, remove `.env`, regenerate it with the setup script, and start again. The database owner password is initialized when the volume is created.

## Develop and test without Docker

Python 3.12+ and Node 22+ are recommended. These commands use a clearly labeled **test-only in-memory repository**; they do not exercise PostgreSQL or RLS.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r backend/requirements-dev.txt
cd backend
python -m unittest discover -s tests -v
# Test-only API, loopback only:
uvicorn app.testing:app --host 127.0.0.1 --port 8000
```

In another shell:

```sh
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
# Open the local address printed by Vite.
```

Frontend API requests use `/api` through the Vite development proxy. The normal API entrypoint, `app.main:app`, requires a database URL and does not silently fall back to the test repository.

```sh
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
cd ..
python3 scripts/check_public_safe.py
```

See [Verification](docs/VERIFICATION.md) for exact checks performed in the build environment, remaining checks, and the database smoke procedure. An in-memory test pass is not evidence of a PostgreSQL/RLS pass.

## Architecture

```text
Browser (React / TypeScript / MapLibre; local schematic geometry)
  │ same-origin HTTP, opaque session cookie
Nginx on 127.0.0.1:8080
  │ /api proxy
FastAPI (one process; server-side in-memory demo sessions)
  │ readonly edip_app DB account + transaction-local role
PostgreSQL 16 / PostGIS 3.4 (forced RLS)
  ▲
Validated fixture ingestion (edip_ingest account)
  ▲
Original synthetic CSV + JSON fixtures
```

- `frontend/`: application, styles, local map asset, frontend tests
- `backend/`: API, repositories, fixture validation/ingestion, SQL migration, API/security tests
- `infra/`: container builds, proxy configuration, owner-only migration runner
- `scripts/`: local credential setup and public-source hygiene check
- `docs/`: security boundaries, provenance, and verification notes

The migration owner, ingest writer, and API reader are separate database roles. The API account is neither table owner, superuser, nor `BYPASSRLS`; rows are filtered by policies as well as repository/application projection. Request roles come from server-side sessions, never a caller-supplied role query parameter. A transaction-local database setting scopes reads and is not intended to protect a compromised API process or database credential.

## Data and licensing

All facilities, reports, identifiers, and schematic geometry were generated specifically for this demo. Coordinates are illustrative placements in a fictional area and should not be interpreted as real facility locations. Sources are bundled local fixtures, not external feeds. See [Data provenance](docs/DATA.md).

No code or original-data reuse license has been selected. Public repository visibility does not itself grant a reuse license. Third-party dependencies retain their own licenses and are not relicensed by this repository.

## Limitations

This is a small, single-process local prototype. It is not production security, a live authoritative dataset, a geospatial analysis engine, an accredited system, or an AI retrieval system. No real accounts, production secrets, live data ingestion, document OCR, vector search, exports, collaborative annotations, audit retention, monitoring, disaster recovery, or production deployment are provided. The supported Q&A only applies deterministic rules to records already visible in the current filtered view. See [Security](SECURITY.md) before adapting the architecture.
