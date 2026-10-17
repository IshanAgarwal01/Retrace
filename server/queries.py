"""Reads that several features share: the one list, the morning brief, the context
screen and Retrace all need "what's due between these two times"."""

# Every sync stamps the assignments it saw with the same last_seen_at, so rows missing
# from the latest sync are ones a professor deleted from Carmen. Unfinished and still
# in Carmen = worth showing.
LIVE_ASSIGNMENT = "done_at IS NULL AND last_seen_at = (SELECT MAX(last_seen_at) FROM assignments)"


def item_entry(row: dict) -> dict:
    return {"kind": "item", "id": row["id"], "type": row["type"], "title": row["title"],
            "course": row["course"], "due_at": row["due_at"], "all_day": bool(row["all_day"]),
            "place": row["place"], "url": None}


def assignment_entry(row: dict) -> dict:
    return {"kind": "assignment", "id": row["id"], "type": "assignment", "title": row["title"],
            "course": row["course_code"], "due_at": row["due_at"], "all_day": bool(row["all_day"]),
            "place": None, "url": row["url"]}


def by_due(entries: list[dict]) -> list[dict]:
    """Soonest first, undated last."""
    return sorted(entries, key=lambda e: (e["due_at"] is None, e["due_at"] or ""))


def due_between(conn, start: str, end: str) -> list[dict]:
    """Open items and live Carmen assignments due in [start, end), soonest first."""
    items = conn.execute(
        """SELECT * FROM items
           WHERE status = 'open' AND due_at >= ? AND due_at < ?""",
        (start, end),
    ).fetchall()
    assignments = conn.execute(
        f"""SELECT * FROM assignments
            WHERE {LIVE_ASSIGNMENT} AND due_at >= ? AND due_at < ?""",
        (start, end),
    ).fetchall()
    return by_due([item_entry(r) for r in items] + [assignment_entry(r) for r in assignments])



def recent_captures(conn, limit: int) -> list[dict]:
    """The newest captures, whatever their status (archived ones aside)."""
    rows = conn.execute(
        """SELECT id, type, title, status, created_at FROM items
           WHERE status <> 'archived'
           ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def latest_context(conn, since: str | None = None) -> dict | None:
    """The most recent place the phone reported, optionally only if newer than `since`."""
    if since:
        return conn.execute(
            "SELECT * FROM contexts WHERE at >= ? ORDER BY at DESC, id DESC LIMIT 1", (since,)
        ).fetchone()
    return conn.execute("SELECT * FROM contexts ORDER BY at DESC, id DESC LIMIT 1").fetchone()
