import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ghosts
import loops
import notify
from brief import build_brief
from capture import parse_capture, summarize
from db import connect, init_db
import retrace
from queries import (LIVE_ASSIGNMENT, assignment_entry, by_due, due_between, item_entry,
                     latest_context, recent_captures)
from sync import sync_assignments

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("retrace")

# The exported web app (npx expo export --platform web). The Dockerfile puts it at
# /app/web; locally it's mobile/dist after you run the export yourself.
WEB_DIR = Path(os.environ.get("RETRACE_WEB_DIR", Path(__file__).resolve().parent.parent / "mobile" / "dist"))

# No timer runs inside the server: free hosting puts idle servers to sleep, which
# would stop it. Instead an outside scheduler (cron-job.org) calls POST /sync hourly.
init_db()
app = FastAPI(title="Retrace")

# Lets the Expo web preview (http://localhost:8081) call this server from a browser.
# The phone app is not a browser, so it doesn't need this.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Depends(api_key_header)) -> None:
    expected = os.environ.get("RETRACE_API_KEY")
    if not expected or not key or not secrets.compare_digest(key, expected):
        raise HTTPException(status_code=401, detail="Missing or wrong API key")


# Every route on this router needs the X-API-Key header
api = APIRouter(dependencies=[Depends(require_api_key)])


class CaptureIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    source: Literal["text", "voice", "share"] = "text"


class ContextIn(BaseModel):
    place: str = Field(min_length=1, max_length=120)
    source: str = Field(default="shortcut", max_length=40)


class RetraceStart(BaseModel):
    ghost_id: int | None = None  # opened from a "lost a thought here" notification


class RetraceEnd(BaseModel):
    outcome: Literal["recovered", "ghost", "gave_up"]
    text: str | None = Field(default=None, max_length=5000)  # the thought, when recovered
    item_id: int | None = None  # or: it was an item already on your list, so nothing new to save
    cue: str | None = Field(default=None, max_length=200)    # e.g. "item:12" or "chip:buy"
    ghost_id: int | None = None  # the ghost this session was chasing, if any


class ItemUpdate(BaseModel):
    status: Literal["open", "done", "archived"]


class AssignmentUpdate(BaseModel):
    done: bool


# How far back unfinished Carmen assignments still show up in the list
OVERDUE_WINDOW = timedelta(days=3)


@app.get("/health")
def health():
    return {"status": "ok"}


@api.get("/assignments")
def list_assignments(course: str | None = None):
    conn = connect()
    try:
        if course:
            rows = conn.execute(
                "SELECT * FROM assignments WHERE course_code = ? ORDER BY due_at",
                (course,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM assignments ORDER BY due_at").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


@api.get("/changes")
def list_changes():
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT assignment_changes.*, assignments.title, assignments.course_code
               FROM assignment_changes
               JOIN assignments ON assignments.id = assignment_changes.assignment_id
               ORDER BY detected_at DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


@api.post("/sync")
def sync():
    """Pull Carmen. cron-job.org calls this every hour."""
    forget_old_contexts()  # first, so it still happens if Carmen is down
    result = sync_assignments()
    log.info("Carmen sync: %s added, %s changes", result["added"], len(result["changes"]))

    # One notification per run, listing every moved deadline
    moved = [c for c in result["changes"] if c["field"] == "due_at"]
    if moved:
        lines = [f"{c['title']}: {notify.local_time(c['old'])} -> {notify.local_time(c['new'])}"
                 for c in moved]
        title = "Carmen deadline moved" if len(moved) == 1 else f"{len(moved)} Carmen deadlines moved"
        conn = connect()
        try:
            notify.nudge(conn, "deadline_change", None, title, "\n".join(lines))
        finally:
            conn.close()
    return result


def forget_old_contexts() -> None:
    cutoff = (datetime.now(timezone.utc) - CONTEXT_KEEP).isoformat()
    conn = connect()
    try:
        with conn.transaction():
            old = """SELECT id FROM contexts
                     WHERE at < ?
                       AND id NOT IN (SELECT context_id FROM items WHERE context_id IS NOT NULL)
                       AND id NOT IN (SELECT context_id FROM ghosts WHERE context_id IS NOT NULL)"""
            # Retrace sessions just forget the place rather than keep it alive
            conn.execute(f"UPDATE retrace_sessions SET context_id = NULL WHERE context_id IN ({old})",
                         (cutoff,))
            conn.execute(f"DELETE FROM contexts WHERE id IN ({old})", (cutoff,))
    finally:
        conn.close()


@api.post("/brief")
def morning_brief():
    """Send the morning brief. cron-job.org calls this daily at 7:30 AM."""
    conn = connect()
    try:
        title, message = build_brief(conn)
        sent = notify.nudge(conn, "brief", None, title, message)
    finally:
        conn.close()
    return {"sent": sent, "title": title, "message": message}


# A capture remembers where you were if the phone reported a place this recently
CONTEXT_FRESHNESS = timedelta(hours=2)
# The loop detector compares a new capture with at most this many open items
LOOP_LOOKBACK = 300
# Places older than this are forgotten, unless a capture or lost thought points at them
CONTEXT_KEEP = timedelta(days=30)


def save_capture(text: str, source: str) -> dict:
    """Sort raw text into items and save them. Shared by POST /captures and Retrace."""
    conn = connect()
    try:
        course_codes = [
            row["course_code"]
            for row in conn.execute(
                "SELECT DISTINCT course_code FROM assignments WHERE course_code IS NOT NULL"
            )
        ]

        try:
            parsed, ai_output = parse_capture(text, course_codes)
        except Exception:
            # Never lose a thought: if the AI step fails for any reason, keep the raw
            # text as a note. The full error still goes to the server log.
            log.exception("AI parsing failed; saving capture as a plain note")
            parsed = [{"type": "note", "title": text[:120], "due_at": None,
                       "all_day": False, "course": None, "place": None}]
            ai_output = None

        now = datetime.now(timezone.utc)
        context = latest_context(conn, since=(now - CONTEXT_FRESHNESS).isoformat())
        context_id = context["id"] if context else None

        # Loop detector: compare against what's still open, before adding the new items
        open_items = conn.execute(
            "SELECT title, embedding FROM items WHERE status = 'open' ORDER BY created_at DESC LIMIT ?",
            (LOOP_LOOKBACK,),
        ).fetchall()
        vectors = loops.embed([item["title"] for item in parsed])
        loop_note = loops.loop_note(parsed, vectors, open_items)

        saved = []
        with conn.transaction():
            for index, item in enumerate(parsed):
                cursor = conn.execute(
                    """INSERT INTO items
                       (type, title, source, due_at, all_day, course, place,
                        raw_text, ai_output, created_at, context_id, embedding)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       RETURNING id""",
                    (item["type"], item["title"], source, item["due_at"],
                     int(item["all_day"]), item["course"], item["place"],
                     text, ai_output, now.isoformat(), context_id,
                     json.dumps(vectors[index]) if vectors else None),
                )
                saved.append({"id": cursor.fetchone()["id"], **item, "status": "open"})
    finally:
        conn.close()
    summary = summarize(parsed) + (f"\n{loop_note}" if loop_note else "")
    return {"ai_ok": ai_output is not None, "summary": summary, "loop": loop_note, "items": saved}


@api.post("/captures", status_code=201)
def create_capture(capture: CaptureIn):
    return save_capture(capture.text, capture.source)


@api.post("/contexts", status_code=201)
def add_context(context: ContextIn):
    """Record where you are. Called by iOS Shortcuts automations ("When I arrive at Dreese")."""
    now = datetime.now(timezone.utc).isoformat()
    conn = connect()
    try:
        with conn.transaction():
            context_id = conn.execute(
                "INSERT INTO contexts (at, place, source) VALUES (?, ?, ?) RETURNING id",
                (now, context.place.strip(), context.source),
            ).fetchone()["id"]
        # Arriving somewhere you once lost a thought may bring it back
        prompted = ghosts.maybe_prompt(conn, context.place.strip())
    finally:
        conn.close()
    return {"id": context_id, "at": now, "place": context.place.strip(), "ghost_prompted": prompted}


def context_now(conn) -> dict:
    """Where you last were, what's due in the next day, and what you captured lately."""
    now = datetime.now(timezone.utc)
    place = latest_context(conn)
    return {
        "place": {"place": place["place"], "at": place["at"]} if place else None,
        "due_soon": due_between(conn, now.isoformat(), (now + timedelta(hours=24)).isoformat()),
        "recent_captures": recent_captures(conn, 5),
    }


@api.get("/context/now")
def get_context_now():
    conn = connect()
    try:
        return context_now(conn)
    finally:
        conn.close()


@api.post("/retrace", status_code=201)
def start_retrace(start: RetraceStart | None = None):
    """Start a lost-thought session: what you were up to, plus ranked guesses."""
    now = datetime.now(timezone.utc)
    conn = connect()
    try:
        strip = context_now(conn)
        here = latest_context(conn, since=(now - CONTEXT_FRESHNESS).isoformat())
        place = here["place"] if here else None

        # Chasing a ghost: rank by where that thought was lost instead of where you are
        ghost = None
        if start and start.ghost_id:
            ghost = conn.execute("SELECT * FROM ghosts WHERE id = ?", (start.ghost_id,)).fetchone()
            if ghost is None:
                raise HTTPException(status_code=404, detail="Ghost not found")
            place = ghost["place"] or place
            strip["ghost"] = {"id": ghost["id"], "place": ghost["place"],
                              "lost_at": ghost["created_at"]}

        guesses = retrace.rank_guesses(conn, now, place)

        phrased_by_ai = False
        top = guesses[:retrace.PHRASED_BY_AI]
        if top:
            try:
                questions = retrace.phrase_questions(top)
                for guess in top:
                    guess["question"] = questions.get(guess["ref"], guess["question"])
                phrased_by_ai = bool(questions)
            except Exception:
                # The template questions are already filled in, so just carry on
                log.warning("Gemini couldn't word the Retrace questions; using templates",
                            exc_info=True)

        with conn.transaction():
            session_id = conn.execute(
                """INSERT INTO retrace_sessions (started_at, context_id, cues_shown)
                   VALUES (?, ?, ?) RETURNING id""",
                (now.isoformat(), here["id"] if here else None, retrace.cues_json(guesses)),
            ).fetchone()["id"]
    finally:
        conn.close()
    return {"id": session_id, "started_at": now.isoformat(), "context": strip,
            "chips": retrace.CHIPS, "guesses": guesses, "phrased_by_ai": phrased_by_ai}


@api.patch("/retrace/{session_id}")
def end_retrace(session_id: int, end: RetraceEnd):
    """Finish a session. "recovered" saves the thought like any other capture."""
    if end.outcome == "recovered" and not end.item_id and not (end.text and end.text.strip()):
        raise HTTPException(status_code=422, detail="A recovered thought needs its text")

    conn = connect()
    try:
        session = conn.execute(
            "SELECT * FROM retrace_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise HTTPException(status_code=404, detail="Retrace session not found")
        if session["outcome"]:
            raise HTTPException(status_code=409, detail="This session already ended")

        ghost = None
        if end.ghost_id:
            ghost = conn.execute("SELECT * FROM ghosts WHERE id = ?", (end.ghost_id,)).fetchone()
            if ghost is None:
                raise HTTPException(status_code=404, detail="Ghost not found")

        captured = None
        recovered_item_id = None
        if end.outcome == "recovered" and end.item_id:
            if not conn.execute("SELECT id FROM items WHERE id = ?", (end.item_id,)).fetchone():
                raise HTTPException(status_code=404, detail="Item not found")
            recovered_item_id = end.item_id
        elif end.outcome == "recovered":
            captured = save_capture(end.text.strip(), "recovered")
            recovered_item_id = captured["items"][0]["id"]
        now = datetime.now(timezone.utc)
        seconds = int((now - datetime.fromisoformat(session["started_at"])).total_seconds())

        with conn.transaction():
            conn.execute(
                """UPDATE retrace_sessions
                   SET outcome = ?, cue_that_worked = ?, recovered_item_id = ?, seconds_taken = ?
                   WHERE id = ?""",
                (end.outcome, end.cue, recovered_item_id, seconds, session_id),
            )
            if ghost and recovered_item_id:
                conn.execute("UPDATE ghosts SET resolved_item_id = ? WHERE id = ?",
                             (recovered_item_id, ghost["id"]))
            # Still gone: leave a ghost, unless this was already chasing one
            if end.outcome == "ghost" and not ghost:
                ghosts.create_ghost(conn, session)
    finally:
        conn.close()
    return {"id": session_id, "outcome": end.outcome, "seconds_taken": seconds,
            "recovered_item_id": recovered_item_id, "capture": captured}


@api.get("/items")
def list_items(status: Literal["open", "done", "archived"] = "open"):
    conn = connect()
    try:
        rows = conn.execute(
            """SELECT * FROM items WHERE status = ?
               ORDER BY due_at IS NULL, due_at, created_at DESC""",
            (status,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


@api.patch("/items/{item_id}")
def update_item(item_id: int, update: ItemUpdate):
    done_at = datetime.now(timezone.utc).isoformat() if update.status == "done" else None
    conn = connect()
    try:
        with conn.transaction():
            cursor = conn.execute(
                "UPDATE items SET status = ?, done_at = ? WHERE id = ?",
                (update.status, done_at, item_id),
            )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
        row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()
    return dict(row)


@api.patch("/assignments/{assignment_id}")
def update_assignment(assignment_id: int, update: AssignmentUpdate):
    done_at = datetime.now(timezone.utc).isoformat() if update.done else None
    conn = connect()
    try:
        with conn.transaction():
            cursor = conn.execute(
                "UPDATE assignments SET done_at = ? WHERE id = ?", (done_at, assignment_id)
            )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Assignment not found")
        row = conn.execute("SELECT * FROM assignments WHERE id = ?", (assignment_id,)).fetchone()
    finally:
        conn.close()
    return dict(row)


@api.get("/list")
def one_list():
    """Open captures and unfinished Carmen assignments, merged into one list.

    Grouping into Today / This week / Later happens on the phone, which knows
    the local time zone.
    """
    since = (datetime.now(timezone.utc) - OVERDUE_WINDOW).isoformat()
    conn = connect()
    try:
        items = conn.execute(
            """SELECT id, type, title, course, due_at, all_day, place
               FROM items WHERE status = 'open'"""
        ).fetchall()
        assignments = conn.execute(
            f"""SELECT id, title, course_code, due_at, all_day, url
                FROM assignments
                WHERE {LIVE_ASSIGNMENT} AND due_at >= ?""",
            (since,),
        ).fetchall()
    finally:
        conn.close()

    return by_due([item_entry(row) for row in items] + [assignment_entry(row) for row in assignments])


app.include_router(api)

# Serve the app itself at "/". Mounted last so every API route above wins first.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
