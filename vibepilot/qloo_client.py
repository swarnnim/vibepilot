"""Live Qloo API client — the real backend.

Implements the documented Qloo shapes (https://docs.qloo.com):

* **Auth** — every request carries ``X-Api-Key: <key>``; the key comes from
  the ``QLOO_API_KEY`` environment variable, never from code.
* **Entity search** — ``GET https://api.qloo.com/search?query=<text>``
  returns ``results``: a list of ``{entity_id, name, type, ...}``.
* **Insights (recommendations)** — ``GET https://api.qloo.com/v2/insights/``
  with ``filter.type=urn:entity:<type>`` and
  ``signal.interests.entities=<seed URN,seed URN>``, ``take=<n>``,
  ``sort_by=affinity``. Results carry ``entity_id``, ``name``, ``type``,
  ``popularity`` and ``tags`` (``[{name, tag_id}]``) — exactly what the
  coherence engine consumes.

All parsing is defensive: field names accept the documented variants
(``entity_id``/``id``/``urn``, tags as dicts or strings, results as a list
or ``results.entities``) so minor API shape drift degrades gracefully
instead of crashing. HTTP is injectable (``transport``) so tests can run
the full request/response path with zero network.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from .backend import TasteBackend
from .models import Entity

BASE_URL = "https://api.qloo.com"

TYPE_URNS = {
    "person": "urn:entity:person",
    "movie": "urn:entity:movie",
    "music_artist": "urn:entity:music_artist",
    "restaurant": "urn:entity:restaurant",
    "book": "urn:entity:book",
    "fashion_brand": "urn:entity:fashion_brand",
    "destination": "urn:entity:destination",
}


class QlooConfigError(RuntimeError):
    """Raised when the client cannot be configured (e.g. no API key)."""


class QlooAPIError(RuntimeError):
    """Raised when the Qloo API returns an error response."""

    def __init__(self, status, message, url=""):
        super().__init__(f"Qloo API error (HTTP {status}): {message}")
        self.status = status
        self.url = url


def _urn_to_type(urn: str) -> str:
    parts = str(urn).split(":")
    return parts[2] if len(parts) >= 3 else ""


def _entity_from_payload(item: dict) -> Entity | None:
    if not isinstance(item, dict):
        return None
    eid = item.get("entity_id") or item.get("id") or item.get("urn") or ""
    name = item.get("name") or ""
    if not eid or not name:
        return None
    etype = item.get("type") or _urn_to_type(eid)
    if etype.startswith("urn:"):
        etype = _urn_to_type(etype)
    props = item.get("properties") or {}
    city = props.get("city") or item.get("city") or ""
    blurb = props.get("description") or item.get("description") or ""
    return Entity(
        id=eid,
        name=name,
        type=etype or "movie",
        tags=item.get("tags") or props.get("tags") or (),
        popularity=float(item.get("popularity") or 0.5),
        city=city,
        blurb=blurb,
    )


class QlooClient(TasteBackend):
    """TasteBackend over the live Qloo API."""

    label = "Qloo live API (api.qloo.com)"

    def __init__(self, api_key: str | None = None, transport=None, timeout: int = 20):
        key = api_key or os.environ.get("QLOO_API_KEY", "")
        if not key:
            raise QlooConfigError(
                "No Qloo API key found. Set QLOO_API_KEY in the environment "
                "to use live mode, or run with --offline for the fixture demo."
            )
        self._api_key = key
        self._timeout = timeout
        self._transport = transport or self._urllib_transport

    # -- HTTP plumbing --------------------------------------------------------
    def _urllib_transport(self, url: str, headers: dict):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except Exception:
                payload = {}
            return e.code, payload
        except urllib.error.URLError as e:
            raise QlooAPIError(0, f"network error reaching Qloo: {e.reason}", url)

    def build_url(self, path: str, params: dict) -> str:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
        return f"{BASE_URL}{path}?{qs}" if qs else f"{BASE_URL}{path}"

    def _get(self, path: str, params: dict) -> dict:
        url = self.build_url(path, params)
        headers = {"X-Api-Key": self._api_key, "Accept": "application/json"}
        status, payload = self._transport(url, headers)
        if status >= 400 or (isinstance(payload, dict) and payload.get("success") is False):
            msg = ""
            if isinstance(payload, dict):
                msg = str(payload.get("message") or payload.get("error") or "")
            raise QlooAPIError(status, msg or "request failed", url)
        return payload if isinstance(payload, dict) else {}

    # -- search ----------------------------------------------------------------
    def search(self, query, entity_type=None, limit=5):
        params = {"query": query}
        if entity_type:
            params["types"] = TYPE_URNS.get(entity_type, "")
        payload = self._get("/search", params)
        results = payload.get("results") or []
        out = []
        for idx, item in enumerate(results[:limit]):
            ent = _entity_from_payload(item)
            if ent is None:
                continue
            score = item.get("score")
            score = float(score) if score is not None else round(1.0 - 0.1 * idx, 4)
            out.append((ent, max(0.0, min(1.0, score))))
        return out

    # -- cross-domain expansion --------------------------------------------------
    def related(self, seed_ids, target_type, limit=8):
        if not seed_ids:
            return []
        params = {
            "filter.type": TYPE_URNS.get(target_type, f"urn:entity:{target_type}"),
            "signal.interests.entities": ",".join(seed_ids),
            "take": limit,
            "sort_by": "affinity",
        }
        payload = self._get("/v2/insights/", params)
        results = payload.get("results") or {}
        items = results.get("entities") if isinstance(results, dict) else results
        items = items or []
        seed_set = set(seed_ids)
        out = []
        n = max(len(items), 1)
        for idx, item in enumerate(items):
            ent = _entity_from_payload(item)
            if ent is None or ent.id in seed_set:
                continue
            affinity = item.get("affinity")
            if affinity is None and isinstance(item.get("query"), dict):
                affinity = item["query"].get("affinity")
            affinity = float(affinity) if affinity is not None else round(1.0 - idx / n, 4)
            out.append((ent, max(0.0, min(1.0, affinity))))
        out.sort(key=lambda p: -p[1])
        return out[:limit]
