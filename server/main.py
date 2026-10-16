from fastapi import FastAPI

from db import connect, init_db
from sync import sync_assignments

init_db()
app = FastAPI(title="Retrace")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/assignments")
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


@app.get("/changes")
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


@app.post("/sync")
def sync():
    return sync_assignments()