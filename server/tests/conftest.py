import os
import sys
from pathlib import Path

# Set test values before any app module loads .env (load_dotenv never overrides these)
os.environ["CARMEN_FEED_URL"] = "https://example.invalid/feed.ics"
os.environ["RETRACE_API_KEY"] = "test-key"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
