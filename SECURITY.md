# Security scope

Boreal is a disposable, loopback-only demonstration over synthetic data. Do not place real sensitive data in it or expose it on a public interface.

## Demonstrated controls

- Opaque, random server-side sessions; the browser cannot assign a role by editing record requests
- HTTP-only, same-site cookies, request origin validation and CSRF checks for authenticated mutation-shaped requests
- A database API account separate from the migration owner and ingest writer
- PostgreSQL row-level policies on records and evidence, including synthetic restricted evidence attached to public records
- Consistent filtering of counts, search, map features, details, provenance, related links, and deterministic Q&A
- No external map tiles, analytics, browser fonts, model API, or data uploads at runtime
- Loopback-only web port; database and API remain inside the Compose network
- Unique local database credentials, generated rather than committed

## Boundaries and exclusions

The two demo roles are buttons, deliberately available to every local visitor. Anyone can select analyst. This does **not** establish real user identity, need-to-know, clearance, tenant isolation, or least-privilege account assignment. “Restricted” data is a fictional canary used to test projection boundaries, not protected real-world information.

Session storage is in memory and single-process. Restarting the API logs out sessions; multiple workers are unsupported. The local HTTP cookie is not marked Secure because local development uses HTTP. There is no identity provider, TLS termination for a production origin, persistent audit log, deployment hardening, rate-limit service, or formal security evaluation.

The API database role cannot use PostgreSQL's `BYPASSRLS` attribute or table-owner privileges. However, the API supplies a transaction-local role setting, so compromise of its process or database credentials can request the analyst setting. RLS is defense in depth for application read paths, not a boundary against a compromised application server. The migration owner remains privileged and must never be used by the web API.

The ingest account has broad write access to these synthetic tables. It is a one-shot service and is not used for web requests. A production system needs controlled ingestion authorization, validated source trust, reviewable provenance, and scoped management permissions.

## Verification expectations

Application tests run with an in-memory repository and verify attempted leakage across API surfaces. They cannot establish PostGIS SQL correctness or database policy behavior. Run the documented PostgreSQL integration/smoke checks separately. No penetration-test or security-accreditation claim is made.

Before using any real data, replace the role picker with verified identity and server-managed assignments, design a suitable authorization model, add HTTPS and persistent session/revocation handling, review data governance and dependency risks, and commission an appropriate independent assessment.
