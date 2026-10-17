from datetime import date

import pytest
from fastapi.testclient import TestClient

import capture
import main
from capture import quick_due
from helpers import AUTH, fake_parse


@pytest.fixture
def client():
    return TestClient(main.app)


def capture_one(client, monkeypatch, item_type, due_at=None):
    item = {"type": item_type, "title": "Finish homework", "due_at": due_at, "all_day": False,
            "course": None, "place": None}
    monkeypatch.setattr(main, "parse_capture", fake_parse([item]))
    return client.post("/captures", json={"text": "finish homework"}, headers=AUTH).json()


def test_task_without_date_is_flagged(client, monkeypatch):
    body = capture_one(client, monkeypatch, "task")
    assert body["needs_date"] == [body["items"][0]["id"]]


@pytest.mark.parametrize("item_type,due_at", [
    ("task", "2099-01-01T04:59:00+00:00"),  # already has a date
    ("idea", None),                          # ideas don't need deadlines
])
def test_items_that_dont_need_a_date(client, monkeypatch, item_type, due_at):
    assert capture_one(client, monkeypatch, item_type, due_at)["needs_date"] == []


def test_ai_fallback_notes_are_not_flagged(client, monkeypatch):
    def broken(text, codes):
        raise ConnectionError("offline")

    monkeypatch.setattr(main, "parse_capture", broken)
    body = client.post("/captures", json={"text": "finish homework"}, headers=AUTH).json()
    assert body["needs_date"] == []


def test_set_due_from_picked_date(client, monkeypatch):
    item_id = capture_one(client, monkeypatch, "task")["items"][0]["id"]

    body = client.post(f"/items/{item_id}/due", json={"date": "2026-10-23"}, headers=AUTH).json()

    # All-day dates mean 11:59 PM in Columbus
    assert body["item"]["due_at"] == "2026-10-24T03:59:00+00:00"
    assert body["item"]["all_day"] == 1
    assert "due Fri Oct 23" in body["summary"]
    assert client.get("/list", headers=AUTH).json()[0]["due_at"] == "2026-10-24T03:59:00+00:00"


def test_set_due_with_time(client, monkeypatch):
    item_id = capture_one(client, monkeypatch, "task")["items"][0]["id"]
    body = client.post(f"/items/{item_id}/due", json={"date": "2026-10-23", "time": "15:00"},
                       headers=AUTH).json()
    assert body["item"]["due_at"] == "2026-10-23T19:00:00+00:00"
    assert "at 3:00 PM" in body["summary"]


def test_set_due_from_text_uses_quick_rules_without_ai(client, monkeypatch):
    item_id = capture_one(client, monkeypatch, "task")["items"][0]["id"]
    monkeypatch.setattr(capture, "get_client", lambda: pytest.fail("AI should not be needed"))

    response = client.post(f"/items/{item_id}/due", json={"text": "tomorrow"}, headers=AUTH)

    assert response.status_code == 200
    assert response.json()["item"]["all_day"] == 1


def test_set_due_from_text_asks_gemini_for_harder_answers(client, monkeypatch):
    from test_api import fake_gemini

    item_id = capture_one(client, monkeypatch, "task")["items"][0]["id"]
    seen = {}
    monkeypatch.setattr(capture, "get_client",
                        fake_gemini('{"due_date": "2026-10-27", "due_time": "15:00"}', seen))

    body = client.post(f"/items/{item_id}/due", json={"text": "next tuesday at 3pm"}, headers=AUTH).json()

    assert "next tuesday at 3pm" in seen["input"]
    assert body["item"]["due_at"] == "2026-10-27T19:00:00+00:00"


@pytest.mark.parametrize("payload", [{}, {"text": "  "}, {"date": "not-a-date"}, {"date": "2026-02-30"}])
def test_set_due_rejects_bad_input(client, monkeypatch, payload):
    item_id = capture_one(client, monkeypatch, "task")["items"][0]["id"]
    assert client.post(f"/items/{item_id}/due", json=payload, headers=AUTH).status_code == 422


def test_set_due_when_no_date_in_text(client, monkeypatch):
    from test_api import fake_gemini

    item_id = capture_one(client, monkeypatch, "task")["items"][0]["id"]
    monkeypatch.setattr(capture, "get_client", fake_gemini('{"due_date": null, "due_time": null}'))

    response = client.post(f"/items/{item_id}/due", json={"text": "whenever"}, headers=AUTH)

    assert response.status_code == 422
    assert "Couldn't find a date" in response.json()["detail"]


def test_set_due_unknown_item(client):
    assert client.post("/items/999/due", json={"date": "2026-10-23"}, headers=AUTH).status_code == 404


SATURDAY = date(2026, 10, 17)


@pytest.mark.parametrize("text,expected", [
    ("today", date(2026, 10, 17)),
    ("Tonight", date(2026, 10, 17)),
    ("tomorrow", date(2026, 10, 18)),
    ("friday", date(2026, 10, 23)),
    ("this Friday", date(2026, 10, 23)),
    ("on monday", date(2026, 10, 19)),
    ("saturday", date(2026, 10, 24)),  # a weekday means the next one, not today
    ("10/24", date(2026, 10, 24)),
    ("1/15", date(2027, 1, 15)),       # already passed this year, so next year
    ("12/1/26", date(2026, 12, 1)),
    ("next tuesday at 3pm", None),     # left for Gemini
    ("whenever", None),
])
def test_quick_due(text, expected):
    assert quick_due(text, SATURDAY) == expected
