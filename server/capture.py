import os
import re
from datetime import date, datetime, time, timedelta
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


def local_due(due_date: str, due_time: str | None) -> tuple[str, bool]:
    """Columbus-time "YYYY-MM-DD" (+ optional "HH:MM") -> (UTC ISO text, all_day).

    Raises ValueError for anything that isn't a real date or time.
    """
    day = date.fromisoformat(due_date)
    if due_time:
        return normalize_due(datetime.combine(day, time.fromisoformat(due_time), tzinfo=COLUMBUS))
    return normalize_due(day)


def to_due(item: ParsedItem) -> tuple[str | None, bool]:
    """Turn the model's local date/time strings into (UTC ISO text, all_day)."""
    if not item.due_date:
        return None, False
    try:
        return local_due(item.due_date, item.due_time)
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


# Things that need a deadline. When one comes back without a date, the app asks for one.
DATED_TYPES = {"task", "reminder"}

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
SLASH_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$")

DUE_SCHEMA = {
    "type": "object",
    "properties": {
        "due_date": {**NULLABLE_STRING, "description": "YYYY-MM-DD, Columbus time"},
        "due_time": {**NULLABLE_STRING, "description": "HH:MM, 24-hour"},
    },
    "required": ["due_date", "due_time"],
}

DUE_SYSTEM = """The student was asked when something is due and typed the answer below. Return the date (and time of day, if they gave one) it describes, resolving relative words against the current date given. A named weekday means its next occurrence after today. If the text doesn't describe a date, return null for both."""


class ParsedDue(BaseModel):
    due_date: str | None
    due_time: str | None


def quick_due(text: str, today: date) -> date | None:
    """Understand the common answers without calling the AI: today, tomorrow, a weekday, 10/24."""
    words = text.strip().lower().removeprefix("on ").removeprefix("this ").strip(" .!")
    if words in ("today", "tonight"):
        return today
    if words in ("tomorrow", "tmrw", "tmr"):
        return today + timedelta(days=1)
    if words in WEEKDAYS:
        # Next occurrence after today, matching what the capture prompt tells Gemini
        days_ahead = (WEEKDAYS.index(words) - today.weekday()) % 7 or 7
        return today + timedelta(days=days_ahead)
    match = SLASH_DATE.match(words)
    if match:
        month, day, year = int(match[1]), int(match[2]), match[3]
        if year:
            year = int(year) + (2000 if len(year) == 2 else 0)
            return date(year, month, day)
        guess = date(today.year, month, day)
        # "1/15" typed in October means next January
        return guess if guess >= today else date(today.year + 1, month, day)
    return None


def parse_due_text(text: str) -> tuple[str, bool]:
    """Turn an answer like "friday" or "next tuesday at 3pm" into (UTC ISO text, all_day).

    Raises ValueError or CaptureError when no date can be found in it.
    """
    now = datetime.now(COLUMBUS)
    day = quick_due(text, now.date())
    if day:
        return normalize_due(day)

    interaction = get_client().interactions.create(
        model=MODEL,
        system_instruction=DUE_SYSTEM,
        input=f"Current date and time: {now:%A, %B %d, %Y, %I:%M %p} (Columbus, Ohio)\n\nAnswer:\n{text}",
        response_format={"type": "text", "mime_type": "application/json", "schema": DUE_SCHEMA},
        generation_config={"thinking_level": "low"},
    )
    parsed = ParsedDue.model_validate_json(interaction.output_text or "")
    if not parsed.due_date:
        raise CaptureError("No date in that answer")
    return local_due(parsed.due_date, parsed.due_time)


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
