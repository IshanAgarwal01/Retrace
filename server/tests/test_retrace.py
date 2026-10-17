import json
from datetime import datetime, timedelta, timezone

import pytest

import main
import retrace
from helpers import AUTH, add_assignment, add_item, fake_parse
from test_context import add_context

NOW = datetime(2026, 10, 20, 18, 0, tzinfo=timezone.utc)  # Tue 2 PM in Columbus


def ago(**kwargs):
    return (NOW - timedelta(**kwargs)).isoformat()


def ahead(**kwargs):
    return (NOW + timedelta(**kwargs)).isoformat()


def candidate(**fields):
    base = {"kind": "item", "type": "task", "title": "x", "course": None, "due_at": None,
            "place": None, "created_at": None}
    return {**base, **fields}


def test_signals_follow_the_documented_rules():
    s = retrace.signals(candidate(created_at=ago(hours=36), due_at=ahead(days=3, hours=12),
                                  place="Dreese"), NOW, "dreese ")
    assert s == {"recency": 0.5, "due_soon": 0.5, "place": 1.0, "hour": 0.0}  # 36h ago: 2 AM

    two_days_ago_an_hour_earlier = retrace.signals(candidate(created_at=ago(days=2, hours=1)), NOW, None)
    assert two_days_ago_an_hour_earlier["hour"] == 1.0

    old = retrace.signals(candidate(created_at=ago(days=5, hours=4), due_at=ago(hours=1)), NOW, None)
    assert old == {"recency": 0.0, "due_soon": 1.0, "place": 0.0, "hour": 0.0}


def test_hour_of_day_wraps_around_midnight():
    late = datetime(2026, 10, 20, 3, 30, tzinfo=timezone.utc)   # 11:30 PM Columbus
    early = datetime(2026, 10, 20, 4, 10, tzinfo=timezone.utc)  # 12:10 AM Columbus
    assert retrace.hours_apart(late, early) == 1


def test_chips():
    assert retrace.chips_for(candidate(title="Buy printer paper")) == ["task", "buy"]
    assert retrace.chips_for(candidate(type="note", title="Text Sam about Friday")) == ["tell someone"]
    assert retrace.chips_for(candidate(kind="assignment", type="assignment", title="HW 3",
                                       course="CSE 2221")) == ["class thing"]
    assert retrace.chips_for(candidate(type="question", title="Worried about the midterm")) == ["worry"]


def test_ranking_prefers_recent_due_soon_and_same_place():
    conn = main.connect()
    dreese = add_context("Dreese", hours_ago=0)
    add_item("Old open idea", type="idea", created_at=ago(days=20, hours=5))
    add_item("Captured yesterday", created_at=ago(days=1, hours=5))
    add_item("Captured at Dreese", created_at=ago(days=1, hours=5), context_id=dreese)
    add_item("Done last week", status="done", created_at=ago(days=6))
    add_item("Archived", status="archived", created_at=ago(hours=1))
    add_assignment("Lab due tomorrow", ahead(days=1))
    add_assignment("Lab due next month", ahead(days=30))

    guesses = retrace.rank_guesses(conn, NOW, "Dreese")
    conn.close()

    titles = [g["title"] for g in guesses]
    assert titles == ["Captured at Dreese", "Captured yesterday", "Lab due tomorrow", "Old open idea"]
    assert guesses[0]["ref"].startswith("item:")
    assert guesses[2]["question"] == 'Was it about "Lab due tomorrow" for CSE 2221?'


def test_start_retrace_without_gemini_uses_templates(client):
    add_context("Thompson Library", hours_ago=0.2)
    item_id = add_item("Email advisor", created_at=datetime.now(timezone.utc).isoformat())

    response = client.post("/retrace", headers=AUTH)

    assert response.status_code == 201
    body = response.json()
    assert body["phrased_by_ai"] is False
    assert body["context"]["place"]["place"] == "Thompson Library"
    assert body["context"]["recent_captures"][0]["title"] == "Email advisor"
    assert "class thing" in body["chips"]
    guess = body["guesses"][0]
    assert (guess["ref"], guess["question"]) == (f"item:{item_id}", 'Was it about "Email advisor"?')
    assert guess["chips"] == ["task", "tell someone"]

    conn = main.connect()
    session = conn.execute("SELECT * FROM retrace_sessions WHERE id = ?", (body["id"],)).fetchone()
    conn.close()
    assert json.loads(session["cues_shown"]) == [f"item:{item_id}"]
    assert session["context_id"] is not None and session["outcome"] is None


def test_start_retrace_uses_gemini_wording(client, monkeypatch):
    item_id = add_item("Email advisor", created_at=datetime.now(timezone.utc).isoformat())
    seen = {}

    def fake_phrase(guesses):
        seen["refs"] = [g["ref"] for g in guesses]
        return {f"item:{item_id}": "Was it that email to your advisor?"}

    monkeypatch.setattr(retrace, "phrase_questions", fake_phrase)
    body = client.post("/retrace", headers=AUTH).json()

    assert seen["refs"] == [f"item:{item_id}"]
    assert body["phrased_by_ai"] is True
    assert body["guesses"][0]["question"] == "Was it that email to your advisor?"


def test_phrase_questions_ignores_made_up_refs(monkeypatch):
    from test_api import fake_gemini

    reply = json.dumps({"questions": [{"ref": "item:1", "question": "Was it the email?"},
                                      {"ref": "item:999", "question": "Was it invented?"}]})
    seen = {}
    monkeypatch.setattr(retrace, "get_client", fake_gemini(reply, seen))

    questions = retrace.phrase_questions([{"ref": "item:1", "title": "Email advisor",
                                           "type": "task", "course": None}])

    assert questions == {"item:1": "Was it the email?"}
    assert seen["response_format"]["schema"] == retrace.QUESTIONS_SCHEMA
    assert "item:1: Email advisor (task)" in seen["input"]


def test_recovered_thought_becomes_a_capture(client, monkeypatch):
    parsed = {"type": "task", "title": "Return the HDMI cable", "due_at": None, "all_day": False,
              "course": None, "place": None}
    monkeypatch.setattr(main, "parse_capture", fake_parse([parsed]))
    session_id = client.post("/retrace", headers=AUTH).json()["id"]

    response = client.patch(f"/retrace/{session_id}", headers=AUTH,
                            json={"outcome": "recovered", "text": "return the hdmi cable", "cue": "chip:task"})

    body = response.json()
    assert body["outcome"] == "recovered"
    assert body["capture"]["summary"] == "Task: Return the HDMI cable"
    item = client.get("/items", headers=AUTH).json()[0]
    assert (item["source"], item["raw_text"]) == ("recovered", "return the hdmi cable")

    conn = main.connect()
    session = conn.execute("SELECT * FROM retrace_sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    assert session["recovered_item_id"] == item["id"]
    assert session["cue_that_worked"] == "chip:task"
    assert session["seconds_taken"] >= 0

    again = client.patch(f"/retrace/{session_id}", headers=AUTH, json={"outcome": "gave_up"})
    assert again.status_code == 409


def test_recovering_an_item_already_on_the_list_adds_nothing(client):
    item_id = add_item("Buy printer paper", created_at=datetime.now(timezone.utc).isoformat())
    session_id = client.post("/retrace", headers=AUTH).json()["id"]

    body = client.patch(f"/retrace/{session_id}", headers=AUTH,
                        json={"outcome": "recovered", "item_id": item_id, "cue": f"item:{item_id}"}).json()

    assert (body["recovered_item_id"], body["capture"]) == (item_id, None)
    assert len(client.get("/items", headers=AUTH).json()) == 1

    other = client.post("/retrace", headers=AUTH).json()["id"]
    missing = client.patch(f"/retrace/{other}", headers=AUTH, json={"outcome": "recovered", "item_id": 999})
    assert missing.status_code == 404


@pytest.mark.parametrize("body,status", [
    ({"outcome": "recovered"}, 422),
    ({"outcome": "recovered", "text": "  "}, 422),
    ({"outcome": "lost"}, 422),
])
def test_end_retrace_validation(client, body, status):
    session_id = client.post("/retrace", headers=AUTH).json()["id"]
    assert client.patch(f"/retrace/{session_id}", headers=AUTH, json=body).status_code == status


def test_end_unknown_session(client):
    assert client.patch("/retrace/999", headers=AUTH, json={"outcome": "gave_up"}).status_code == 404


def test_retrace_requires_key(client):
    assert client.post("/retrace").status_code == 401
    assert client.patch("/retrace/1", json={"outcome": "gave_up"}).status_code == 401
