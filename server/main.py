import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from capture import parse_capture, summarize
from db import connect, init_db
from sync import sync_assignments

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("retrace")

SYNC_EVERY = timedelta(hours=1)

# The exported web app (npx expo export --platform web). The Dockerfile puts it at
# /app/web; locally it's mobile/dist after you run the export yourself.
WEB_DIR = Path(os.environ.get("RETRACE_WEB_DIR", Path(__file__).resolve().parent.parent / "mobile" / "dist"))


async def sync_forever() -> None:
    while True:
        try:
            # sync_assignments is ordinary blocking code, so run it on a worker thread
            # instead of freezing the server while Carmen downloads
            result = await asyncio.to_thread(sync_assignments)
            log.info("Carmen sync: %s added, %s changes", result["added"], len(result["changes"]))
        except Exception:
            log.exception("Scheduled Carmen sync failed")
        await asyncio.sleep(SYNC_EVERY.total_seconds())


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the server starts (before the yield) and once when it stops
    task = asyncio.create_task(sync_forever())
    yield
    task.cancel()


init_db()
app = FastAPI(title="Retrace", lifespan=lifespan)

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
    return sync_assignments()


@api.post("/captures", status_code=201)
def create_capture(capture: CaptureIn):
    conn = connect()
    try:
        course_codes = [
            row["course_code"]
            for row in conn.execute(
                "SELECT DISTINCT course_code FROM assignments WHERE course_code IS NOT NULL"
            )
        ]

        try:
            parsed, ai_output = parse_capture(capture.text, course_codes)
        except Exception:
            # Never lose a thought: if the AI step fails for any reason, keep the raw
            # text as a note. The full error still goes to the server log.
            log.exception("AI parsing failed; saving capture as a plain note")
            parsed = [{"type": "note", "title": capture.text[:120], "due_at": None,
                       "all_day": False, "course": None, "place": None}]
            ai_output = None

        now = datetime.now(timezone.utc).isoformat()
        saved = []
        with conn:
            for item in parsed:
                cursor = conn.execute(
                    """INSERT INTO items
                       (type, title, source, due_at, all_day, course, place,
                        raw_text, ai_output, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (item["type"], item["title"], capture.source, item["due_at"],
                     item["all_day"], item["course"], item["place"],
                     capture.text, ai_output, now),
                )
                saved.append({"id": cursor.lastrowid, **item, "status": "open"})
    finally:
        conn.close()
    return {"ai_ok": ai_output is not None, "summary": summarize(parsed), "items": saved}


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
        with conn:
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
        with conn:
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
            """SELECT id, title, course_code, due_at, all_day, url
               FROM assignments
               WHERE done_at IS NULL AND due_at >= ?""",
            (since,),
        ).fetchall()
    finally:
        conn.close()

    entries = [
        {"kind": "item", "id": row["id"], "type": row["type"], "title": row["title"],
         "course": row["course"], "due_at": row["due_at"], "all_day": bool(row["all_day"]),
         "place": row["place"], "url": None}
        for row in items
    ] + [
        {"kind": "assignment", "id": row["id"], "type": "assignment", "title": row["title"],
         "course": row["course_code"], "due_at": row["due_at"], "all_day": bool(row["all_day"]),
         "place": None, "url": row["url"]}
        for row in assignments
    ]
    entries.sort(key=lambda e: (e["due_at"] is None, e["due_at"] or ""))
    return entries


app.include_router(api)

# Serve the app itself at "/". Mounted last so every API route above wins first.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
