import anthropic
import pytest
from fastapi.testclient import TestClient

import capture
import main
from capture import ParsedItem, to_due

AUTH = {"X-API-Key": "test-key"}


@pytest.fixture
def client():
    return TestClient(main.app)


def fake_parse(items):
    return lambda text, course_codes: (items, '{"items": "..."}')


def test_health_needs_no_key(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_routes_reject_missing_or_wrong_key(client, headers):
    assert client.get("/items", headers=headers).status_code == 401


def test_capture_saves_items(client, monkeypatch):
    item = {"type": "task", "title": "Finish 2321 homework", "due_at": "2026-10-24T03:59:00+00:00",
            "all_day": True, "course": "CSE 2321", "place": None}
    monkeypatch.setattr(main, "parse_capture", fake_parse([item]))

    response = client.post("/captures", json={"text": "finish 2321 homework by friday"}, headers=AUTH)

    assert response.status_code == 201
    body = response.json()
    assert body["ai_ok"] is True
    assert body["items"][0]["title"] == "Finish 2321 homework"

    items = client.get("/items", headers=AUTH).json()
    assert len(items) == 1
    assert items[0]["raw_text"] == "finish 2321 homework by friday"
    assert items[0]["course"] == "CSE 2321"


def test_capture_falls_back_to_note_when_ai_fails(client, monkeypatch):
    def broken(text, course_codes):
        raise anthropic.APIConnectionError(request=None)

    monkeypatch.setattr(main, "parse_capture", broken)

    body = client.post("/captures", json={"text": "call mom"}, headers=AUTH).json()

    assert body["ai_ok"] is False
    assert body["items"][0]["type"] == "note"
    assert body["items"][0]["title"] == "call mom"


def test_capture_without_anthropic_key_is_saved_as_note(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    capture.get_client.cache_clear()

    body = client.post("/captures", json={"text": "buy printer paper"}, headers=AUTH).json()

    assert body["ai_ok"] is False
    assert body["items"][0]["title"] == "buy printer paper"


def test_mark_done_and_archive(client, monkeypatch):
    item = {"type": "idea", "title": "App idea", "due_at": None, "all_day": False,
            "course": None, "place": None}
    monkeypatch.setattr(main, "parse_capture", fake_parse([item]))
    item_id = client.post("/captures", json={"text": "app idea"}, headers=AUTH).json()["items"][0]["id"]

    done = client.patch(f"/items/{item_id}", json={"status": "done"}, headers=AUTH).json()
    assert done["status"] == "done" and done["done_at"]
    assert client.get("/items", headers=AUTH).json() == []
    assert len(client.get("/items?status=done", headers=AUTH).json()) == 1

    assert client.patch("/items/999", json={"status": "done"}, headers=AUTH).status_code == 404


def add_assignment(title, due_at):
    conn = main.connect()
    with conn:
        cursor = conn.execute(
            """INSERT INTO assignments (canvas_uid, course_code, title, due_at, last_seen_at)
               VALUES (?, 'CSE 2221', ?, ?, '2026-10-01T00:00:00+00:00')""",
            (f"event-assignment-{title}", title, due_at),
        )
    conn.close()
    return cursor.lastrowid


def test_one_list_merges_items_and_assignments(client, monkeypatch):
    item = {"type": "task", "title": "Buy paper", "due_at": None, "all_day": False,
            "course": None, "place": None}
    monkeypatch.setattr(main, "parse_capture", fake_parse([item]))
    client.post("/captures", json={"text": "buy paper"}, headers=AUTH)
    add_assignment("Homework 1", "2099-01-01T04:59:00+00:00")
    add_assignment("Ancient homework", "2000-01-01T04:59:00+00:00")

    entries = client.get("/list", headers=AUTH).json()

    # Dated entries first, undated last; long-past assignments are left out
    assert [(e["kind"], e["title"]) for e in entries] == [
        ("assignment", "Homework 1"),
        ("item", "Buy paper"),
    ]


def test_marking_assignment_done_hides_it(client):
    assignment_id = add_assignment("Homework 2", "2099-01-01T04:59:00+00:00")

    response = client.patch(f"/assignments/{assignment_id}", json={"done": True}, headers=AUTH)

    assert response.json()["done_at"]
    assert client.get("/list", headers=AUTH).json() == []
    client.patch(f"/assignments/{assignment_id}", json={"done": False}, headers=AUTH)
    assert len(client.get("/list", headers=AUTH).json()) == 1


def test_init_db_adds_missing_columns(tmp_path, monkeypatch):
    import sqlite3

    import db

    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE assignments (id INTEGER PRIMARY KEY, canvas_uid TEXT, "
                 "course TEXT, course_code TEXT, title TEXT, due_at TEXT, all_day INTEGER, "
                 "url TEXT, last_seen_at TEXT)")
    conn.close()
    monkeypatch.setattr(db, "DB_PATH", old)

    db.init_db()

    conn = sqlite3.connect(old)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(assignments)")]
    conn.close()
    assert "done_at" in columns


def test_capture_returns_readable_summary(client, monkeypatch):
    items = [
        {"type": "task", "title": "Finish 2321 homework", "due_at": "2026-10-24T03:59:00+00:00",
         "all_day": True, "course": "CSE 2321", "place": None},
        {"type": "reminder", "title": "Call mom", "due_at": "2026-10-23T19:00:00+00:00",
         "all_day": False, "course": None, "place": None},
    ]
    monkeypatch.setattr(main, "parse_capture", fake_parse(items))

    body = client.post("/captures", json={"text": "..."}, headers=AUTH).json()

    assert body["summary"] == (
        "Task: Finish 2321 homework (CSE 2321), due Fri Oct 23\n"
        "Reminder: Call mom, due Fri Oct 23 at 3:00 PM"
    )


def test_empty_capture_is_rejected(client):
    assert client.post("/captures", json={"text": ""}, headers=AUTH).status_code == 422


def parsed(due_date, due_time=None):
    return ParsedItem(type="task", title="x", due_date=due_date, due_time=due_time,
                      course=None, place=None)


def test_to_due_date_only_is_end_of_day_columbus():
    # 11:59 PM EDT on Oct 23 is 03:59 UTC on Oct 24
    assert to_due(parsed("2026-10-23")) == ("2026-10-24T03:59:00+00:00", True)


def test_to_due_with_time():
    assert to_due(parsed("2026-10-23", "15:00")) == ("2026-10-23T19:00:00+00:00", False)


def test_to_due_handles_missing_and_bad_values():
    assert to_due(parsed(None)) == (None, False)
    assert to_due(parsed("next friday")) == (None, False)


def test_parse_capture_drops_unknown_courses(monkeypatch):
    class FakeResponse:
        stop_reason = "end_turn"
        parsed_output = capture.ParsedCapture(items=[
            ParsedItem(type="task", title="Study", due_date=None, due_time=None,
                       course="BIO 1101", place=None),
        ])

    class FakeClient:
        class beta:
            class messages:
                @staticmethod
                def parse(**kwargs):
                    assert "CSE 2321" in kwargs["messages"][0]["content"]
                    return FakeResponse()

    monkeypatch.setattr(capture, "get_client", lambda: FakeClient())
    items, raw = capture.parse_capture("study for bio", ["CSE 2321"])
    assert items[0]["course"] is None
    assert '"Study"' in raw
