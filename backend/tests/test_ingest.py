import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.fixtures import dataset_digest, load_fixtures
from app.models import Dataset
from app.repository import MemoryRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for source in FIXTURES.glob("*"):
            if source.is_file():
                shutil.copy(source, self.directory)
        self.dataset = load_fixtures(self.directory)
        self.repository = MemoryRepository(self.dataset)

    def edit_csv(self, fn):
        path = self.directory / "civic_facilities.csv"
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames
            rows = list(reader)
        fn(rows)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def test_repeat_is_idempotent_and_changed_snapshot_replaces(self):
        first = self.repository.ingest(self.dataset)
        second = self.repository.ingest(load_fixtures(self.directory))
        self.assertTrue(first["skipped"])
        self.assertTrue(second["skipped"])
        self.assertEqual(first["digest"], second["digest"])
        self.edit_csv(lambda rows: rows[0].update(name="Alder Library revised synthetic name"))
        changed = self.repository.ingest(load_fixtures(self.directory))
        self.assertFalse(changed["skipped"])
        self.assertNotEqual(first["digest"], changed["digest"])
        self.assertEqual(changed["records"], 12)
        self.assertEqual(len(self.repository.load("analyst").records), 12)
        # Loading A, then B, then A restores A rather than skipping an old hash.
        restored = self.repository.ingest(self.dataset)
        self.assertFalse(restored["skipped"])
        self.assertEqual(restored["digest"], first["digest"])

    def test_invalid_fixture_is_rejected_without_changing_snapshot(self):
        before = dataset_digest(self.repository.load("analyst"))
        self.edit_csv(lambda rows: rows[0].update(longitude="999"))
        with self.assertRaises(ValueError):
            self.repository.ingest(load_fixtures(self.directory))
        self.assertEqual(before, dataset_digest(self.repository.load("analyst")))

    def test_duplicate_csv_id_is_rejected(self):
        self.edit_csv(lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(ValueError, "duplicate records"):
            load_fixtures(self.directory)

    def test_duplicate_report_id_is_rejected(self):
        path = self.directory / "reports.json"
        data = json.loads(path.read_text())
        data["reports"].append(data["reports"][0].copy())
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "duplicate reports"):
            load_fixtures(self.directory)

    def test_duplicate_json_object_key_is_rejected(self):
        path = self.directory / "reports.json"
        path.write_text(path.read_text().replace('"access": "public"', '"access": "public", "access": "restricted"', 1))
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            load_fixtures(self.directory)

    def test_unknown_foreign_key_and_public_restricted_source_are_rejected(self):
        for source_id in ("src-unknown", "src-restricted-memo"):
            data = self.dataset.model_dump()
            data["records"][0]["source_id"] = source_id
            with self.assertRaises(ValueError):
                Dataset.model_validate(data)

    def test_nonfinite_partial_coordinate_and_naive_timestamp_are_rejected(self):
        for patch in ({"longitude": float("nan")}, {"latitude": None}, {"updated_at": "2026-10-01T09:00:00"}, {"longitude": float("inf")}):
            data = self.dataset.model_dump()
            data["records"][0].update(patch)
            with self.assertRaises(ValueError):
                Dataset.model_validate(data)

    def test_license_and_source_link_constraints(self):
        for change in ({"synthetic": False}, {"license": "unknown"}, {"url": "https://tracking.example/private"}, {"url": "/api/sources/wrong-source"}):
            data = self.dataset.model_dump()
            data["sources"][0].update(change)
            with self.assertRaises(ValueError):
                Dataset.model_validate(data)

    def test_unknown_role_and_csv_schema_rejected(self):
        with self.assertRaises(ValueError):
            self.repository.load("admin")
        path = self.directory / "civic_facilities.csv"
        path.write_text(path.read_text().replace("longitude", "lng", 1))
        with self.assertRaisesRegex(ValueError, "unexpected column schema"):
            load_fixtures(self.directory)

    def test_duplicate_csv_column_is_rejected(self):
        path = self.directory / "civic_facilities.csv"
        path.write_text(path.read_text().replace("source_id\n", "source_id,access\n", 1))
        with self.assertRaisesRegex(ValueError, "unexpected column schema"):
            load_fixtures(self.directory)


if __name__ == "__main__":
    unittest.main()
