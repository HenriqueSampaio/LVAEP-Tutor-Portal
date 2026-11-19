"""WSGI entry point: the same app as `python3 server.py`, for hosts that run WSGI applications
(Vercel's Python runtime, gunicorn, mod_wsgi, ...). Nothing runs in the background here: on such
hosts the daily job at /api/cron/daily runs the reminder schedule and sends queued email.

    from app.wsgi import app
"""
from http import HTTPStatus

from . import server


def application(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO") or "/"
    query = environ.get("QUERY_STRING") or ""
    raw_path = f"{path}?{query}" if query else path
    headers = {k[5:].replace("_", "-"): v for k, v in environ.items() if k.startswith("HTTP_")}
    for key, name in (("CONTENT_TYPE", "Content-Type"), ("CONTENT_LENGTH", "Content-Length")):
        if environ.get(key):
            headers[name] = environ[key]
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    body = environ["wsgi.input"].read(length) if length > 0 else b""

    server.ensure_initialized()
    resp = server.handle(method, raw_path, server.Headers(headers.items()), body)
    try:
        phrase = HTTPStatus(resp.status).phrase
    except ValueError:
        phrase = ""
    start_response(f"{resp.status} {phrase}".strip(), resp.headers)
    return [resp.body]


app = application
