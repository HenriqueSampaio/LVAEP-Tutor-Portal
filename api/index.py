"""Vercel serverless function: every request to the site is routed here (see vercel.json).

Vercel imports this file and serves the WSGI callable named `app`. The real application lives in
the `app/` package at the repository root, so put that on the import path first.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("LVAEP_SERVERLESS", "1")

from app.wsgi import app  # noqa: E402,F401
