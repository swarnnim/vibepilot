"""The coherence engine — what makes a plan feel like ONE taste.

A culturally blind agent returns five independent top-10 lists. VibePilot
instead builds a *taste profile* from the seeds, then assembles the plan
greedily: every candidate pick is scored on

* **seed affinity** — how much of the candidate's tag vocabulary is the
  seeds' vocabulary (weighted: a tag shared by two seeds counts double),
* **pairwise coherence** — how strongly it rhymes with the picks already
  chosen, so dinner and the film feel cut from the same cloth, and
* **popularity** — a small tiebreaker toward things people actually love.

Picks below a coherence floor are *dropped*, not padded in — a plan with an
honest gap beats a plan with a random filler. Every surviving pick carries
an explanation generated from the actual shared tags, so a human can see
*why* it belongs.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .models import Entity

# Weights of the coherence score (they sum to 1.0).
W_SEED = 0.60
W_PAIR = 0.30
W_POPULARITY = 0.10

#: A pick whose total coherence falls below this floor is dropped.
MIN_COHERENCE = 0.16


@dataclass
class TasteProfile:
    """Weighted tag vocabulary distilled from the seed entities."""

    seeds: tuple  # tuple[Entity]
    tag_weights: dict  # tag -> weight in (0, 1]; 1.0 = present in every seed

    @classmethod
    def from_seeds(cls, seeds) -> "TasteProfile":
        seeds = tuple(seeds)
        if not seeds:
            return cls(seeds=(), tag_weights={})
        counts = Counter()
        for s in seeds:
            for t in set(s.tags):
                counts[t] += 1
        n = len(seeds)
        weights = {t: c / n for t, c in counts.items()}
        return cls(seeds=seeds, tag_weights=weights)

    def weight(self, tag: str) -> float:
        return self.tag_weights.get(tag, 0.0)

    def top_tags(self, n: int = 5):
        return [t for t, _ in sorted(self.tag_weights.items(), key=lambda kv: -kv[1])[:n]]


@dataclass
class ScoreBreakdown:
    seed: float = 0.0
    pair: float = 0.0
    popularity: float = 0.0
    total: float = 0.0

    def as_dict(self):
        return {
            "seed": round(self.seed, 4),
            "pair": round(self.pair, 4),
            "popularity": round(self.popularity, 4),
            "total": round(self.total, 4),
        }


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_candidate(candidate: Entity, profile: TasteProfile, selected, affinity: float = 0.0) -> ScoreBreakdown:
    """Score one candidate against the seed profile and the picks so far.

    Seed relatedness is measured through two independent lenses and the
    stronger one counts: (a) shared-tag weight against the seed profile —
    transparent, but weak across domains, whose tag vocabularies barely
    overlap (movie plot keywords vs. artist descriptors); (b) the backend's
    own taste-graph affinity (Qloo's graph, or the fixture graph's
    tag-derived affinity offline), squared so weak affinities are discounted
    and only a strong graph signal can carry a pick on its own. A candidate
    with neither shared tags nor a real affinity still scores ~0 and is
    dropped by the floor — no evidence, no pick.
    """
    if candidate.tags:
        tag_score = sum(profile.weight(t) for t in candidate.tags) / len(candidate.tags)
    else:
        tag_score = 0.0
    seed_score = max(tag_score, affinity * affinity)
    if selected:
        ctags = candidate.tag_set()
        pair_score = sum(jaccard(ctags, p.tag_set()) for p in selected) / len(selected)
    else:
        pair_score = 0.0
    pop = candidate.popularity
    total = W_SEED * seed_score + W_PAIR * pair_score + W_POPULARITY * pop
    return ScoreBreakdown(seed=seed_score, pair=pair_score, popularity=pop, total=total)


@dataclass
class Pick:
    entity: Entity
    score: ScoreBreakdown
    affinity: float  # the backend's own affinity for this candidate
    why: str

    def as_dict(self):
        return {
            "id": self.entity.id,
            "name": self.entity.name,
            "type": self.entity.type,
            "tags": list(self.entity.tags),
            "city": self.entity.city,
            "blurb": self.entity.blurb,
            "affinity": round(self.affinity, 4),
            "coherence": self.score.as_dict(),
            "why": self.why,
        }


def explain(candidate: Entity, profile: TasteProfile, selected) -> str:
    """Generate the human 'why this pick' line from real shared tags."""
    shared = sorted(
        (t for t in candidate.tags if profile.weight(t) > 0),
        key=lambda t: (-profile.weight(t), t),
    )
    bits = []
    if shared:
        shown = ", ".join(shared[:3])
        bits.append(f"shares “{shown}” with your seeds")
    # Echo: the already-chosen pick it rhymes with most.
    best, best_shared = None, []
    for p in selected:
        inter = sorted(set(candidate.tags) & set(p.tags))
        if len(inter) > len(best_shared):
            best, best_shared = p, inter
    if best is not None and best_shared:
        bits.append(f"echoes {best.name} through “{', '.join(best_shared[:2])}”")
    if not bits:
        bits.append("the closest taste-graph neighbour for this slot")
    return "; ".join(bits) + "."


def choose_pick(candidates, profile: TasteProfile, selected, used_ids: set):
    """Greedily choose the most coherent candidate for one itinerary slot.

    ``candidates`` is the backend's ``(entity, affinity)`` list. Returns a
    :class:`Pick` or ``None`` when every candidate is already used or falls
    below the coherence floor (an honest gap beats a random filler).
    """
    best = None
    for entity, affinity in candidates:
        if entity.id in used_ids:
            continue
        bd = score_candidate(entity, profile, selected, affinity=affinity)
        if bd.total < MIN_COHERENCE:
            continue
        ranked = (bd.total, affinity, entity.popularity)
        if best is None or ranked > best[0]:
            best = (ranked, entity, affinity, bd)
    if best is None:
        return None
    _, entity, affinity, bd = best
    return Pick(entity=entity, score=bd, affinity=affinity,
                why=explain(entity, profile, selected))
