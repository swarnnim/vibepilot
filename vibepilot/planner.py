"""Itinerary assembly: turn resolved seeds into an ordered, coherent plan.

Each occasion is a template of slots (set the scene → dinner → film →
soundtrack → take-home book, and variants). Slots are filled greedily in
order by the coherence engine, so every pick is chosen *in the context of
the picks before it* — that's what makes the evening feel like one taste
instead of five unrelated lists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .coherence import TasteProfile, choose_pick

# Slot: (label, time, entity_type)
OCCASIONS = {
    "date_night": {
        "title": "Date night",
        "slots": [
            ("The look", "17:00", "fashion_brand"),
            ("Set the scene", "17:45", "destination"),
            ("Dinner", "19:00", "restaurant"),
            ("The film", "21:15", "movie"),
            ("The soundtrack home", "23:00", "music_artist"),
            ("Take home", "for the shelf", "book"),
        ],
    },
    "solo_recharge": {
        "title": "Solo recharge",
        "slots": [
            ("Slow start", "10:00", "restaurant"),
            ("Read", "11:30", "book"),
            ("Wander", "14:00", "destination"),
            ("One film, just for you", "19:30", "movie"),
            ("Wind down", "21:30", "music_artist"),
        ],
    },
    "friends_visiting": {
        "title": "Friends in town — the food crawl",
        "slots": [
            ("First bite", "12:30", "restaurant"),
            ("The main event", "15:00", "restaurant"),
            ("Walk it off", "17:30", "destination"),
            ("Late-night finish", "20:00", "restaurant"),
            ("The playlist", "all day", "music_artist"),
        ],
    },
}


@dataclass
class Step:
    label: str
    time: str
    entity_type: str
    pick: object = None  # coherence.Pick | None (slot honestly left open)

    def as_dict(self):
        return {
            "label": self.label,
            "time": self.time,
            "type": self.entity_type,
            "pick": self.pick.as_dict() if self.pick else None,
        }


@dataclass
class Plan:
    occasion: str
    title: str
    city: str
    seeds: list
    profile: TasteProfile
    backend_label: str
    steps: list = field(default_factory=list)

    @property
    def filled(self):
        return sum(1 for s in self.steps if s.pick is not None)

    def as_dict(self):
        return {
            "occasion": self.occasion,
            "title": self.title,
            "city": self.city,
            "seeds": [
                {"id": s.id, "name": s.name, "type": s.type, "tags": list(s.tags)}
                for s in self.seeds
            ],
            "taste_profile": self.profile.top_tags(8),
            "data_source": self.backend_label,
            "steps": [s.as_dict() for s in self.steps],
        }

    def to_markdown(self) -> str:
        where = f" in {self.city}" if self.city else ""
        lines = [
            f"# VibePilot — {self.title}{where}",
            "",
            f"**Seeds:** {' · '.join(s.name for s in self.seeds)}",
            f"**Taste profile:** {' · '.join(self.profile.top_tags(6))}",
            f"**Data:** {self.backend_label}",
            "",
        ]
        for step in self.steps:
            if step.pick is None:
                lines += [
                    f"**{step.time} — {step.label}:** _left open_ — no "
                    f"{step.entity_type.replace('_', ' ')} in the graph cleared the "
                    "coherence bar. We'd rather leave a gap than force a mismatch.",
                    "",
                ]
                continue
            e = step.pick.entity
            place = f" · {e.city}" if e.city else ""
            lines += [
                f"**{step.time} — {step.label}: {e.name}** ({e.short_type()}{place})",
                f"{e.blurb}" if e.blurb else "",
                f"_Why this pick:_ {step.pick.why}",
                f"_Coherence {step.pick.score.total:.2f} · taste-graph affinity "
                f"{step.pick.affinity:.2f} · tags: {', '.join(e.tags)}_",
                "",
            ]
        lines.append(
            f"_{self.filled}/{len(self.steps)} slots filled — every pick scored "
            "against your seeds AND against each other pick._"
        )
        return "\n".join(lines)


def build_plan(backend, seeds, occasion="date_night", city="") -> Plan:
    """Assemble a plan: resolve the template, fill slots greedily."""
    template = OCCASIONS.get(occasion) or OCCASIONS["date_night"]
    profile = TasteProfile.from_seeds(seeds)
    seed_ids = [s.id for s in seeds]
    plan = Plan(
        occasion=occasion,
        title=template["title"],
        city=city or "",
        seeds=list(seeds),
        profile=profile,
        backend_label=backend.label,
    )
    selected_entities = []
    used_ids = set(seed_ids)
    for label, time, entity_type in template["slots"]:
        candidates = backend.related(seed_ids, entity_type, limit=8)
        if city:
            # Soft city preference: local picks first on ties.
            candidates = sorted(
                candidates,
                key=lambda p: -(p[1] + (0.15 if p[0].city == city else 0.0)),
            )
        pick = choose_pick(candidates, profile, selected_entities, used_ids)
        if pick is not None:
            used_ids.add(pick.entity.id)
            selected_entities.append(pick.entity)
        plan.steps.append(Step(label=label, time=time, entity_type=entity_type, pick=pick))
    return plan
