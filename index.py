"""Vercel entrypoint: exposes the FastAPI ASGI app.

Vercel's Python runtime detects the `app` object in this root module.
Local / VM deployments keep using `run.py` (uvicorn).
"""

from app.main import app  # noqa: F401
