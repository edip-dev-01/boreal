"""Production-shaped local demo entrypoint: requires the read-only PostgreSQL URL."""
from .api import create_app

app = create_app()
