"""Keep the test suite off the live database.

`app.config` reads `database_url` from the environment and `app.database`
builds its engine at import time, so a test that opens
`with TestClient(app)` runs the real startup lifespan — including
`_reset_stale_jobs()`, which marks every RUNNING job FAILED and pushes its
`downloading` rows back to `pending`. Against the default
`./data/igdownloader.db` that silently kills whatever the actual backend is
downloading; it took a live 10-account Instagram batch this way.

Pointing the URL at a throwaway file per test session costs nothing because
the tests that need tables build their own engines.
"""
from __future__ import annotations

import os
import tempfile

_TEST_DB = os.path.join(tempfile.mkdtemp(prefix="igdownloader-tests-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.replace(os.sep, '/')}"

from sqlalchemy import create_engine  # noqa: E402

import app.models  # noqa: E402,F401  — registers every table on Base.metadata
from app.database import Base  # noqa: E402

_sync = create_engine(f"sqlite:///{_TEST_DB.replace(os.sep, '/')}")
Base.metadata.create_all(_sync)
_sync.dispose()
