"""Ghosts: thoughts that stayed lost.

When Retrace can't bring a thought back ("Still gone"), it leaves a ghost: a note
of where and when you lost it. Thoughts tend to come back in the same setting, so
when you're next at that place, or it's the same time of day, Retrace sends one
gentle prompt: "Last Tuesday at Dreese you lost a thought. Anything come back?"
"""

import os
from datetime import datetime, timedelta, timezone

import notify
from carmen import COLUMBUS
from retrace import same_place

LIFETIME = timedelta(days=14)  # after two weeks, let it go
PROMPTS_PER_DAY = 1


def create_ghost(conn, session: dict) -> int:
    """Leave a ghost for a Retrace session that ended "Still gone"."""
    started = datetime.fromisoformat(session["started_at"])
    place = None
    if session["context_id"]:
        context = conn.execute(
            "SELECT place FROM contexts WHERE id = ?", (session["context_id"],)
        ).fetchone()
        place = context["place"] if context else None
    now = datetime.now(timezone.utc)
    return conn.execute(
        """INSERT INTO ghosts
           (retrace_session_id, context_id, place, hour, created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
        (session["id"], session["context_id"], place, started.astimezone(COLUMBUS).hour,
         now.isoformat(), (now + LIFETIME).isoformat()),
    ).fetchone()["id"]


def when_lost(created: datetime, now: datetime) -> str:
    """"Yesterday", "Last Tuesday" or "On Tue Oct 6", in Columbus time."""
    days = (now.astimezone(COLUMBUS).date() - created.astimezone(COLUMBUS).date()).days
    if days <= 0:
        return "Earlier today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return f"Last {created.astimezone(COLUMBUS):%A}"
    local = created.astimezone(COLUMBUS)
    return f"On {local:%a %b} {local.day}"


def prompt_text(ghost: dict, now: datetime) -> str:
    created = datetime.fromisoformat(ghost["created_at"])
    if ghost["place"]:
        where = f" at {ghost['place']}"
    else:
        hour = ghost["hour"]
        where = f" around {hour % 12 or 12} {'AM' if hour < 12 else 'PM'}"
    return f"{when_lost(created, now)}{where} you lost a thought. Anything come back?"


def matching_ghost(conn, place: str, now: datetime) -> dict | None:
    """The newest open ghost lost at this place, or at about this hour of day.

    Only ghosts from before today count: a prompt an hour after giving up would be
    nagging, not a cue.
    """
    ghosts = conn.execute(
        """SELECT * FROM ghosts
           WHERE resolved_item_id IS NULL AND prompted_at IS NULL
             AND expires_at > ? AND created_at < ?
           ORDER BY created_at DESC""",
        (now.isoformat(), notify.start_of_today()),
    ).fetchall()
    hour_now = now.astimezone(COLUMBUS).hour
    for ghost in ghosts:
        hours_off = abs(ghost["hour"] - hour_now)
        if same_place(ghost["place"], place) or min(hours_off, 24 - hours_off) <= 1:
            return ghost
    return None


def maybe_prompt(conn, place: str) -> int | None:
    """Called when you arrive somewhere. Returns the id of the ghost prompted, if any."""
    if notify.sent_today(conn, "ghost") >= PROMPTS_PER_DAY:
        return None
    now = datetime.now(timezone.utc)
    ghost = matching_ghost(conn, place, now)
    if ghost is None:
        return None

    # On Render, tapping the notification opens the app straight into Retrace
    base = os.environ.get("RENDER_EXTERNAL_URL")
    url = f"{base}/?ghost={ghost['id']}" if base else None
    if not notify.nudge(conn, "ghost", f"ghost:{ghost['id']}", "Retrace",
                        prompt_text(ghost, now), url):
        return None
    with conn.transaction():
        conn.execute("UPDATE ghosts SET prompted_at = ? WHERE id = ?", (now.isoformat(), ghost["id"]))
    return ghost["id"]
