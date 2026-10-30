"""Policy search tool.

Why keyword search and not embeddings: there are only 22 small sections, so a
few lines of word matching are enough. It needs no API key or network, gives the
same result every time (deterministic, testable), and the score is easy to
explain: each distinct query word (or synonym) found in a section's heading adds
3, found in its body adds 1. A section needs a total score of at least 2.

Known limits: no real understanding of meaning (only the small SYNONYM_GROUPS
table), no typo tolerance, and questions about things the shop never wrote down
can still match by accident. "What are your hours?" finds nothing, because "hour"
is deliberately not an opening-hours synonym: it hijacked every "price per hour"
question. Next step if the policies grow: embeddings or a hybrid with BM25 ranking.
"""

import re

from helpdesk.data import PolicySection

HEADING_WEIGHT = 3
BODY_WEIGHT = 1
MIN_SCORE = 2  # one weak body hit is not enough evidence
DEFAULT_TOP_K = 3
MIN_PREFIX_LENGTH = 4
NO_RESULTS_NOTE = "No relevant policy found."

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "do", "does", "can", "i", "my", "me", "you", "your",
    "we", "to", "of", "on", "in", "at", "for", "and", "or", "it", "this", "that", "what",
    "which", "how", "when", "who", "get", "want", "there",
}  # fmt: skip

# Every question in this shop is about bike rental, so these words say nothing. They are dropped from
# the query only; the section texts keep them, so the price group below can reach the "Bike rental" heading.
GENERIC_WORDS = {"bike", "bikes", "rent", "rental", "citywheels"}

# Words that mean the same thing for this shop. A query word searches its whole group.
SYNONYM_GROUPS = [
    {"ebike", "electric"},
    {"open", "opening", "close", "closed", "closing"},
    {"discount", "off", "week", "days"},
    {"lock", "add", "extra"},  # "add" reaches the Add-ons heading
    {"money", "refund", "back"},
    {"christmas", "december", "january"},
    {"price", "cost", "much", "rate", "hourly", "daily", "rental"},  # the price table is under "Bike rental"
]  # fmt: skip


def search_policies(sections: list[PolicySection], query: str, top_k: int = DEFAULT_TOP_K) -> dict:
    """Return the best matching sections, best first. Never raises; no match gives a note."""
    terms = _expand(_query_tokens(query))
    ranked = sorted((_rank(section, terms) for section in sections), key=lambda r: r[:3], reverse=True)
    best_first = [item for item in ranked if item[0] >= MIN_SCORE]
    results = [
        {"source": s.source, "heading": s.heading, "text": s.text, "score": score}
        for score, _, _, s in best_first[:top_k]
    ]
    output = {"query": query, "results": results}
    if not results:
        output["note"] = NO_RESULTS_NOTE
    return output


def _tokens(text: object) -> set[str]:
    if not isinstance(text, str):
        return set()
    text = re.sub(r"\be[- ]?bikes?\b", "ebike", text.lower())  # "e-bike" must not become "bike"
    words = re.findall(r"[a-z0-9]+", text)
    return {w for w in words if w not in STOPWORDS and w not in GENERIC_WORDS}


def _query_tokens(query: object) -> set[str]:
    words = _tokens(query) - GENERIC_WORDS
    # "can I rent an e-bike at 15?" is an age question, though it never says "age".
    if isinstance(query, str) and re.search(r"\bat \d{1,2}\b(?![:.]\d)", query.lower()):
        words.add("age")
    return words


def _same_word(a: str, b: str) -> bool:
    """Equal, or one is a prefix of the other and the shorter has 4+ letters: close/closed."""
    short, long = sorted((a, b), key=len)
    return a == b or (len(short) >= MIN_PREFIX_LENGTH and long.startswith(short))


def _expand(words: set[str]) -> set[str]:
    expanded = set(words)
    for group in SYNONYM_GROUPS:
        if any(_same_word(w, entry) for w in words for entry in group):
            expanded |= group
    return expanded


def _hits(terms: set[str], words: set[str]) -> int:
    return sum(1 for term in terms if any(_same_word(term, word) for word in words))


def _rank(section: PolicySection, terms: set[str]) -> tuple:
    """Sort key: higher score, then more heading hits, then shorter section."""
    heading_hits = _hits(terms, _tokens(section.heading))
    body_hits = _hits(terms, _tokens(section.text))
    score = heading_hits * HEADING_WEIGHT + body_hits * BODY_WEIGHT
    return (score, heading_hits, -len(section.text), section)
