"""Keep the test suite off whatever database this machine is pointed at.

Every test module builds its own throwaway SQLite file, but two of them do it
with `os.environ.setdefault`, which only works if `DATABASE_URL` is unset when
the fixture runs. It is not, in two situations:

  * `test_matching.py` imports `app.matching` at module scope, and importing
    `app` reads `backend/.env` — so by the time any other module's fixture
    runs, `DATABASE_URL` is whatever `.env` names. On this checkout that is
    Neon, and `setdefault` would quietly hand the suite the live workspace:
    `create_all`, seeded users and dispatch cycles, straight into real data.

  * Anyone running `DATABASE_URL=… pytest` to check something by hand.

Importing `app` here first, then clearing the variable, makes the order
deterministic: pytest loads conftest before it collects a single test module,
the `.env` has already been read and discarded, and each fixture falls through
to its own temp file exactly as it was written to.
"""
import os

import app  # noqa: F401  — imported for the side effect of reading .env

os.environ.pop("DATABASE_URL", None)
