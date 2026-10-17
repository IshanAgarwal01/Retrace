from datetime import datetime, timedelta, timezone

import pytest

import ghosts
import main
import notify
from carmen import COLUMBUS
from helpers import AUTH, fake_parse
from test_context import add_context


def give_up(client, place=None):
    """Run a Retrace session that ends "Still gone"; returns the ghost row."""
    if place:
        add_context(place, hours_ago=0.1)
    session_id = client.post("/retrace", headers=AUTH).json()["id"]
    client.patch(f"/retrace/{session_id}", headers=AUTH, json={"outcome": "ghost"})
    conn = main.connect()
    ghost = conn.execute("SELECT * FROM ghosts WHERE retrace_session_id = ?", (session_id,)).fetchone()
    conn.close()
    return ghost


def backdate(ghost_id, days, hour_offset=0):
    """Pretend the ghost was left `days` ago, at `hour_offset` hours from this hour."""
    lost = datetime.now(timezone.utc) - timedelta(days=days)
    conn = main.connect()
    with conn.transaction():
        conn.execute(
            "UPDATE ghosts SET created_at = ?, expires_at = ?, hour = ? WHERE id = ?",
            (lost.isoformat(), (lost + ghosts.LIFETIME).isoformat(),
             (datetime.now(COLUMBUS).hour + hour_offset) % 24, ghost_id),
        )
    conn.close()


def ghost_row(ghost_id):
    conn = main.connect()
    row = conn.execute("SELECT * FROM ghosts WHERE id = ?", (ghost_id,)).fetchone()
    conn.close()
    return row


def test_still_gone_leaves_a_ghost(client):
    ghost = give_up(client, "Dreese")

    assert ghost["place"] == "Dreese"
    assert ghost["hour"] == datetime.now(COLUMBUS).hour
    created = datetime.fromisoformat(ghost["created_at"])
    assert datetime.fromisoformat(ghost["expires_at"]) - created == timedelta(days=14)
    assert ghost["prompted_at"] is None and ghost["resolved_item_id"] is None


def test_other_outcomes_leave_no_ghost(client):
    session_id = client.post("/retrace", headers=AUTH).json()["id"]
    client.patch(f"/retrace/{session_id}", headers=AUTH, json={"outcome": "gave_up"})
    conn = main.connect()
    assert conn.execute("SELECT COUNT(*) AS n FROM ghosts").fetchone()["n"] == 0
    conn.close()


def test_arriving_at_the_same_place_prompts_once_a_day(client, sent):
    ghost = give_up(client, "Dreese")
    backdate(ghost["id"], days=3, hour_offset=6)
    other = give_up(client, "Dreese")
    backdate(other["id"], days=4, hour_offset=6)

    first = client.post("/contexts", json={"place": "dreese"}, headers=AUTH).json()

    assert first["ghost_prompted"] == ghost["id"]  # the newest matching ghost
    lost_day = (datetime.now(COLUMBUS) - timedelta(days=3)).strftime("%A")
    assert sent == [{"title": "Retrace", "url": None,
                     "message": f"Last {lost_day} at Dreese you lost a thought. Anything come back?"}]
    assert ghost_row(ghost["id"])["prompted_at"] is not None

    # The other ghost also matches, but one prompt a day is enough
    assert client.post("/contexts", json={"place": "Dreese"}, headers=AUTH).json()["ghost_prompted"] is None
    assert len(sent) == 1


def test_same_hour_of_day_also_prompts(client, sent, monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://retrace.onrender.com")
    ghost = give_up(client)  # no place known
    backdate(ghost["id"], days=1, hour_offset=1)

    body = client.post("/contexts", json={"place": "RPAC"}, headers=AUTH).json()

    assert body["ghost_prompted"] == ghost["id"]
    assert sent[0]["message"].startswith("Yesterday around ")
    assert sent[0]["url"] == f"https://retrace.onrender.com/?ghost={ghost['id']}"


@pytest.mark.parametrize("days,hour_offset,place", [
    (0, 0, "Dreese"),   # lost today: too soon to ask
    (15, 0, "Dreese"),  # expired after two weeks
    (2, 5, "Union"),    # different place and a different time of day
])
def test_no_prompt(client, sent, days, hour_offset, place):
    ghost = give_up(client, "Dreese")
    backdate(ghost["id"], days=days, hour_offset=hour_offset)
    assert client.post("/contexts", json={"place": place}, headers=AUTH).json()["ghost_prompted"] is None
    assert sent == []


def test_failed_notification_leaves_ghost_unprompted(client, monkeypatch):
    monkeypatch.setattr(notify, "send", lambda *args, **kwargs: False)
    ghost = give_up(client, "Dreese")
    backdate(ghost["id"], days=2)
    assert client.post("/contexts", json={"place": "Dreese"}, headers=AUTH).json()["ghost_prompted"] is None
    assert ghost_row(ghost["id"])["prompted_at"] is None


def test_chasing_a_ghost_and_recovering_it_resolves_it(client, monkeypatch):
    ghost = give_up(client, "Dreese")
    add_context("Union", hours_ago=0)  # you're somewhere else now
    monkeypatch.setattr(main, "parse_capture", fake_parse([
        {"type": "idea", "title": "Club flyer idea", "due_at": None, "all_day": False,
         "course": None, "place": None}]))

    start = client.post("/retrace", json={"ghost_id": ghost["id"]}, headers=AUTH).json()
    assert start["context"]["ghost"]["place"] == "Dreese"

    end = client.patch(f"/retrace/{start['id']}", headers=AUTH,
                       json={"outcome": "recovered", "text": "club flyer idea", "ghost_id": ghost["id"]}).json()
    assert ghost_row(ghost["id"])["resolved_item_id"] == end["recovered_item_id"]


def test_chasing_a_ghost_and_still_failing_makes_no_new_ghost(client):
    ghost = give_up(client, "Dreese")
    session_id = client.post("/retrace", json={"ghost_id": ghost["id"]}, headers=AUTH).json()["id"]
    client.patch(f"/retrace/{session_id}", headers=AUTH, json={"outcome": "ghost", "ghost_id": ghost["id"]})
    conn = main.connect()
    assert conn.execute("SELECT COUNT(*) AS n FROM ghosts").fetchone()["n"] == 1
    conn.close()


def test_unknown_ghost(client):
    assert client.post("/retrace", json={"ghost_id": 999}, headers=AUTH).status_code == 404


def test_when_lost_wording():
    now = datetime(2026, 10, 22, 16, 0, tzinfo=timezone.utc)  # Thu Oct 22
    assert ghosts.when_lost(now - timedelta(days=1), now) == "Yesterday"
    assert ghosts.when_lost(now - timedelta(days=2), now) == "Last Tuesday"
    assert ghosts.when_lost(now - timedelta(days=10), now) == "On Mon Oct 12"


def test_sync_keeps_places_ghosts_point_at(client, monkeypatch):
    from helpers import FEED, use_feed

    old = add_context("Dreese", hours_ago=24 * 40)
    unused = add_context("Union", hours_ago=24 * 40)
    conn = main.connect()
    with conn.transaction():
        session_id = conn.execute(
            "INSERT INTO retrace_sessions (started_at, context_id, cues_shown) VALUES (?, ?, '[]') RETURNING id",
            ("2026-09-01T12:00:00+00:00", old),
        ).fetchone()["id"]
        ghosts.create_ghost(conn, conn.execute(
            "SELECT * FROM retrace_sessions WHERE id = ?", (session_id,)).fetchone())
        # A session without a ghost doesn't keep its place alive
        conn.execute("INSERT INTO retrace_sessions (started_at, context_id, cues_shown) VALUES (?, ?, '[]')",
                     ("2026-09-01T12:00:00+00:00", unused))
    conn.close()

    use_feed(monkeypatch, FEED)
    client.post("/sync", headers=AUTH)

    conn = main.connect()
    places = [row["place"] for row in conn.execute("SELECT place FROM contexts").fetchall()]
    orphaned = conn.execute("SELECT COUNT(*) AS n FROM retrace_sessions WHERE context_id IS NULL").fetchone()
    conn.close()
    assert places == ["Dreese"]
    assert orphaned["n"] == 1
