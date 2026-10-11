"""Read the entire synthetic snapshot and validate it before beginning any write."""
import csv
import hashlib
import json
from pathlib import Path

from .models import Dataset, Observation, Record


def _unique_object_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_fixtures(directory: str | Path) -> Dataset:
    directory = Path(directory)
    with (directory / "reports.json").open(encoding="utf-8") as stream:
        content = json.load(stream, object_pairs_hook=_unique_object_keys)
    expected = {"sources", "reports", "observations", "links"}
    if set(content) != expected:
        raise ValueError("reports.json must contain exactly sources, reports, observations, links")
    records = []
    baseline = []
    with (directory / "civic_facilities.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"id", "name", "kind", "longitude", "latitude", "updated_at", "access", "summary", "status", "source_id"}
        if len(reader.fieldnames or []) != len(required) or set(reader.fieldnames or []) != required:
            raise ValueError("civic_facilities.csv has an unexpected column schema")
        for row in reader:
            for key in ("longitude", "latitude", "updated_at"):
                if row[key] == "":
                    row[key] = None
            record = Record.model_validate(row)
            records.append(record)
            for field in ("name", "kind", "longitude", "latitude", "updated_at", "summary", "status"):
                value = getattr(record, field)
                if value is not None:
                    baseline.append(Observation(
                        id=f"{record.id}-{field}", record_id=record.id,
                        source_id=record.source_id, field=field,
                        value=value.isoformat() if hasattr(value, "isoformat") else str(value),
                        observed_at=record.updated_at, access=record.access,
                    ))
    return Dataset.model_validate({"records": records, **content, "observations": [*baseline, *content["observations"]]})


def dataset_digest(dataset: Dataset) -> str:
    encoded = json.dumps(dataset.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
