#!/usr/bin/env python3
"""Print SHA-256 checksums for bundled synthetic inputs and schematic assets."""
from hashlib import sha256
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = sorted((root / "backend/fixtures").glob("*"))
paths += sorted((root / "frontend/public").glob("*.geojson"))
paths += [root / "frontend/src/geography.ts"]
for path in paths:
    if path.is_file():
        print(f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}")
