import os
import re
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv()
FEED_URL = os.environ["CARMEN_FEED_URL"]
COLUMBUS = ZoneInfo("America/New_York")

# Canvas titles look like "Homework 5 [CSE 2221 AU2026 (4829)]"
TITLE_AND_COURSE = re.compile(r"^(.*)\s\[(.+)\]$")


def download_feed(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    return response.content


def normalize_due(value) -> tuple[str | None, bool]:
    """Return (due time as UTC ISO text, whether it was an all-day date)."""
    if value is None:
        return None, False
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=COLUMBUS)
        return value.astimezone(timezone.utc).isoformat(), False
    # A date with no time means "due that day": treat it as 11:59 PM in Columbus
    end_of_day = datetime.combine(value, time(23, 59), tzinfo=COLUMBUS)
    return end_of_day.astimezone(timezone.utc).isoformat(), True


def parse_events(feed: bytes) -> list[dict]:
    calendar = Calendar.from_ical(feed)
    events = []
    for event in calendar.walk("VEVENT"):
        uid = str(event.get("UID", ""))
        summary = str(event.get("SUMMARY", ""))

        match = TITLE_AND_COURSE.match(summary)
        if match:
            title, course = match.groups()
            course_code = " ".join(course.split()[:2])
        else:
            title, course, course_code = summary, None, None

        start = event.get("DTSTART")
        due_at, all_day = normalize_due(start.dt if start else None)
        events.append({
            "uid": uid,
            "title": title,
            "course": course,
            "course_code": course_code,
            "due_at": due_at,
            "all_day": all_day,
            "url": str(event.get("URL", "")) or None,
            "is_assignment": uid.startswith("event-assignment-"),
        })
    return events


def main():
    feed = download_feed(FEED_URL)
    events = parse_events(feed)
    events.sort(key=lambda e: e["due_at"] or "")

    print(f"Found {len(events)} events\n")
    for e in events:
        kind = "ASSIGNMENT" if e["is_assignment"] else "event"
        course = e["course_code"] or "-"
        print(f"{e['due_at'] or '-':<27} {kind:<11} {course:<14} {e['title']}")


if __name__ == "__main__":
    main()