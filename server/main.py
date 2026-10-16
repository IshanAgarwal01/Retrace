import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from capture import parse_capture
from db import connect, init_db
from sync import sync_assignments

log = logging.getLogger("retrace")

init_db()
app = FastAPI(title="Retrace")

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
    return {"ai_ok": ai_output is not None, "items": saved}


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


app.include_router(api)
