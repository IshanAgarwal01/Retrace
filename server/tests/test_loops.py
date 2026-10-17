import json

import loops
import main
from helpers import AUTH, add_item, fake_parse


def capture(client, monkeypatch, title):
    item = {"type": "task", "title": title, "due_at": None, "all_day": False,
            "course": None, "place": None}
    monkeypatch.setattr(main, "parse_capture", fake_parse([item]))
    return client.post("/captures", json={"text": title}, headers=AUTH).json()


def test_same_words():
    assert loops.same_words("Buy printer paper", "buy more printer papers")
    assert not loops.same_words("Buy printer paper", "Buy milk")
    assert loops.same_words("Call mom", "call MOM")
    assert not loops.same_words("Laundry", "laundry today")  # one real word isn't enough to judge


def test_third_time_is_noticed_without_gemini(client, monkeypatch):
    first = capture(client, monkeypatch, "Email professor about the regrade")
    assert first["loop"] is None
    capture(client, monkeypatch, "email the professor about my regrade")
    third = capture(client, monkeypatch, "Professor regrade email")

    assert third["loop"] == "You've thought about this 3 times"
    assert third["summary"] == "Task: Professor regrade email\nYou've thought about this 3 times"


def test_done_items_dont_count(client, monkeypatch):
    add_item("Email professor about the regrade", status="done")
    add_item("Email professor about regrade", status="done")
    assert capture(client, monkeypatch, "Email professor about the regrade")["loop"] is None


def test_embeddings_are_used_and_stored(client, monkeypatch):
    # Pretend Gemini put "laundry" and "wash clothes" close together
    vectors = {"Do laundry": [1.0, 0.0], "Wash clothes": [0.95, 0.1], "Buy milk": [0.0, 1.0]}
    monkeypatch.setattr(loops, "embed", lambda texts: [vectors[t] for t in texts])

    capture(client, monkeypatch, "Do laundry")
    capture(client, monkeypatch, "Buy milk")
    capture(client, monkeypatch, "Do laundry")
    result = capture(client, monkeypatch, "Wash clothes")

    assert result["loop"] == "You've thought about this 3 times"
    conn = main.connect()
    stored = conn.execute("SELECT embedding FROM items WHERE title = 'Wash clothes'").fetchone()
    conn.close()
    assert json.loads(stored["embedding"]) == [0.95, 0.1]


def test_embed_calls_gemini_and_falls_back_on_errors(monkeypatch):
    seen = {}

    class FakeEmbedding:
        def __init__(self, values):
            self.values = values

    class FakeClient:
        class models:
            @staticmethod
            def embed_content(**kwargs):
                seen.update(kwargs)

                class Reply:
                    embeddings = [FakeEmbedding([0.1, 0.2]) for _ in kwargs["contents"]]
                return Reply()

    monkeypatch.setattr(loops, "get_client", lambda: FakeClient())
    assert loops.embed(["a", "b"]) == [[0.1, 0.2], [0.1, 0.2]]
    assert seen["model"] == loops.EMBED_MODEL
    assert seen["config"]["output_dimensionality"] == loops.DIMENSIONS

    def broken():
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(loops, "get_client", broken)
    assert loops.embed(["a"]) is None


def test_multi_item_capture_names_the_repeated_thought(client, monkeypatch):
    add_item("Buy printer paper")
    add_item("buy paper for the printer")
    items = [{"type": "task", "title": "Buy printer paper", "due_at": None, "all_day": False,
              "course": None, "place": None},
             {"type": "idea", "title": "Startup idea", "due_at": None, "all_day": False,
              "course": None, "place": None}]
    monkeypatch.setattr(main, "parse_capture", fake_parse(items))

    body = client.post("/captures", json={"text": "..."}, headers=AUTH).json()

    assert body["loop"] == 'You\'ve thought about "Buy printer paper" 3 times'
