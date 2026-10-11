# Data provenance

## Original synthetic inputs

The CSV facilities, JSON evidence reports, and local schematic GeoJSON were created specifically for Boreal. Names, record identifiers, summaries, timestamps, links, report text, and source titles are fictional. No information about real individuals or actual facility operations is included.

The intended examples include:

- A recently observed public community facility
- Stale evidence relative to the fixed fixture clock
- A missing timestamp
- A missing coordinate pair, retained in the table but absent from map features
- Conflicting observations with separate source attribution
- A restricted synthetic facility containing a canary marker
- Restricted synthetic evidence attached to a public record
- Related-record links whose target is subject to visibility checks

The map uses a local schematic river/road/land illustration. It is not an authoritative geographic boundary or licensed external basemap. Its degree coordinates support demonstration of bounding-box queries only. Neither the map nor the point placement represents real site locations. No completeness, positional accuracy, or current-state claim should be inferred.

## Provenance semantics

A displayed source is the local fixture origin of a field or report. Source attribution does not independently verify a synthetic claim. Freshness means only age relative to the explicit `AS_OF` fixture clock. A conflicting value is preserved as source evidence rather than silently treated as truth.

Ingestion validates the entire batch before writing. Stable identifiers and content hashes allow repeats without duplicate records; invalid input must not partially update data. The application deliberately retains missing coordinates/timestamps to demonstrate incomplete-source handling while rejecting malformed coordinates and invalid references.

## Licenses

No reuse license has been granted for the original application, synthetic fixtures, or original schematic geometry. Source metadata says so explicitly. There are no third-party dataset imports. Runtime/build dependencies have their own package licenses; consult their package metadata and distribution terms before redistribution.

## Runtime network use

After initial dependency and container downloads, data, map geometry, UI assets, API queries, and deterministic question answering remain within the local stack. The UI needs no map provider key and makes no model calls. Source links point only to authorized local evidence endpoints rather than third-party websites.

## Fixture integrity

`docs/fixture-checksums.sha256` records the SHA-256 checksums of the bundled CSV, JSON, and schematic geography source. Recompute with `python3 scripts/fixture_manifest.py`; verify with `sha256sum -c docs/fixture-checksums.sha256` on platforms that provide it. These hashes establish file identity, not real-world accuracy.
