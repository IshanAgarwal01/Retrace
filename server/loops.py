"""The loop detector: notice when you keep capturing the same thought.

If a new capture is very similar to two or more items that are still open, the
capture's summary says "You've thought about this N times". That's often a sign
the thing needs doing now, or dropping.

"Similar" is judged with Gemini embeddings when there's an API key: an embedding
turns text into a list of numbers so that texts with similar meaning get similar
lists. Each item's embedding is made once, when it's captured, and stored on the
item, so a capture costs one small API call. Without a key (or if the call fails),
or for older items saved without an embedding, a plain shared-words check is used.
"""

import json
import logging
import math
import re

from capture import CaptureError, get_client

log = logging.getLogger("retrace.loops")

# Gemini's text embedding model, free tier (ai.google.dev/gemini-api/docs/embeddings)
EMBED_MODEL = "gemini-embedding-001"
# 256 numbers per item instead of the default 3072 keeps the stored text small,
# and is plenty for comparing short thoughts
DIMENSIONS = 256

# How alike two thoughts must be to count as the same one
SAME_MEANING = 0.88     # cosine similarity of embeddings, from -1 to 1
SAME_WORDS = 0.5        # share of distinct words in common (Jaccard), from 0 to 1
MIN_SHARED_WORDS = 2
LOOP_AT = 2             # similar open items needed before we say anything

STOPWORDS = {
    "the", "and", "for", "you", "your", "this", "that", "with", "about", "from", "need",
    "needs", "should", "have", "has", "just", "some", "get", "got", "into", "out", "are",
    "was", "were", "will", "can", "today", "tomorrow", "tonight", "also", "really", "maybe",
}


def embed(texts: list[str]) -> list[list[float]] | None:
    """One embedding per text, or None if Gemini isn't available right now."""
    if not texts:
        return []
    try:
        response = get_client().models.embed_content(
            model=EMBED_MODEL,
            contents=texts,
            config={"task_type": "SEMANTIC_SIMILARITY", "output_dimensionality": DIMENSIONS},
        )
        vectors = [e.values for e in response.embeddings or []]
        if len(vectors) != len(texts) or not all(vectors):
            raise CaptureError("Gemini returned the wrong number of embeddings")
        return vectors
    except CaptureError as error:
        log.info("Loop detector using word overlap: %s", error)
    except Exception:
        log.warning("Embedding failed; loop detector using word overlap", exc_info=True)
    return None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    size = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / size if size else 0.0


def content_words(text: str) -> set[str]:
    """Meaningful words, lowercased, with a plural "s" trimmed ("books" -> "book")."""
    found = set()
    for word in re.findall(r"[a-z0-9']+", text.lower()):
        if len(word) < 3 or word in STOPWORDS:
            continue
        found.add(word[:-1] if word.endswith("s") and len(word) > 3 else word)
    return found


def same_words(a: str, b: str) -> bool:
    words_a, words_b = content_words(a), content_words(b)
    shared = words_a & words_b
    if len(shared) < MIN_SHARED_WORDS:
        return False
    return len(shared) / len(words_a | words_b) >= SAME_WORDS


def is_similar(title: str, vector: list[float] | None, other: dict) -> bool:
    """Compare a new item with an open one (a row with title and embedding)."""
    if vector and other["embedding"]:
        return cosine(vector, json.loads(other["embedding"])) >= SAME_MEANING
    return same_words(title, other["title"])


def loop_note(items: list[dict], vectors: list | None, open_items: list[dict]) -> str | None:
    """The line to add to a capture's summary, or None when nothing repeats."""
    notes = []
    for index, item in enumerate(items):
        vector = vectors[index] if vectors else None
        matches = sum(1 for other in open_items if is_similar(item["title"], vector, other))
        if matches >= LOOP_AT:
            times = matches + 1  # the open ones plus this one
            if len(items) == 1:
                notes.append(f"You've thought about this {times} times")
            else:
                notes.append(f'You\'ve thought about "{item["title"]}" {times} times')
    return "\n".join(notes) or None
