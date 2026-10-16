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
        raise ConnectionError("no internet")

    monkeypatch.setattr(main, "parse_capture", broken)

    body = client.post("/captures", json={"text": "call mom"}, headers=AUTH).json()

    assert body["ai_ok"] is False
    assert body["items"][0]["type"] == "note"
    assert body["items"][0]["title"] == "call mom"


def test_capture_without_gemini_key_is_saved_as_note(client, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
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
    with conn.transaction():
        row = conn.execute(
            """INSERT INTO assignments (canvas_uid, course_code, title, due_at, last_seen_at)
               VALUES (?, 'CSE 2221', ?, ?, '2026-10-01T00:00:00+00:00')
               RETURNING id""",
            (f"event-assignment-{title}", title, due_at),
        ).fetchone()
    conn.close()
    return row["id"]


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


def test_init_db_adds_missing_columns():
    import db

    # Pretend this database was created before done_at existed
    conn = db.connect()
    with conn.transaction():
        conn.execute("ALTER TABLE assignments DROP COLUMN done_at")
    assert "done_at" not in db.existing_columns(conn, "assignments")
    conn.close()

    db.init_db()

    conn = db.connect()
    assert "done_at" in db.existing_columns(conn, "assignments")
    conn.close()


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


def fake_gemini(output_text, seen=None):
    class FakeInteraction:
        pass

    class FakeClient:
        class interactions:
            @staticmethod
            def create(**kwargs):
                if seen is not None:
                    seen.update(kwargs)
                reply = FakeInteraction()
                reply.output_text = output_text
                return reply

    return lambda: FakeClient()


def test_parse_capture_reads_gemini_json_and_drops_unknown_courses(monkeypatch):
    seen = {}
    reply = ('{"items": [{"type": "task", "title": "Study", "due_date": "2026-10-23", '
             '"due_time": null, "course": "BIO 1101", "place": null}]}')
    monkeypatch.setattr(capture, "get_client", fake_gemini(reply, seen))

    items, raw = capture.parse_capture("study for bio by friday", ["CSE 2321"])

    assert "CSE 2321" in seen["input"]
    assert seen["response_format"]["schema"] == capture.CAPTURE_SCHEMA
    assert items[0]["course"] is None
    assert items[0]["due_at"] == "2026-10-24T03:59:00+00:00"
    assert '"Study"' in raw


def test_parse_capture_rejects_malformed_reply(monkeypatch):
    monkeypatch.setattr(capture, "get_client", fake_gemini('{"items": [{"title": 5}]}'))
    with pytest.raises(Exception):
        capture.parse_capture("anything", [])
