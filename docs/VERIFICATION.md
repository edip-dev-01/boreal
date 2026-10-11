# Verification record

Local source verification on 2026-10-11. “Not run” is not a pass. CI results, once available, should be checked separately for the exact commit under review.

## Passed locally

- Backend clean isolated install using the hash-pinned development lock (Python 3.12, FastAPI 0.143.0, psycopg 3.3.6).
- `cd backend && python -m unittest discover -s tests -v`: **21 passed, 7 skipped**. The skipped cases require actual PostgreSQL/PostGIS. Coverage includes unauthenticated/forged sessions, role spoofing, reader canary isolation across every API output, nested restricted source/report/link handling, CSRF/origin/host checks, session rotation/logout/expiry, bounds/freshness, deterministic question grounding, malformed and duplicate input rejection, and test-repository idempotency.
- `python -m unittest discover -s tests -v` at repository root: **4 passed**, covering generated credential uniqueness, no overwrite, owner-only file mode, empty example credentials, principal separation, and bounded source hygiene.
- Frontend `npm run typecheck`, `npm run lint`, `npm test`: **11 frontend tests passed**.
- Frontend `npm run build`: production build passed.
- Backend and script Python compilation; shell migration-runner syntax; Compose/workflow YAML structure checks passed.
- `scripts/http_smoke.py` against the explicit **test-memory** API passed: 11 reader records vs 12 analyst records, source/detail/map/search/count/Q&A canary filtering, CSRF, invalid bounds, role changes, and logout.
- Bounded credential-signature source scan passed. This is not a comprehensive secret scan or security assessment.
- Independent read-only review found two defects, both fixed and regression-tested: non-ASCII CSRF headers previously caused HTTP 500, and duplicate CSV headers were silently accepted. Duplicate JSON object keys were subsequently rejected too.

## Warnings and unverified checks

- Vite warns that the MapLibre-inclusive JS bundle is approximately 1.31 MB (364 KB gzip), above its default chunk warning threshold. This is a performance warning, not a failed build.
- Starlette emits a test-only deprecation warning for its httpx TestClient compatibility path. Current pinned tests pass.
- **Docker build/start and all 7 actual PostgreSQL/PostGIS/RLS integration tests were not run locally:** Docker and PostgreSQL executables are absent. Memory tests cannot prove database policies, spatial SQL, or transaction rollback behavior.
- **Browser interaction and visual/screenshot QA were not completed locally:** shell Chromium launch was blocked by sandbox socket restrictions, including an escalated attempt; the supported cloud browser could not reach the loopback service. No screenshot inspection or no-external-request browser result is claimed.

## Real stack verification

On a machine with Docker Compose v2, using only the disposable synthetic demo database:

```sh
python3 scripts/setup_env.py
docker compose up --build -d --wait --wait-timeout 180
python3 scripts/http_smoke.py --url http://127.0.0.1:8080
docker compose --profile verify run --rm verify
docker compose run --rm ingest
python3 scripts/http_smoke.py --url http://127.0.0.1:8080
```

The `verify` profile runs seven real DB checks with separate test read/write URLs: principal attributes and table ownership, forced RLS across every data table, nested canaries and hidden link targets, unset/invalid/transaction-local role scopes, write and SET ROLE denial, PostGIS bounds, idempotency, and an injected mid-transaction rollback. It may replace and restore the demo fixture snapshot; never point it at a customer or production database.

Optional browser smoke, after the stack is running:

```sh
pip install playwright==1.62.0
python -m playwright install --with-deps chromium
python scripts/browser_smoke.py --url http://127.0.0.1:8080
```

The script covers desktop/mobile flows, local source links, filters, evidence Q&A, role switching, API failure/retry, session expiry, map availability, page exceptions and external requests. Screenshots are written under ignored `test-results/browser/`; inspect them before calling visual QA complete.

`.github/workflows/ci.yml` runs application checks, a real Compose/PostGIS smoke, and the browser smoke after source publication. It retains only synthetic UI screenshots for seven days and requests read-only repository permissions. Creating the workflow is not evidence it has run.
