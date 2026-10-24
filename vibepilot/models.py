"""Core data model shared by every backend.

An :class:`Entity` is one node of the taste graph: a film, a restaurant, a
song artist, a book... Each entity carries a set of *taste tags* — the shared
vocabulary the coherence engine reasons over. Tags are normalized to
lowercase, hyphenated form (``faded-elegance``, ``lantern-lit``) so fixture
tags and Qloo API tag names compare cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Entity types VibePilot knows how to plan with. These mirror Qloo's
#: entity taxonomy (urn:entity:<type>).
ENTITY_TYPES = (
    "person",
    "movie",
    "music_artist",
    "restaurant",
    "book",
    "fashion_brand",
    "destination",
)


def normalize_tag(tag: str) -> str:
    """Normalize a raw tag (from fixtures or the Qloo API) to canonical form."""
    return "-".join(str(tag).strip().lower().replace("_", " ").split())


def normalize_tags(tags) -> tuple:
    out = []
    for t in tags or ():
        # Qloo returns tags as {"name": ..., "tag_id": ...} dicts.
        if isinstance(t, dict):
            t = t.get("name") or t.get("tag") or ""
        n = normalize_tag(t)
        if n and n not in out:
            out.append(n)
    return tuple(out)


@dataclass(frozen=True)
class Entity:
    """One taste-graph node."""

    id: str  # URN, e.g. "urn:entity:movie:the-grand-budapest-hotel"
    name: str
    type: str  # one of ENTITY_TYPES
    tags: tuple = ()
    popularity: float = 0.5  # 0..1, Qloo-style popularity score
    city: str = ""  # where it lives, if place-bound ("" = anywhere)
    blurb: str = ""  # one-line human description for plan rendering

    def __post_init__(self):
        object.__setattr__(self, "tags", normalize_tags(self.tags))
        object.__setattr__(self, "popularity", max(0.0, min(1.0, float(self.popularity))))

    def tag_set(self) -> frozenset:
        return frozenset(self.tags)

    def short_type(self) -> str:
        return {
            "music_artist": "music",
            "fashion_brand": "style",
        }.get(self.type, self.type)
