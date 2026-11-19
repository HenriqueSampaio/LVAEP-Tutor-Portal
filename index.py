"""Vercel entrypoint. Vercel's Python preset finds this file at the project root, imports the WSGI
callable named `app` and routes every request that isn't a file in public/ to it (see vercel.json).

The application itself lives in the `app/` package; this file must not be called app.py, because
that module name would shadow the package.
"""
import os

os.environ.setdefault("LVAEP_SERVERLESS", "1")

from app.wsgi import app  # noqa: E402,F401
