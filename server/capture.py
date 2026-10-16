import os
from datetime import date, datetime, time
from functools import cache
from typing import Literal

import anthropic
from pydantic import BaseModel

from carmen import COLUMBUS, normalize_due

MODEL = "claude-opus-5-5"

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
def get_client() -> anthropic.Anthropic:
    # Created on first use, so the server still starts without ANTHROPIC_API_KEY set
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise CaptureError("ANTHROPIC_API_KEY is not set in .env")
    return anthropic.Anthropic()


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
    """Ask Claude to turn raw text into items. Returns (items, raw JSON it sent back)."""
    now = datetime.now(COLUMBUS)
    prompt = (
        f"Current date and time: {now:%A, %B %d, %Y, %I:%M %p} (Columbus, Ohio)\n"
        f"Courses: {', '.join(course_codes) or 'none known'}\n\n"
        f"Captured text:\n{text}"
    )
    response = get_client().beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_format=ParsedCapture,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal" or response.parsed_output is None:
        raise CaptureError(f"Claude returned no items (stop_reason={response.stop_reason})")

    items = []
    for parsed in response.parsed_output.items:
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
        raise CaptureError("Claude returned an empty list")
    return items, response.parsed_output.model_dump_json()


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
