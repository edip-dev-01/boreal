"""Explicit test/visual-smoke server only; never used by Docker Compose.

Run: uvicorn app.testing:app --host 127.0.0.1
"""
import os
from pathlib import Path

os.environ.setdefault("DEMO_ALLOWED_ORIGINS", "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173")
from .fixtures import load_fixtures
from .api import create_app
from .repository import MemoryRepository

app = create_app(MemoryRepository(load_fixtures(Path(__file__).parent.parent / "fixtures")), testing=True)
