from datetime import datetime, timezone

from carmen import FEED_URL, download_feed, parse_events
from db import connect, init_db

# The fields where a change is worth telling you about
TRACKED_FIELDS = ("title", "due_at")


def sync_assignments() -> dict:
    events = parse_events(download_feed(FEED_URL))
    assignments = [e for e in events if e["is_assignment"]]
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    changes = []

    conn = connect()
    try:
        with conn.transaction():  # either everything saves, or nothing does
            for a in assignments:
                row = conn.execute(
                    "SELECT * FROM assignments WHERE canvas_uid = ?", (a["uid"],)
                ).fetchone()

                if row is None:
                    conn.execute(
                        """INSERT INTO assignments
                           (canvas_uid, course, course_code, title, due_at, all_day, url, last_seen_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (a["uid"], a["course"], a["course_code"], a["title"],
                         a["due_at"], int(a["all_day"]), a["url"], now),
                    )
                    added += 1
                    continue

                for field in TRACKED_FIELDS:
                    if row[field] != a[field]:
                        conn.execute(
                            """INSERT INTO assignment_changes
                               (assignment_id, field, old_value, new_value, detected_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            (row["id"], field, row[field], a[field], now),
                        )
                        changes.append({"title": a["title"], "field": field,
                                        "old": row[field], "new": a[field]})

                conn.execute(
                    """UPDATE assignments
                       SET course = ?, course_code = ?, title = ?, due_at = ?,
                           all_day = ?, url = ?, last_seen_at = ?
                       WHERE id = ?""",
                    (a["course"], a["course_code"], a["title"], a["due_at"],
                     int(a["all_day"]), a["url"], now, row["id"]),
                )
    finally:
        conn.close()

    return {"fetched": len(assignments), "added": added, "changes": changes}


if __name__ == "__main__":
    init_db()
    print(sync_assignments())