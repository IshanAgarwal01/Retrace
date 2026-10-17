"""Push notifications through ntfy.sh, a free service with an iPhone app.

The ntfy app subscribes to a topic (a channel name). Anyone who knows the name can
post to it or read it, so NTFY_TOPIC should be long and random, like a password.
POSTing text to https://ntfy.sh/<topic> makes it pop up on the phone.

A notification is never important enough to break the thing that triggered it, so
nothing in here raises: problems are logged and the caller carries on.
"""

import logging
import os
from datetime import datetime, time, timezone

import httpx

from carmen import COLUMBUS

log = logging.getLogger("retrace.notify")

NTFY_SERVER = "https://ntfy.sh"

# At most this many notifications a day, not counting the morning brief, so the
# phone never turns into a slot machine
DAILY_CAP = 5


def send(title: str, message: str, url: str | None = None) -> bool:
    """Push one notification. Returns True if ntfy accepted it."""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log.info("NTFY_TOPIC is not set; skipping notification %r", title)
        return False

    # Header values must be plain ASCII; the message body can be any text
    headers = {"Title": title.encode("ascii", "replace").decode()}
    if url:
        headers["Click"] = url  # tapping the notification opens this
    try:
        response = httpx.post(f"{NTFY_SERVER}/{topic}", content=message.encode(),
                              headers=headers, timeout=5)
        response.raise_for_status()
        return True
    except Exception:
        log.exception("Could not send notification %r", title)
        return False


def start_of_today() -> str:
    """Midnight in Columbus, as UTC ISO text, so it compares with stored times."""
    midnight = datetime.combine(datetime.now(COLUMBUS).date(), time(0), tzinfo=COLUMBUS)
    return midnight.astimezone(timezone.utc).isoformat()


def sent_today(conn, kind: str | None = None) -> int:
    """How many notifications went out today: of one kind, or all but the brief."""
    if kind:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM nudges WHERE kind = ? AND sent_at >= ?",
            (kind, start_of_today()),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM nudges WHERE kind <> 'brief' AND sent_at >= ?",
            (start_of_today(),),
        ).fetchone()
    return row["n"]


def nudge(conn, kind: str, item_ref: str | None, title: str, message: str,
          url: str | None = None) -> bool:
    """Send a notification, respecting the daily cap, and record it in `nudges`.

    kind is a short label such as "brief", "deadline_change" or "ghost"; item_ref
    says what it was about (e.g. "ghost:4"). Returns True if it was sent.
    """
    if kind != "brief" and sent_today(conn) >= DAILY_CAP:
        log.info("Daily notification cap reached; skipping %r", title)
        return False
    if not send(title, message, url):
        return False
    with conn.transaction():
        conn.execute(
            "INSERT INTO nudges (kind, item_ref, message, sent_at) VALUES (?, ?, ?, ?)",
            (kind, item_ref, f"{title}\n{message}", datetime.now(timezone.utc).isoformat()),
        )
    return True


def local_time(iso: str | None, all_day: bool = False) -> str:
    """UTC ISO text -> "Fri Oct 23, 3:00 PM" in Columbus time."""
    if not iso:
        return "no date"
    when = datetime.fromisoformat(iso).astimezone(COLUMBUS)
    day = f"{when:%a %b} {when.day}"
    if all_day:
        return day
    return f"{day}, {when.hour % 12 or 12}:{when:%M %p}"
