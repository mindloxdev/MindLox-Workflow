"""Read backend/.env before anything else in the package looks at the
environment.

The README has always said to copy `.env.example` to `.env` and edit it, but
nothing loaded the file, so `DATABASE_URL` and `JWT_SECRET` were only ever read
from real environment variables. A `.env` naming a hosted Postgres was silently
ignored and the app quietly carried on against the local SQLite file — the
worst kind of wrong, because it starts up perfectly and serves the wrong data.

This runs on `import app`, which is before `app.main` and `app.models` are
imported and therefore before either reads a variable at module level.

Real environment variables win. That is what keeps `DATABASE_URL=… pytest` and
a hosted deployment (Render, Docker, Fly) working: those set the variable in the
environment, and a `.env` left in the image must not override it.
"""
from __future__ import annotations

import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_env(path: Path) -> None:
    """Minimal `.env` reader: KEY=value, `#` comments, optional quotes.

    Deliberately not python-dotenv. This is a handful of lines against a
    dependency, and the file it reads is one the team writes by hand.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # Already set in the real environment: leave it alone.
        if key and key not in os.environ:
            os.environ[key] = value


_load_env(_ENV_FILE)
