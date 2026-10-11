#!/usr/bin/env python3
"""Bounded public-source hygiene check; not a comprehensive secret scanner."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "node_modules", "dist", ".venv", "__pycache__", ".pytest_cache", "test-results", "playwright-report"}
RULES = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub credential", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b")),
    ("cloud access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("OpenAI credential", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
]


def main() -> int:
    problems: list[str] = []
    checked = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.name.startswith(".env") and path.name != ".env.example":
            continue  # local setup files are explicitly ignored, not publication candidates
        if path.suffix in {".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2", ".zip", ".gz"}:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        checked += 1
        for label, pattern in RULES:
            if pattern.search(content):
                problems.append(f"{path.relative_to(ROOT)}: possible {label}")
    ignore = (ROOT / ".gitignore").read_text()
    if ".env\n" not in ignore:
        problems.append(".env is not explicitly ignored")
    compose = (ROOT / "compose.yaml").read_text()
    if '"127.0.0.1:${BOREAL_PORT:-8080}:8080"' not in compose:
        problems.append("Compose does not retain expected loopback-only web binding")
    if problems:
        print("\n".join(problems))
        return 1
    print(f"PASS: {checked} source files checked for a bounded set of credential signatures; .env ignored; loopback binding present.")
    print("This does not replace a real secret scan or a human review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
