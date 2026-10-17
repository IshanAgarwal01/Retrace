"""Retrace: help you recover a thought you lost before writing it down.

Lost thoughts usually come back from a cue: something you were just doing, a
deadline hanging over you, the place you're in. So Retrace gathers things that
might be connected to the lost thought, ranks them with the plain scoring below
(no AI involved), and shows the best ones as "Was it...?" questions. Gemini is
only used, when available, to word those questions more naturally.
"""

import json
import re
from datetime import datetime, timedelta

from pydantic import BaseModel

from capture import MODEL, get_client
from carmen import COLUMBUS
from queries import LIVE_ASSIGNMENT

# How much each kind of evidence counts. Each signal is a number from 0 to 1, then
# multiplied by its weight, and the guess's score is the sum.
#   recency  3  captured in the last 3 days (1 = just now, fading to 0 at 3 days):
#               what you were thinking about lately is the strongest cue
#   due_soon 2  due in the next 7 days (1 = due now or overdue, 0 = a week out):
#               looming deadlines are what minds wander back to
#   place    2  captured at the place you are now (1 or 0): memory is tied to places
#   hour     1  captured at about this hour of day, within 1 hour (1 or 0): habits
#               repeat daily, but this is the weakest hint, so it only breaks ties
WEIGHTS = {"recency": 3.0, "due_soon": 2.0, "place": 2.0, "hour": 1.0}

RECENT_WINDOW = timedelta(days=3)
DUE_WINDOW = timedelta(days=7)
MAX_GUESSES = 10   # sent to the phone, which re-sorts them when you tap a type chip
PHRASED_BY_AI = 5  # how many of the top guesses Gemini words

# The type chips on the Retrace screen, and which guesses each one points to
CHIPS = ["task", "buy", "tell someone", "idea", "song", "worry", "class thing"]
CHIP_WORDS = {
    "buy": {"buy", "get", "grab", "order", "pick", "purchase", "groceries", "store"},
    "tell someone": {"tell", "text", "call", "email", "ask", "message", "reply", "remind", "invite"},
    "worry": {"worry", "worried", "anxious", "nervous", "stress", "stressed", "afraid", "scared"},
}


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def chips_for(candidate: dict) -> list[str]:
    title_words = words(candidate["title"])
    chips = []
    if candidate["type"] in ("task", "reminder"):
        chips.append("task")
    for chip in ("buy", "tell someone"):
        if title_words & CHIP_WORDS[chip]:
            chips.append(chip)
    if candidate["type"] in ("idea", "song"):
        chips.append(candidate["type"])
    if title_words & CHIP_WORDS["worry"]:
        chips.append("worry")
    if candidate["kind"] == "assignment" or candidate["course"]:
        chips.append("class thing")
    return chips


def same_place(a: str | None, b: str | None) -> bool:
    return bool(a and b and a.strip().lower() == b.strip().lower())


def hours_apart(a: datetime, b: datetime) -> int:
    """Distance between two times of day in whole hours, wrapping at midnight."""
    diff = abs(a.astimezone(COLUMBUS).hour - b.astimezone(COLUMBUS).hour)
    return min(diff, 24 - diff)


def signals(candidate: dict, now: datetime, place: str | None) -> dict:
    """Each piece of evidence for one candidate, from 0 to 1."""
    result = {"recency": 0.0, "due_soon": 0.0, "place": 0.0, "hour": 0.0}

    if candidate["created_at"]:
        created = datetime.fromisoformat(candidate["created_at"])
        age = now - created
        if age < RECENT_WINDOW:
            result["recency"] = 1 - age / RECENT_WINDOW
        if hours_apart(created, now) <= 1:
            result["hour"] = 1.0

    if candidate["due_at"]:
        until = datetime.fromisoformat(candidate["due_at"]) - now
        if until < timedelta(0):
            result["due_soon"] = 1.0  # overdue: very much on your mind
        elif until < DUE_WINDOW:
            result["due_soon"] = 1 - until / DUE_WINDOW

    if same_place(candidate["place"], place):
        result["place"] = 1.0
    return result


def load_candidates(conn, now: datetime) -> list[dict]:
    """Open items, captures from the last 3 days, and assignments due within a week."""
    items = conn.execute(
        """SELECT items.*, contexts.place AS context_place
           FROM items LEFT JOIN contexts ON contexts.id = items.context_id
           WHERE items.status = 'open'
              OR (items.status = 'done' AND items.created_at >= ?)""",
        ((now - RECENT_WINDOW).isoformat(),),
    ).fetchall()
    assignments = conn.execute(
        f"""SELECT * FROM assignments
            WHERE {LIVE_ASSIGNMENT} AND due_at >= ? AND due_at < ?""",
        (now.isoformat(), (now + DUE_WINDOW).isoformat()),
    ).fetchall()

    return [
        {"ref": f"item:{row['id']}", "kind": "item", "id": row["id"], "type": row["type"],
         "title": row["title"], "course": row["course"], "due_at": row["due_at"],
         # Where you were when you captured it, or a place named in the text itself
         "place": row["context_place"] or row["place"], "created_at": row["created_at"]}
        for row in items
    ] + [
        {"ref": f"assignment:{row['id']}", "kind": "assignment", "id": row["id"],
         "type": "assignment", "title": row["title"], "course": row["course_code"],
         "due_at": row["due_at"], "place": None, "created_at": None}
        for row in assignments
    ]


def rank_guesses(conn, now: datetime, place: str | None) -> list[dict]:
    """The best candidates, highest score first, each with its matching chips."""
    guesses = []
    for candidate in load_candidates(conn, now):
        evidence = signals(candidate, now, place)
        score = sum(WEIGHTS[name] * value for name, value in evidence.items())
        guesses.append({**candidate, "score": round(score, 3), "chips": chips_for(candidate),
                        "question": template_question(candidate)})
    guesses.sort(key=lambda g: (-g["score"], -created_timestamp(g)))  # ties: newer first
    return guesses[:MAX_GUESSES]


def created_timestamp(guess: dict) -> float:
    return datetime.fromisoformat(guess["created_at"]).timestamp() if guess["created_at"] else 0


def template_question(candidate: dict) -> str:
    """The question wording used when Gemini isn't available."""
    title = candidate["title"]
    if candidate["kind"] == "assignment":
        course = f" for {candidate['course']}" if candidate["course"] else ""
        return f'Was it about "{title}"{course}?'
    if candidate["type"] == "song":
        return f'Was it a song, like "{title}"?'
    if candidate["type"] == "idea":
        return f'Was it an idea about "{title}"?'
    return f'Was it about "{title}"?'


# The reply Gemini must send, written out by hand like CAPTURE_SCHEMA in capture.py
QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string"},
                    "question": {"type": "string"},
                },
                "required": ["ref", "question"],
            },
        },
    },
    "required": ["questions"],
}

SYSTEM = """A college student lost a thought before writing it down. You help them get it back.

You get a list of things that might be connected to the lost thought, each with a ref. For each one, write one short, friendly yes/no question starting with "Was it", under 12 words, that might jog their memory (for example "Was it something about the CSE 2221 homework?"). Don't invent details that aren't given. Return every ref exactly as given."""


class Question(BaseModel):
    ref: str
    question: str


class Questions(BaseModel):
    questions: list[Question]


def phrase_questions(guesses: list[dict]) -> dict[str, str]:
    """Ask Gemini to word questions for these guesses. Returns {ref: question}.

    Raises on any problem; the caller then keeps the template questions.
    """
    lines = []
    for g in guesses:
        detail = ", ".join(filter(None, [g["type"], g["course"]]))
        lines.append(f"{g['ref']}: {g['title']} ({detail})")
    interaction = get_client().interactions.create(
        model=MODEL,
        system_instruction=SYSTEM,
        input="\n".join(lines),
        response_format={"type": "text", "mime_type": "application/json", "schema": QUESTIONS_SCHEMA},
        generation_config={"thinking_level": "low"},
    )
    reply = Questions.model_validate_json(interaction.output_text or "")
    wanted = {g["ref"] for g in guesses}
    # Ignore anything the model made up, and keep only sensible-looking questions
    return {q.ref: q.question.strip() for q in reply.questions
            if q.ref in wanted and 0 < len(q.question.strip()) <= 140}


def cues_json(guesses: list[dict]) -> str:
    """What the session showed, saved so we can later learn which cues work."""
    return json.dumps([g["ref"] for g in guesses])
