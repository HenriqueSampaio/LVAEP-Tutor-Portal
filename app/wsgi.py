"""WSGI entry point: the same app as `python3 server.py`, for hosts that run WSGI applications
(Vercel's Python runtime, gunicorn, mod_wsgi, ...). Nothing runs in the background here: on such
hosts the daily job at /api/cron/daily runs the reminder schedule and sends queued email.

    from app.wsgi import app
"""
import html
import json
import traceback
from http import HTTPStatus

from . import db, server


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

    try:
        if path.startswith("/api/") or path.startswith("/export/") or path == "/print":
            server.ensure_initialized()  # static files never need the database
        resp = server.handle(method, raw_path, server.Headers(headers.items()), body)
    except Exception as exc:  # say what happened instead of the host's generic error page
        traceback.print_exc()
        down = db.is_connection_error(exc)
        status = 503 if down else 500
        message = ("The site's database isn't reachable right now. Please try again in a minute." if down
                   else "Something went wrong on the server.")
        extra = {"Retry-After": "60"} if down else None
        if path.startswith("/print") or path.startswith("/export"):  # these open in a browser tab
            resp = server.Response(status, f"<p style='font-family:sans-serif'>{html.escape(message)} "
                                           "<a href='/'>Back to the app</a></p>", "text/html; charset=utf-8", extra)
        else:
            resp = server.Response(status, json.dumps({"error": message}), headers=extra)
    try:
        phrase = HTTPStatus(resp.status).phrase
    except ValueError:
        phrase = ""
    start_response(f"{resp.status} {phrase}".strip(), resp.headers)
    return [resp.body]


app = application
