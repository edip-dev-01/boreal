"""Role-scoped projection and deterministic answer rules shared across repositories."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from .models import Dataset, Freshness

STALE_AFTER_DAYS = 90


def parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    try:
        coordinates = tuple(float(part.strip()) for part in value.split(","))
        if len(coordinates) != 4 or not all(math.isfinite(n) for n in coordinates):
            raise ValueError
        west, south, east, north = coordinates
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError
        return coordinates
    except (ValueError, TypeError):
        raise ValueError("bbox must be west,south,east,north with finite, ordered longitude/latitude bounds") from None


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


def freshness_of(updated_at: datetime | None, as_of: datetime) -> str:
    if updated_at is None:
        return "missing"
    return "stale" if updated_at < as_of - timedelta(days=STALE_AFTER_DAYS) else "fresh"


def project_records(dataset: Dataset, as_of: datetime, q: str = "", freshness: Freshness = "all", bbox=None) -> list[dict]:
    """Input MUST already be permission-filtered, including its nested objects."""
    result = []
    query = q.strip().casefold()
    for record in sorted(dataset.records, key=lambda row: row.name):
        if query and query not in f"{record.name} {record.kind} {record.summary} {record.status}".casefold():
            continue
        state = freshness_of(record.updated_at, as_of)
        if freshness != "all" and state != freshness:
            continue
        if bbox:
            west, south, east, north = bbox
            if record.longitude is None or not (west <= record.longitude <= east and south <= record.latitude <= north):
                continue
        observations = [o for o in dataset.observations if o.record_id == record.id]
        statuses = {o.value.casefold().strip() for o in observations if o.field == "status"}
        sources = {record.source_id, *(o.source_id for o in observations), *(r.source_id for r in dataset.reports if r.record_id == record.id)}
        missing = []
        if record.longitude is None:
            missing.append("coordinates")
        if record.updated_at is None:
            missing.append("updated_at")
        result.append({
            "id": record.id, "name": record.name, "kind": record.kind,
            "longitude": record.longitude, "latitude": record.latitude,
            "updated_at": iso(record.updated_at), "freshness": state,
            "access": record.access, "summary": record.summary, "status": record.status,
            "conflict": len(statuses) > 1, "missing_fields": missing,
            "source_ids": sorted(sources),
        })
    return result


def detail_record(dataset: Dataset, record: dict) -> dict:
    source_map = {source.id: source for source in dataset.sources}
    record_map = {item.id: item for item in dataset.records}
    observations = [o for o in dataset.observations if o.record_id == record["id"]]
    return {
        **record,
        "provenance": [
            {"field": o.field, "value": o.value, "source_id": o.source_id,
             "source_title": source_map[o.source_id].title, "observed_at": iso(o.observed_at)}
            for o in sorted(observations, key=lambda o: (o.field, o.source_id, o.id))
        ],
        "sources": [source_map[sid].model_dump(exclude={"access"}) for sid in record["source_ids"]],
        "links": [{"record_id": link.to_id, "label": link.label} for link in dataset.links
                  if link.from_id == record["id"] and link.to_id in record_map],
        "reports": [{"id": report.id, "title": report.title, "text": report.text,
                     "observed_at": iso(report.observed_at), "source_id": report.source_id}
                    for report in dataset.reports if report.record_id == record["id"]],
    }


def answer_question(question: str, records: list[dict], as_of: datetime) -> dict:
    text = " ".join(question.lower().split()).rstrip("?.!")
    base = {"evidence": [], "supported": True, "engine": "deterministic-rules", "as_of": iso(as_of)}
    # Finite allowlist: no guessing at arbitrary intent, factual claims, or commands.
    supported = {
        "how many facilities": "count", "how many facilities are there": "count",
        "count facilities": "count", "how many facilities are in this view": "count",
        "which facilities are stale": "stale", "show stale facilities": "stale", "stale facilities": "stale",
        "which facilities have conflicting reports": "conflict", "show conflicting reports": "conflict", "conflicting reports": "conflict",
        "which facilities are missing coordinates": "missing", "show missing coordinates": "missing", "missing coordinates": "missing",
    }
    intent = supported.get(text)
    if intent is None:
        return {**base, "supported": False, "answer": "This demo supports four exact question types: count facilities, stale facilities, conflicting reports, and missing coordinates. It does not use a language model or infer unsupported facts."}
    if intent == "count":
        chosen = records
        answer = f"There are {len(chosen)} facilities in your permitted, filtered view."
    else:
        chosen = [record for record in records if
                  (intent == "stale" and record["freshness"] == "stale") or
                  (intent == "conflict" and record["conflict"]) or
                  (intent == "missing" and "coordinates" in record["missing_fields"])]
        labels = {"stale": "have updates older than 90 days", "conflict": "have conflicting visible status observations", "missing": "have no coordinates and cannot be placed on the map"}
        answer = f"{len(chosen)} facilities {labels[intent]} in your permitted, filtered view."
        if chosen:
            answer += " " + "; ".join(record["name"] for record in chosen) + "."
    return {**base, "answer": answer, "evidence": [{"record_id": record["id"], "label": record["name"]} for record in chosen]}
