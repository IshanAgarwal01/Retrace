import os
import re

import httpx
from dotenv import load_dotenv
from icalendar import Calendar

load_dotenv()
FEED_URL = os.environ["CARMEN_FEED_URL"]

# Canvas titles look like "Homework 5 [CSE 2221 (AU26)]"
TITLE_AND_COURSE = re.compile(r"^(.*)\s\[(.+)\]$")


def download_feed(url: str) -> bytes:
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()
    return response.content


def parse_events(feed: bytes) -> list[dict]:
    calendar = Calendar.from_ical(feed)
    events = []
    for event in calendar.walk("VEVENT"):
        uid = str(event.get("UID", ""))
        summary = str(event.get("SUMMARY", ""))

        match = TITLE_AND_COURSE.match(summary)
        if match:
            title, course = match.groups()
        else:
            title, course = summary, None

        start = event.get("DTSTART")
        events.append({
            "uid": uid,
            "title": title,
            "course": course,
            "due": start.dt if start else None,
            "url": str(event.get("URL", "")) or None,
            "is_assignment": uid.startswith("event-assignment-"),
        })
    return events


def main():
    feed = download_feed(FEED_URL)
    events = parse_events(feed)
    events.sort(key=lambda e: str(e["due"]))

    print(f"Found {len(events)} events\n")
    for e in events:
        kind = "ASSIGNMENT" if e["is_assignment"] else "event"
        course = e["course"] or "-"
        print(f"{str(e['due']):<27} {kind:<11} {course:<22} {e['title']}")


if __name__ == "__main__":
    main()