import os
import sys
from pathlib import Path

# Set test values before any app module loads .env (load_dotenv never overrides these)
os.environ["CARMEN_FEED_URL"] = "https://example.invalid/feed.ics"
os.environ["RETRACE_API_KEY"] = "test-key"
os.environ["GEMINI_API_KEY"] = ""
# Tests must never touch your real database. They use a throwaway SQLite file, or a
# Postgres database you name explicitly in TEST_DATABASE_URL (it gets wiped).
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    if os.environ["DATABASE_URL"]:
        conn = db.connect()
        with conn.transaction():
            conn.execute("DROP TABLE IF EXISTS assignment_changes, assignments, items")
        conn.close()
    db.init_db()
