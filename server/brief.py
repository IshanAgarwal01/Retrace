"""The morning brief: one notification at 7:30 AM with what the day holds.

Nothing in the server runs on a timer (free hosting sleeps), so cron-job.org calls
POST /brief every morning and that route calls build_brief() below.
"""

from datetime import datetime, timedelta, timezone

from notify import local_time
from queries import LIVE_ASSIGNMENT, due_between

LOOKAHEAD = timedelta(hours=48)
# Same window as the one list: older unfinished assignments are no longer shown
OVERDUE_WINDOW = timedelta(days=3)
UNDATED_SHOWN = 3


def build_brief(conn, now: datetime | None = None) -> tuple[str, str]:
    """Return (title, message) for this morning's notification."""
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()

    due = due_between(conn, now_iso, (now + LOOKAHEAD).isoformat())

    overdue_items = conn.execute(
        "SELECT COUNT(*) AS n FROM items WHERE status = 'open' AND due_at < ?", (now_iso,)
    ).fetchone()["n"]
    overdue_assignments = conn.execute(
        f"""SELECT COUNT(*) AS n FROM assignments
            WHERE {LIVE_ASSIGNMENT} AND due_at < ? AND due_at >= ?""",
        (now_iso, (now - OVERDUE_WINDOW).isoformat()),
    ).fetchone()["n"]
    overdue = overdue_items + overdue_assignments

    undated = conn.execute(
        """SELECT title FROM items WHERE status = 'open' AND due_at IS NULL
           ORDER BY created_at DESC LIMIT ?""",
        (UNDATED_SHOWN,),
    ).fetchall()

    lines = []
    if due:
        lines.append("Due in the next 48 hours:")
        for entry in due:
            course = f" ({entry['course']})" if entry["course"] else ""
            lines.append(f"- {entry['title']}{course}, {local_time(entry['due_at'], entry['all_day'])}")
    else:
        lines.append("Nothing due in the next 48 hours.")
    if overdue:
        lines.append(f"{overdue} overdue.")
    if undated:
        lines.append("Still open:")
        lines.extend(f"- {row['title']}" for row in undated)

    title = f"Good morning: {len(due)} due soon" if due else "Good morning"
    return title, "\n".join(lines)
