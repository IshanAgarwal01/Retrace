"""Small helpers shared by the test files."""

import main

AUTH = {"X-API-Key": "test-key"}


def fake_parse(items):
    """Stands in for the Gemini call: always "parses" the text into these items."""
    return lambda text, course_codes: (items, '{"items": "..."}')


def add_assignment(title, due_at, last_seen_at="2026-10-01T00:00:00+00:00"):
    conn = main.connect()
    with conn.transaction():
        row = conn.execute(
            """INSERT INTO assignments (canvas_uid, course_code, title, due_at, last_seen_at)
               VALUES (?, 'CSE 2221', ?, ?, ?)
               RETURNING id""",
            (f"event-assignment-{title}", title, due_at, last_seen_at),
        ).fetchone()
    conn.close()
    return row["id"]


def add_item(title, due_at=None, created_at="2026-10-01T00:00:00+00:00", type="task",
             status="open", place=None, context_id=None):
    """Insert an item directly, skipping the capture route and its AI step."""
    conn = main.connect()
    with conn.transaction():
        row = conn.execute(
            """INSERT INTO items
               (type, title, source, status, due_at, place, raw_text, created_at, context_id)
               VALUES (?, ?, 'text', ?, ?, ?, ?, ?, ?)
               RETURNING id""",
            (type, title, status, due_at, place, title, created_at, context_id),
        ).fetchone()
    conn.close()
    return row["id"]


# A tiny Carmen feed: two assignments and one non-assignment event
FEED = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:test
BEGIN:VEVENT
UID:event-assignment-1
DTSTART:20991024T035900Z
SUMMARY:Homework #22 [CSE 2221 AU2026 (4829)]
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-2
DTSTART;VALUE=DATE:20991206
SUMMARY:Post-Course Survey [GENED 1201 AU2026 (30163)]
END:VEVENT
BEGIN:VEVENT
UID:event-calendar-event-9
DTSTART:20991020T180000Z
SUMMARY:Office Hours
END:VEVENT
END:VCALENDAR
"""


def use_feed(monkeypatch, text):
    """Make the next sync read `text` instead of downloading the real Carmen feed."""
    import sync

    monkeypatch.setattr(sync, "download_feed", lambda url: text.replace("\n", "\r\n").encode())
