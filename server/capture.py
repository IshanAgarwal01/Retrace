import os
from datetime import date, datetime, time
from functools import cache
from typing import Literal

from google import genai
from pydantic import BaseModel

from carmen import COLUMBUS, normalize_due

# A Gemini model on the free tier (ai.google.dev/gemini-api/docs/pricing)
MODEL = "gemini-3.8-flash"

ITEM_TYPES = ["task", "reminder", "idea", "song", "note", "question"]
NULLABLE_STRING = {"type": ["string", "null"]}

# JSON Schema the model's reply must follow. Written out by hand (instead of
# ParsedCapture.model_json_schema()) so it has no $ref links for the API to resolve.
CAPTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ITEM_TYPES},
                    "title": {"type": "string"},
                    "due_date": {**NULLABLE_STRING, "description": "YYYY-MM-DD, Columbus time"},
                    "due_time": {**NULLABLE_STRING, "description": "HH:MM, 24-hour"},
                    "course": NULLABLE_STRING,
                    "place": NULLABLE_STRING,
                },
                "required": ["type", "title", "due_date", "due_time", "course", "place"],
            },
        },
    },
    "required": ["items"],
}

SYSTEM = """You sort quick thoughts captured by a college student at Ohio State into structured items.

Split the text into one item per separate thought; a single thought is one item. Titles use the student's own words, cleaned up into a short phrase with no trailing period.

type: task = something to do; reminder = something to remember at a particular time; idea; song = music to save; note = information to keep; question = something to find out.

due_date and due_time: fill these only when the text states or clearly implies a deadline or time ("by Friday", "tomorrow at 3"). Resolve relative dates against the current date given with the text. A named weekday means its next occurrence after today. Leave due_time empty when no time of day is given.

course: if the thought is about one of the student's courses, give that course's code exactly as listed. A bare course number like "2321" refers to the listed course with that number. Otherwise leave it empty.

place: a specific named place mentioned in the text (for example "Thompson Library"), otherwise empty."""


class ParsedItem(BaseModel):
    type: Literal["task", "reminder", "idea", "song", "note", "question"]
    title: str
    due_date: str | None  # "YYYY-MM-DD", Columbus time
    due_time: str | None  # "HH:MM", 24-hour
    course: str | None
    place: str | None


class ParsedCapture(BaseModel):
    items: list[ParsedItem]


class CaptureError(Exception):
    pass


@cache
def get_client() -> genai.Client:
    # Created on first use, so the server still starts without GEMINI_API_KEY set
    if not os.environ.get("GEMINI_API_KEY"):
        raise CaptureError("GEMINI_API_KEY is not set")
    return genai.Client()  # reads GEMINI_API_KEY from the environment


def to_due(item: ParsedItem) -> tuple[str | None, bool]:
    """Turn the model's local date/time strings into (UTC ISO text, all_day)."""
    if not item.due_date:
        return None, False
    try:
        day = date.fromisoformat(item.due_date)
        if item.due_time:
            when = datetime.combine(day, time.fromisoformat(item.due_time), tzinfo=COLUMBUS)
            return normalize_due(when)
        return normalize_due(day)
    except ValueError:
        return None, False


def parse_capture(text: str, course_codes: list[str]) -> tuple[list[dict], str]:
    """Ask Gemini to turn raw text into items. Returns (items, raw JSON it sent back)."""
    now = datetime.now(COLUMBUS)
    prompt = (
        f"Current date and time: {now:%A, %B %d, %Y, %I:%M %p} (Columbus, Ohio)\n"
        f"Courses: {', '.join(course_codes) or 'none known'}\n\n"
        f"Captured text:\n{text}"
    )
    interaction = get_client().interactions.create(
        model=MODEL,
        system_instruction=SYSTEM,
        input=prompt,
        response_format={"type": "text", "mime_type": "application/json", "schema": CAPTURE_SCHEMA},
        generation_config={"thinking_level": "low"},
    )
    if not interaction.output_text:
        raise CaptureError("Gemini returned no text")
    # Validate it ourselves too: the schema shapes the reply, Pydantic double-checks it
    capture = ParsedCapture.model_validate_json(interaction.output_text)

    items = []
    for parsed in capture.items:
        due_at, all_day = to_due(parsed)
        items.append({
            "type": parsed.type,
            "title": parsed.title,
            "due_at": due_at,
            "all_day": all_day,
            "course": parsed.course if parsed.course in course_codes else None,
            "place": parsed.place,
        })
    if not items:
        raise CaptureError("Gemini returned an empty list")
    return items, capture.model_dump_json()


TYPE_LABELS = {"task": "Task", "reminder": "Reminder", "idea": "Idea", "song": "Song",
               "note": "Note", "question": "Question"}


def summarize(items: list[dict]) -> str:
    """One readable line per item, e.g. for Siri to show after a voice capture."""
    lines = []
    for item in items:
        line = f"{TYPE_LABELS.get(item['type'], item['type'])}: {item['title']}"
        if item["course"]:
            line += f" ({item['course']})"
        if item["due_at"]:
            due = datetime.fromisoformat(item["due_at"]).astimezone(COLUMBUS)
            line += f", due {due:%a %b} {due.day}"
            if not item["all_day"]:
                line += f" at {due.hour % 12 or 12}:{due:%M %p}"
        lines.append(line)
    return "\n".join(lines)
