"""Policy search tool.

Why keyword search and not embeddings: there are only ~15 short sections, so a
few lines of word matching are enough, need no API key or network, give the same
result every time, and can be unit-tested. The score is easy to explain:
each query word that appears in a section's heading adds 3, in its body adds 1.
"""

import re

from helpdesk.data import PolicySection

HEADING_WEIGHT = 3
BODY_WEIGHT = 1

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "do", "does", "can", "i", "my", "me", "you", "your",
    "we", "to", "of", "on", "in", "at", "for", "and", "or", "it", "this", "that", "what",
    "which", "how", "when", "where", "who", "get", "want", "e",
}  # fmt: skip

# Words (already stemmed) that mean the same thing for this shop. A query word
# searches for its whole group. "e-bike" becomes "bike" because "e" is a stopword.
SYNONYM_GROUPS = [
    {"ebike", "electric"},
    {"cancel", "cancell", "cancellation", "refund"},
    {"open", "opening", "hour"},
    {"price", "cost", "much"},
    {"kid", "child", "children"},
    {"age", "old", "year"},
    {"currency", "euro", "eur"},
    {"christmas", "holiday", "december"},
]  # fmt: skip

SUFFIXES = ("ing", "ed", "s")
MIN_STEM_LENGTH = 3


def search_policies(sections: list[PolicySection], query: str, top_k: int = 3) -> dict:
    """Return the best matching sections, highest score first. Only sections with score > 0."""
    terms = _expand(_words(query))
    scored = [(_score(section, terms), section) for section in sections]
    best = sorted((pair for pair in scored if pair[0] > 0), key=lambda pair: -pair[0])
    results = [
        {"source": s.source, "heading": s.heading, "text": s.text, "score": score}
        for score, s in best[: max(top_k, 0)]
    ]
    return {"query": query, "results": results}


def _words(text: object) -> set[str]:
    if not isinstance(text, str):
        return set()
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(token) for token in tokens if token not in STOPWORDS}


def _stem(word: str) -> str:
    for suffix in SUFFIXES:
        if word.endswith(suffix) and not word.endswith("ss") and len(word) - len(suffix) >= MIN_STEM_LENGTH:
            return word[: -len(suffix)]
    return word


def _expand(words: set[str]) -> set[str]:
    expanded = set(words)
    for group in SYNONYM_GROUPS:
        if words & group:
            expanded |= group
    return expanded


def _score(section: PolicySection, terms: set[str]) -> int:
    heading_hits = len(terms & _words(section.heading))
    body_hits = len(terms & _words(section.text))
    return heading_hits * HEADING_WEIGHT + body_hits * BODY_WEIGHT
