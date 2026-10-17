from datetime import datetime, timedelta, timezone

import main
from helpers import AUTH, FEED, add_assignment, add_item, fake_parse, use_feed

NOTE = {"type": "note", "title": "Thing", "due_at": None, "all_day": False,
        "course": None, "place": None}


def add_context(place, hours_ago):
    at = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    conn = main.connect()
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO contexts (at, place, source) VALUES (?, ?, 'test') RETURNING id",
            (at, place),
        ).fetchone()
    conn.close()
    return row["id"]


def item_context(item_id):
    conn = main.connect()
    row = conn.execute("SELECT context_id FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return row["context_id"]


def test_post_context(client):
    assert client.post("/contexts", json={"place": "Dreese"}).status_code == 401

    body = client.post("/contexts", json={"place": " Dreese Labs "}, headers=AUTH).json()

    assert body["place"] == "Dreese Labs"
    assert client.get("/context/now", headers=AUTH).json()["place"]["place"] == "Dreese Labs"


def test_capture_remembers_a_recent_place_only(client, monkeypatch):
    monkeypatch.setattr(main, "parse_capture", fake_parse([NOTE]))

    add_context("Thompson Library", hours_ago=3)
    stale = client.post("/captures", json={"text": "a"}, headers=AUTH).json()["items"][0]["id"]
    assert item_context(stale) is None  # three hours ago is too long

    recent = add_context("Dreese Labs", hours_ago=1)
    fresh = client.post("/captures", json={"text": "b"}, headers=AUTH).json()["items"][0]["id"]
    assert item_context(fresh) == recent


def test_context_now(client):
    now = datetime.now(timezone.utc)
    add_context("RPAC", hours_ago=0.5)
    add_item("Due tonight", due_at=(now + timedelta(hours=5)).isoformat())
    add_item("Due next week", due_at=(now + timedelta(days=6)).isoformat())
    add_assignment("Quiz 3", (now + timedelta(hours=12)).isoformat())
    for i in range(6):
        add_item(f"Capture {i}", created_at=f"2026-10-0{i + 1}T12:00:00+00:00")

    body = client.get("/context/now", headers=AUTH).json()

    assert body["place"]["place"] == "RPAC"
    assert [e["title"] for e in body["due_soon"]] == ["Due tonight", "Quiz 3"]
    assert len(body["recent_captures"]) == 5
    assert body["recent_captures"][0]["title"] == "Capture 5"


def test_context_now_with_nothing_recorded(client):
    body = client.get("/context/now", headers=AUTH).json()
    assert body == {"place": None, "due_soon": [], "recent_captures": []}


def test_sync_forgets_old_places_unless_a_capture_uses_them(client, monkeypatch):
    old_unused = add_context("Union", hours_ago=24 * 40)
    old_used = add_context("Dreese", hours_ago=24 * 40)
    recent = add_context("RPAC", hours_ago=1)
    add_item("x", context_id=old_used)

    use_feed(monkeypatch, FEED)
    client.post("/sync", headers=AUTH)

    conn = main.connect()
    kept = {row["id"] for row in conn.execute("SELECT id FROM contexts").fetchall()}
    conn.close()
    assert old_unused not in kept
    assert kept == {old_used, recent}
