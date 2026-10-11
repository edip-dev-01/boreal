#!/usr/bin/env python3
"""Create local demo credentials without printing or overwriting them."""
from pathlib import Path
import os
import secrets


def main() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    values = [
        "# Generated local demo credentials. Do not commit or reuse elsewhere.",
        *(f"{name}={secrets.token_hex(32)}" for name in (
            "DB_ADMIN_PASSWORD", "DB_APP_PASSWORD", "DB_INGEST_PASSWORD"
        )),
        "BOREAL_PORT=8080",
        "AS_OF=2026-10-11T12:00:00Z",
        "",
    ]
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit(".env already exists; leaving it unchanged.") from None
    with os.fdopen(fd, "w") as handle:
        handle.write("\n".join(values))
    print("Created .env with unique local credentials and owner-only permissions.")


if __name__ == "__main__":
    main()
