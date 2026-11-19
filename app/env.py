"""Load settings from a .env file (KEY=value lines) into the environment.

Variables already set in the environment win, so hosting platforms can override the file.
Import and call load() before importing app.db, which reads DATABASE_URL at import time.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path=None):
    path = path or os.path.join(ROOT, ".env")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip().removeprefix("export ").strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            os.environ.setdefault(key, value)
    return True
