"""PostgreSQL is the only runtime repository. MemoryRepository is a test double."""
from __future__ import annotations

from copy import deepcopy
from typing import Protocol

from .fixtures import dataset_digest
from .models import Dataset, Role


class Repository(Protocol):
    def load(self, role: Role, bbox=None) -> Dataset: ...
    def probe(self) -> None: ...


class MemoryRepository:
    """Unit/integration-test double, never selected by app.main or environment fallback."""

    def __init__(self, dataset: Dataset):
        self._dataset = dataset.model_copy(deep=True)
        self._digest = dataset_digest(dataset)

    def probe(self):
        return None

    def ingest(self, dataset: Dataset) -> dict:
        validated = Dataset.model_validate(dataset.model_dump())
        digest = dataset_digest(validated)
        skipped = digest == self._digest
        if not skipped:
            self._dataset = validated.model_copy(deep=True)
            self._digest = digest
        return {"skipped": skipped, "digest": digest, "records": len(validated.records)}

    def load(self, role: Role, bbox=None) -> Dataset:
        if role not in ("reader", "analyst"):
            raise ValueError("unknown application role")
        visible = lambda row: row.access == "public" or role == "analyst"
        sources = [s for s in self._dataset.sources if visible(s)]
        source_ids = {s.id for s in sources}
        records = [r for r in self._dataset.records if visible(r) and r.source_id in source_ids]
        if bbox:
            west, south, east, north = bbox
            records = [r for r in records if r.longitude is not None and west <= r.longitude <= east and south <= r.latitude <= north]
        record_ids = {r.id for r in records}
        observations = [o for o in self._dataset.observations if visible(o) and o.record_id in record_ids and o.source_id in source_ids]
        reports = [r for r in self._dataset.reports if visible(r) and r.record_id in record_ids and r.source_id in source_ids]
        links = [l for l in self._dataset.links if visible(l) and l.from_id in record_ids and l.to_id in record_ids]
        return Dataset(sources=deepcopy(sources), records=deepcopy(records), observations=deepcopy(observations), reports=deepcopy(reports), links=deepcopy(links))


class PostgresRepository:
    """Every read uses a short transaction, a fixed SQL role, and forced RLS.

    The DB login MUST be edip_app. Application scope is SET LOCAL, never a
    persistent connection setting and never derived from a client-provided role.
    """

    def __init__(self, database_url: str):
        if not database_url:
            raise RuntimeError("DATABASE_URL is required; the application does not fall back to in-memory data")
        self._database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self._database_url, row_factory=dict_row, connect_timeout=5)

    @staticmethod
    def _assert_readonly_principal(connection):
        row = connection.execute("SELECT current_user AS name, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, oid FROM pg_roles WHERE rolname = current_user").fetchone()
        if row["name"] != "edip_app" or any(row[flag] for flag in ("rolsuper", "rolbypassrls", "rolcreatedb", "rolcreaterole")):
            raise RuntimeError("Runtime must use the non-superuser, non-bypass-RLS edip_app login")
        if connection.execute("SELECT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=%s) AS unsafe", (row["oid"],)).fetchone()["unsafe"]:
            raise RuntimeError("Runtime login must not be a member of other database roles")
        checks = connection.execute("SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity, c.relowner=%s AS owns_table, has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS writes FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('sources','records','observations','reports','record_links')", (row["oid"],)).fetchall()
        if len(checks) != 5 or any(check["owns_table"] or check["writes"] or not check["relrowsecurity"] or not check["relforcerowsecurity"] for check in checks):
            raise RuntimeError("Runtime tables must be non-owned, read-only, and protected by forced RLS")

    def probe(self):
        with self._connect() as connection:
            self._assert_readonly_principal(connection)

    def load(self, role: Role, bbox=None) -> Dataset:
        if role not in ("reader", "analyst"):
            raise ValueError("unknown application role")
        with self._connect() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            self._assert_readonly_principal(connection)
            connection.execute("SELECT set_config('app.demo_role', %s, true)", (role,))
            sql = "SELECT id,name,kind,ST_X(geom) AS longitude,ST_Y(geom) AS latitude,updated_at,access,summary,status,source_id FROM records"
            args = ()
            if bbox:
                sql += " WHERE geom && ST_MakeEnvelope(%s,%s,%s,%s,4326) AND ST_Intersects(geom,ST_MakeEnvelope(%s,%s,%s,%s,4326))"
                args = (*bbox, *bbox)
            records = connection.execute(sql + " ORDER BY id", args).fetchall()
            record_ids = [record["id"] for record in records]
            sources = connection.execute("SELECT id,title,type,license,synthetic,url,access FROM sources ORDER BY id").fetchall()
            observations = connection.execute("SELECT id,record_id,source_id,field,value,observed_at,access FROM observations WHERE record_id=ANY(%s) ORDER BY id", (record_ids,)).fetchall()
            reports = connection.execute("SELECT id,record_id,source_id,title,text,observed_at,access FROM reports WHERE record_id=ANY(%s) ORDER BY id", (record_ids,)).fetchall()
            links = connection.execute("SELECT id,from_id,to_id,label,access FROM record_links WHERE from_id=ANY(%s) AND to_id=ANY(%s) ORDER BY id", (record_ids, record_ids)).fetchall()
        return Dataset(sources=sources, records=records, observations=observations, reports=reports, links=links)
