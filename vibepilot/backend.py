"""The taste-backend interface.

VibePilot's planner only ever talks to a :class:`TasteBackend`. Two
implementations exist:

* :class:`~vibepilot.qloo_client.QlooClient` — the live Qloo API.
* :class:`~vibepilot.fixtures.FixtureBackend` — a bundled mini taste-graph
  for offline demos and tests.

Both expose the same two operations, mirroring how Qloo itself is used:
resolve free text to entities (search), then expand seeds cross-domain
(insights / recommendations).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class TasteBackend(ABC):
    #: Human label printed in every plan so judges can tell live data from
    #: fixture data at a glance. Fixture output must never masquerade as live.
    label: str = "unknown backend"

    @abstractmethod
    def search(self, query: str, entity_type: str | None = None, limit: int = 5):
        """Resolve free text to entities.

        Returns a list of ``(entity, score)`` tuples, best match first,
        score in 0..1.
        """
        raise NotImplementedError

    @abstractmethod
    def related(self, seed_ids, target_type: str, limit: int = 8):
        """Cross-domain expansion: entities of ``target_type`` that the taste
        graph connects to the seed entities.

        Returns a list of ``(entity, affinity)`` tuples, strongest first,
        affinity in 0..1. Seed entities themselves are excluded.
        """
        raise NotImplementedError

    def all_entities(self):
        """Every entity the backend knows (fixture backend only; live
        backends return an empty list — the graph is far too big to list)."""
        return []
