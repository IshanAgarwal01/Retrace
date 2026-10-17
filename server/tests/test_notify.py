from datetime import datetime, timedelta, timezone

import httpx

import main
import notify
from brief import build_brief
from helpers import AUTH, FEED, add_assignment, add_item, use_feed


def test_send_skips_quietly_without_topic(monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.send("Hi", "there") is False


def test_send_posts_to_topic(monkeypatch):
    calls = []

    def fake_post(url, content, headers, timeout):
        calls.append((url, content, headers))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setenv("NTFY_TOPIC", "secret-topic")
    monkeypatch.setattr(httpx, "post", fake_post)

    assert notify.send("Title", "Body → text", url="https://example.com") is True
    url, content, headers = calls[0]
    assert url == "https://ntfy.sh/secret-topic"
    assert content == "Body → text".encode()
    assert headers == {"Title": "Title", "Click": "https://example.com"}


def test_send_failure_is_logged_not_raised(monkeypatch):
    def broken_post(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setenv("NTFY_TOPIC", "secret-topic")
    monkeypatch.setattr(httpx, "post", broken_post)
    assert notify.send("Title", "Body") is False


def test_local_time_is_columbus():
    assert notify.local_time("2026-10-23T19:00:00+00:00") == "Fri Oct 23, 3:00 PM"
    assert notify.local_time("2026-10-24T03:59:00+00:00", all_day=True) == "Fri Oct 23"


def test_sync_sends_one_notification_listing_moved_deadlines(client, sent, monkeypatch):
    use_feed(monkeypatch, FEED)
    client.post("/sync", headers=AUTH)
    assert sent == []  # first sync: everything is new, nothing moved

    moved = FEED.replace("20991024T035900Z", "20991027T035900Z").replace(
        "DTSTART;VALUE=DATE:20991206", "DTSTART;VALUE=DATE:20991207")
    use_feed(monkeypatch, moved)
    client.post("/sync", headers=AUTH)

    assert len(sent) == 1
    assert sent[0]["title"] == "2 Carmen deadlines moved"
    assert "Homework #22: Fri Oct 23, 11:59 PM -> Mon Oct 26, 11:59 PM" in sent[0]["message"]

    client.post("/sync", headers=AUTH)  # nothing changed this time
    assert len(sent) == 1


def test_brief_lists_due_soon_overdue_and_undated(client, sent):
    now = datetime.now(timezone.utc)
    soon = (now + timedelta(hours=20)).isoformat()
    add_item("Return library book", due_at=soon)
    add_item("Old task", due_at=(now - timedelta(days=10)).isoformat())
    add_item("Call the bank")
    add_assignment("Homework 9", (now + timedelta(hours=30)).isoformat())
    add_assignment("Next week's homework", (now + timedelta(days=5)).isoformat())

    body = client.post("/brief", headers=AUTH).json()

    assert body["sent"] is True
    assert body["title"] == "Good morning: 2 due soon"
    message = body["message"]
    assert "Return library book" in message and "Homework 9 (CSE 2221)" in message
    assert "Next week's homework" not in message
    assert "1 overdue." in message
    assert "- Call the bank" in message
    assert sent[0]["title"] == body["title"]


def test_brief_on_an_empty_day():
    conn = main.connect()
    title, message = build_brief(conn)
    conn.close()
    assert title == "Good morning"
    assert message == "Nothing due in the next 48 hours."


def test_brief_requires_key(client):
    assert client.post("/brief").status_code == 401


def test_daily_cap_skips_extra_notifications_but_not_the_brief(sent):
    conn = main.connect()
    results = [notify.nudge(conn, "deadline_change", None, f"n{i}", "x") for i in range(7)]
    assert results == [True] * notify.DAILY_CAP + [False, False]
    assert notify.nudge(conn, "brief", None, "Good morning", "x") is True

    rows = conn.execute("SELECT kind FROM nudges").fetchall()
    conn.close()
    assert len(rows) == notify.DAILY_CAP + 1  # every notification sent is recorded
    assert len(sent) == notify.DAILY_CAP + 1


def test_unsent_notifications_are_not_recorded(monkeypatch):
    monkeypatch.setattr(notify, "send", lambda *args, **kwargs: False)
    conn = main.connect()
    assert notify.nudge(conn, "brief", None, "t", "m") is False
    assert conn.execute("SELECT COUNT(*) AS n FROM nudges").fetchone()["n"] == 0
    conn.close()
