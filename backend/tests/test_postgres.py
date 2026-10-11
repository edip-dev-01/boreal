"""Real PostgreSQL/PostGIS tests; run only against this demo's disposable DB.

The DB owner must apply migrations first. These tests replace the synthetic
snapshot. TEST_DATABASE_URL must use edip_app; TEST_INGEST_DATABASE_URL uses
edip_ingest. No production/customer database is appropriate.
"""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.fixtures import load_fixtures
from app.ingest import ingest_dataset
from app.models import Dataset
from app.repository import MemoryRepository, PostgresRepository

APP_URL = os.environ.get("TEST_DATABASE_URL")
INGEST_URL = os.environ.get("TEST_INGEST_DATABASE_URL")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CANARY = "NIMBUS-RESTRICTED-CANARY-947"


@unittest.skipUnless(APP_URL and INGEST_URL, "Requires disposable PostgreSQL/PostGIS TEST_DATABASE_URL and TEST_INGEST_DATABASE_URL")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.dataset = load_fixtures(FIXTURES)
        ingest_dataset(INGEST_URL, cls.dataset)
        cls.repository = PostgresRepository(APP_URL)

    def test_runtime_principal_and_forced_rls_security(self):
        self.repository.probe()
        with self.psycopg.connect(APP_URL) as connection:
            name, superuser, bypass, create_role, create_db = connection.execute("SELECT current_user,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user").fetchone()
            self.assertEqual(name, "edip_app")
            self.assertFalse(any((superuser, bypass, create_role, create_db)))
            tables = connection.execute("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relowner=current_user::regrole FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('sources','records','observations','reports','record_links','ingestion_batches')").fetchall()
            self.assertEqual(len(tables), 6)
            self.assertTrue(all(rls and forced and not owner for _, rls, forced, owner in tables))
            self.assertEqual(connection.execute("SELECT PostGIS_Version()").fetchone()[0].split()[0].split('.')[0], "3")

    def test_unset_or_invalid_role_fails_closed_and_set_local_does_not_leak(self):
        with self.psycopg.connect(APP_URL) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM records").fetchone()[0], 0)
            connection.execute("SELECT set_config('app.demo_role','administrator',true)")
            self.assertEqual(connection.execute("SELECT count(*) FROM records").fetchone()[0], 0)
            connection.execute("SELECT set_config('app.demo_role','reader',true)")
            self.assertEqual(connection.execute("SELECT count(*) FROM records").fetchone()[0], 11)
            connection.commit()
            self.assertEqual(connection.execute("SELECT count(*) FROM records").fetchone()[0], 0)
            connection.commit()
            for role, count in (("reader", 11), ("analyst", 12), ("reader", 11)):
                connection.execute("SELECT set_config('app.demo_role',%s,true)", (role,))
                self.assertEqual(connection.execute("SELECT count(*) FROM records").fetchone()[0], count)
                connection.commit()

    def test_database_rls_filters_every_table_and_nested_canary(self):
        for role, counts in (("reader", (3, 11, 75, 2, 3)), ("analyst", (5, 12, 83, 4, 5))):
            with self.psycopg.connect(APP_URL) as connection:
                connection.execute("SELECT set_config('app.demo_role',%s,true)", (role,))
                for table, expected in zip(("sources", "records", "observations", "reports", "record_links"), counts):
                    rows = connection.execute(f"SELECT row_to_json(t)::text FROM {table} t").fetchall()
                    self.assertEqual(len(rows), expected, table)
                    if role == "reader":
                        self.assertNotIn(CANARY, repr(rows))
                        self.assertNotIn("fac-canary-annex", repr(rows))
                if role == "reader":
                    self.assertEqual(connection.execute("SELECT count(*) FROM reports WHERE record_id='fac-alder-library'").fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT count(*) FROM record_links WHERE to_id='fac-canary-annex'").fetchone()[0], 0)
            visible = self.repository.load(role)
            expected = MemoryRepository(self.dataset).load(role)
            for collection in ("sources", "records", "observations", "reports", "links"):
                self.assertEqual({item.id for item in getattr(visible, collection)}, {item.id for item in getattr(expected, collection)}, collection)

    def test_runtime_role_cannot_mutate_or_read_ingestion_metadata(self):
        for statement in ("DELETE FROM records", "UPDATE records SET name='unauthorized'", "TRUNCATE records", "SELECT * FROM ingestion_batches", "CREATE TABLE public.unauthorized(id int)", "SET ROLE edip_ingest"):
            with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                with self.psycopg.connect(APP_URL) as connection:
                    connection.execute("SELECT set_config('app.demo_role','analyst',true)")
                    connection.execute(statement)

    def test_postgis_bbox_matches_test_repository(self):
        for role in ("reader", "analyst"):
            for bbox in ((-75.76, 45.40, -75.66, 45.47), (-180, -90, 180, 90), (0, 0, 1, 1)):
                actual = self.repository.load(role, bbox)
                expected = MemoryRepository(self.dataset).load(role, bbox)
                self.assertEqual({item.id for item in actual.records}, {item.id for item in expected.records})
                self.assertNotIn("fac-mobile-unit", {item.id for item in actual.records})

    def test_sql_ingestion_idempotency_and_rollback_after_partial_write(self):
        first = ingest_dataset(INGEST_URL, self.dataset)
        second = ingest_dataset(INGEST_URL, self.dataset)
        self.assertTrue(first["skipped"])
        self.assertTrue(second["skipped"])
        before = self.repository.load("analyst")
        changed_data = self.dataset.model_dump()
        changed_data["records"][0]["summary"] = "Changed synthetic summary to test atomic rollback."
        changed = Dataset.model_validate(changed_data)
        original = self.psycopg.Cursor.executemany

        def injected_failure(cursor, query, params, **kwargs):
            if query.startswith("INSERT INTO records"):
                raise RuntimeError("Injected test failure after DELETE and source INSERT")
            return original(cursor, query, params, **kwargs)

        with patch("psycopg.Cursor.executemany", new=injected_failure):
            with self.assertRaisesRegex(RuntimeError, "Injected test failure"):
                ingest_dataset(INGEST_URL, changed)
        after = self.repository.load("analyst")
        self.assertEqual(after, before)
        self.assertTrue(ingest_dataset(INGEST_URL, self.dataset)["skipped"])
        # A successful changed snapshot updates rows, retaining exactly one record
        # per stable ID, and the original fixture is restored in a finally block.
        try:
            result = ingest_dataset(INGEST_URL, changed)
            self.assertFalse(result["skipped"])
            self.assertEqual(len(self.repository.load("analyst").records), 12)
        finally:
            ingest_dataset(INGEST_URL, self.dataset)

    def test_invalid_fixture_fails_before_database_connection(self):
        corrupt = self.dataset.model_copy(deep=True)
        corrupt.records[0].longitude = 999
        with patch("psycopg.connect") as connect:
            with self.assertRaises(ValueError):
                ingest_dataset(INGEST_URL, corrupt)
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
