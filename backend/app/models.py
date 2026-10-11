"""Validated fixture and request contracts; no application role comes from query input."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Role = Literal["reader", "analyst"]
Access = Literal["public", "restricted"]
Freshness = Literal["all", "fresh", "stale", "missing"]
ID_PATTERN = r"^[a-z][a-z0-9_-]{1,63}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Source(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1, max_length=160)
    type: Literal["synthetic-csv", "synthetic-report"]
    license: Literal["Unlicensed synthetic demo"]
    synthetic: Literal[True]
    url: str = Field(pattern=r"^/api/sources/[a-z][a-z0-9_-]{1,63}$")
    access: Access = "public"

    @model_validator(mode="after")
    def own_evidence_url(self):
        if self.url != f"/api/sources/{self.id}":
            raise ValueError("source URL must point to its own protected evidence endpoint")
        return self


class Record(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=60)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    updated_at: datetime | None = None
    access: Access
    summary: str = Field(min_length=1, max_length=1500)
    status: str = Field(min_length=1, max_length=100)
    source_id: str = Field(pattern=ID_PATTERN)

    @field_validator("updated_at")
    @classmethod
    def aware_datetime(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("updated_at must include an explicit timezone")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.longitude is None) != (self.latitude is None):
            raise ValueError("longitude and latitude must both be present or both be missing")
        return self


class Observation(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    record_id: str = Field(pattern=ID_PATTERN)
    source_id: str = Field(pattern=ID_PATTERN)
    field: Literal["name", "kind", "longitude", "latitude", "updated_at", "summary", "status", "capacity"]
    value: str = Field(max_length=1500)
    observed_at: datetime | None
    access: Access

    _aware = field_validator("observed_at")(Record.aware_datetime.__func__)


class Report(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    record_id: str = Field(pattern=ID_PATTERN)
    source_id: str = Field(pattern=ID_PATTERN)
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=8000)
    observed_at: datetime
    access: Access

    _aware = field_validator("observed_at")(Record.aware_datetime.__func__)


class Link(StrictModel):
    id: str = Field(pattern=ID_PATTERN)
    from_id: str = Field(pattern=ID_PATTERN)
    to_id: str = Field(pattern=ID_PATTERN)
    label: str = Field(min_length=1, max_length=160)
    access: Access


class Dataset(StrictModel):
    sources: list[Source]
    records: list[Record]
    observations: list[Observation]
    reports: list[Report]
    links: list[Link]

    @model_validator(mode="after")
    def validate_references(self):
        for name in ("sources", "records", "observations", "reports", "links"):
            rows = getattr(self, name)
            ids = [row.id for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {name} identifier")
        sources = {source.id: source for source in self.sources}
        records = {record.id: record for record in self.records}
        for row in self.records:
            if row.source_id not in sources:
                raise ValueError(f"unknown source for record {row.id}")
            if row.access == "public" and sources[row.source_id].access == "restricted":
                raise ValueError("public record must have a public base source")
        for row in [*self.observations, *self.reports]:
            if row.record_id not in records or row.source_id not in sources:
                raise ValueError(f"unknown record/source for {row.id}")
            if row.access == "public" and sources[row.source_id].access == "restricted":
                raise ValueError("public content must not cite a restricted source")
        for row in self.links:
            if row.from_id not in records or row.to_id not in records:
                raise ValueError(f"unknown link endpoint for {row.id}")
        return self


class LoginRequest(StrictModel):
    role: Role


class AskRequest(StrictModel):
    question: str = Field(min_length=1, max_length=500)
    q: str = Field(default="", max_length=200)
    freshness: Freshness = "all"
    bbox: str | None = Field(default=None, max_length=200)
