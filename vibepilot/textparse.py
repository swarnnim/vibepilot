"""Turn one line of human taste into structured seeds.

Deliberately small and explainable — no NLP stack, no network:

1. **Occasion detection** — keyword rules ("date night", "solo",
   "friends visiting", "food crawl"...).
2. **City detection** — a soft preference matched against the cities the
   backend knows; unknown cities are still honored as a label.
3. **Seed phrases** — the line is split on commas / dashes / "and", filler
   ("I love", "plan my Friday night", ...) is stripped, and each surviving
   phrase is resolved through the backend's own search — so resolution
   works identically against Qloo and against the fixture graph. On the
   fixture backend we additionally scan the raw line for known entity
   names, which catches phrasing the splitter mangles.
"""

from __future__ import annotations

import re

OCCASIONS = ("date_night", "solo_recharge", "friends_visiting")

_OCCASION_RULES = [
    ("friends_visiting", ("friend", "visiting", "food crawl", "group", "mates", "buddies")),
    ("solo_recharge", ("solo", "recharge", "alone", "myself", "me time", "unwind", "quiet night")),
    ("date_night", ("date night", "date", "anniversary", "girlfriend", "boyfriend", "partner", "wife", "husband")),
]

_FILLER_PREFIXES = (
    "i love", "i really love", "i like", "i'm into", "im into", "into",
    "i adore", "i enjoy", "love", "like", "fan of", "a fan of", "obsessed with",
    "we love", "we like", "my favourites are", "my favorites are", "favourites",
)

_PLAN_NOISE = re.compile(
    r"\b(plan|planning|make|build|give|me|my|a|an|the|night|evening|friday|saturday|"
    r"sunday|weekend|tonight|something|please|for|in|around|itinerary|day)\b",
    re.IGNORECASE,
)


def detect_occasion(text: str) -> str:
    low = f" {text.lower()} "
    for occasion, keys in _OCCASION_RULES:
        for k in keys:
            if k in low:
                return occasion
    return "date_night"


def detect_city(text: str, known_cities=()):
    low = text.lower()
    for city in known_cities:
        if city and city.lower() in low:
            return city
    m = re.search(r"\bin\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\b", text)
    if m and m.group(1).lower() not in ("the", "a"):
        return m.group(1)
    return ""


def candidate_phrases(text: str):
    """Split a free-text line into likely seed phrases."""
    parts = re.split(r"[,;—–/]|\band\b|\+", text)
    phrases = []
    for raw in parts:
        p = raw.strip().strip(".!?")
        if not p:
            continue
        low = p.lower()
        for filler in _FILLER_PREFIXES:
            if low.startswith(filler):
                p = p[len(filler):].strip()
                low = p.lower()
                break
        # Drop trailing planning noise ("... films, plan my friday night")
        if "plan" in low or "visiting" in low or "crawl" in low:
            p = _PLAN_NOISE.sub(" ", p).strip(" ,")
            p = re.sub(r"\s+", " ", p)
        if len(p) >= 2 and not _PLAN_NOISE.fullmatch(p.lower()):
            phrases.append(p)
    return phrases


def resolve_seeds(text: str, backend, max_seeds: int = 4):
    """Resolve a free-text line to seed entities via the backend's search."""
    found = {}
    for phrase in candidate_phrases(text):
        for entity, score in backend.search(phrase, limit=3):
            if score >= 0.45:
                found[entity.id] = entity
                break  # best hit per phrase
    # Fixture backends expose their whole graph: also catch entity names
    # mentioned verbatim anywhere in the line (phrasing the splitter missed).
    all_entities = backend.all_entities()
    if all_entities:
        low = text.lower()
        for e in all_entities:
            # Word-boundary match: a bare substring scan would find the
            # film "Her" hiding inside "Everywhere".
            if e.id not in found and re.search(rf"\b{re.escape(e.name.lower())}\b", low):
                found[e.id] = e
    # Prefer "seed-like" entities (people & works) in original mention order.
    seeds = list(found.values())[:max_seeds]
    return seeds
