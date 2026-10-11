"""Atomic, content-addressed synthetic fixture ingestion with a separate writer."""
import argparse
import json
import os
from pathlib import Path

from .fixtures import dataset_digest, load_fixtures
from .models import Dataset


def ingest_dataset(database_url: str, dataset: Dataset) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    # Revalidate even callers who constructed a Dataset with model_construct().
    dataset = Dataset.model_validate(dataset.model_dump())
    digest = dataset_digest(dataset)
    if not database_url:
        raise ValueError("INGEST_DATABASE_URL is required")
    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=5) as connection:
        principal = connection.execute("SELECT current_user AS name, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if principal["name"] != "edip_ingest" or principal["rolsuper"] or principal["rolbypassrls"]:
            raise ValueError("Ingestion requires the separate non-superuser edip_ingest login")
        # Serialize snapshot writers without exposing a partial replace to readers.
        connection.execute("SELECT pg_advisory_xact_lock(73100420)")
        current = connection.execute("SELECT digest FROM ingestion_batches WHERE id='current'").fetchone()
        if current and current["digest"] == digest:
            return {"skipped": True, "digest": digest, "records": len(dataset.records)}
        for table in ("record_links", "observations", "reports", "records", "sources", "ingestion_batches"):
            connection.execute(f"DELETE FROM {table}")  # fixed allowlist, no user SQL identifiers
        with connection.cursor() as cursor:
            cursor.executemany("INSERT INTO sources (id,title,type,license,synthetic,url,access) VALUES (%(id)s,%(title)s,%(type)s,%(license)s,%(synthetic)s,%(url)s,%(access)s)", [row.model_dump() for row in dataset.sources])
            cursor.executemany("INSERT INTO records (id,name,kind,geom,updated_at,access,summary,status,source_id) VALUES (%(id)s,%(name)s,%(kind)s,CASE WHEN %(longitude)s::double precision IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%(longitude)s::double precision,%(latitude)s::double precision),4326) END,%(updated_at)s,%(access)s,%(summary)s,%(status)s,%(source_id)s)", [row.model_dump() for row in dataset.records])
            cursor.executemany("INSERT INTO observations (id,record_id,source_id,field,value,observed_at,access) VALUES (%(id)s,%(record_id)s,%(source_id)s,%(field)s,%(value)s,%(observed_at)s,%(access)s)", [row.model_dump() for row in dataset.observations])
            cursor.executemany("INSERT INTO reports (id,record_id,source_id,title,text,observed_at,access) VALUES (%(id)s,%(record_id)s,%(source_id)s,%(title)s,%(text)s,%(observed_at)s,%(access)s)", [row.model_dump() for row in dataset.reports])
            cursor.executemany("INSERT INTO record_links (id,from_id,to_id,label,access) VALUES (%(id)s,%(from_id)s,%(to_id)s,%(label)s,%(access)s)", [row.model_dump() for row in dataset.links])
        connection.execute("INSERT INTO ingestion_batches (id,digest,record_count) VALUES ('current',%s,%s)", (digest, len(dataset.records)))
    return {"skipped": False, "digest": digest, "records": len(dataset.records)}


def ingest_directory(database_url: str, directory: str | Path) -> dict:
    # All cross-file validation happens before a DB connection or first write.
    return ingest_dataset(database_url, load_fixtures(directory))


def main():
    parser = argparse.ArgumentParser(description="Load the complete, original synthetic Boreal fixture snapshot")
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).parent.parent / "fixtures")
    args = parser.parse_args()
    result = ingest_directory(os.environ.get("INGEST_DATABASE_URL", ""), args.fixtures)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
