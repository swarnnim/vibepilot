"""VibePilot test suite — stdlib only, no network.

Covers: fixture search, cross-domain expansion, free-text seed resolution,
occasion detection, coherence scoring math (exact values), explanation
generation, itinerary assembly (incl. the incoherent-pick drop rule and
no-repeat rule), the live Qloo client's request construction + response
parsing against a mocked transport, and backend selection.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibepilot import textparse
from vibepilot.backend import TasteBackend
from vibepilot.cli import main as cli_main
from vibepilot.cli import select_backend
from vibepilot.coherence import (
    MIN_COHERENCE,
    TasteProfile,
    choose_pick,
    explain,
    score_candidate,
)
from vibepilot.fixtures import BY_SLUG, FixtureBackend
from vibepilot.models import Entity
from vibepilot.planner import build_plan
from vibepilot.qloo_client import QlooAPIError, QlooClient, QlooConfigError


def ent(slug, name, etype, tags, pop=0.5):
    return Entity(id=f"urn:entity:{etype}:{slug}", name=name, type=etype,
                  tags=tuple(tags), popularity=pop)


# --------------------------------------------------------------------------
# Fixture backend: search + expansion
# --------------------------------------------------------------------------

def test_fixture_search_exact_name():
    b = FixtureBackend()
    hits = b.search("Radiohead")
    assert hits and hits[0][0].id == BY_SLUG["radiohead"].id
    assert hits[0][1] == 1.0


def test_fixture_search_name_inside_phrase():
    b = FixtureBackend()
    hits = b.search("Wes Anderson films")
    assert hits and hits[0][0].id == BY_SLUG["wes-anderson"].id


def test_fixture_search_type_filter():
    b = FixtureBackend()
    hits = b.search("kyoto", entity_type="destination")
    assert hits, "expected Kyoto destinations"
    assert all(e.type == "destination" for e, _ in hits)


def test_related_is_cross_domain_and_ranked():
    b = FixtureBackend()
    hits = b.related([BY_SLUG["radiohead"].id], "restaurant")
    assert hits, "expected restaurant neighbours for Radiohead"
    assert all(e.type == "restaurant" for e, _ in hits)
    # Sable & Smoke: Radiohead edge + shared 'nocturnal' — should lead.
    assert hits[0][0].id == BY_SLUG["sable-and-smoke"].id
    scores = [s for _, s in hits]
    assert scores == sorted(scores, reverse=True)


def test_related_excludes_seeds():
    b = FixtureBackend()
    hits = b.related([BY_SLUG["radiohead"].id], "music_artist")
    assert all(e.id != BY_SLUG["radiohead"].id for e, _ in hits)


# --------------------------------------------------------------------------
# Free-text parsing
# --------------------------------------------------------------------------

def test_seed_resolution_from_free_text():
    b = FixtureBackend()
    seeds = textparse.resolve_seeds(
        "I love Wes Anderson films and Radiohead — plan my Friday night", b)
    ids = {s.id for s in seeds}
    assert BY_SLUG["wes-anderson"].id in ids
    assert BY_SLUG["radiohead"].id in ids


def test_seed_scan_respects_word_boundaries():
    # Regression: the film "Her" must not be detected inside "Everywhere".
    b = FixtureBackend()
    seeds = textparse.resolve_seeds(
        "We love Everything Everywhere All at Once and Kendrick Lamar", b)
    ids = {s.id for s in seeds}
    assert BY_SLUG["everything-everywhere-all-at-once"].id in ids
    assert BY_SLUG["kendrick-lamar"].id in ids
    assert BY_SLUG["her"].id not in ids


def test_occasion_detection():
    assert textparse.detect_occasion("plan a date night for my wife") == "date_night"
    assert textparse.detect_occasion("a solo evening to recharge by myself") == "solo_recharge"
    assert textparse.detect_occasion("my friends are visiting — food crawl!") == "friends_visiting"
    assert textparse.detect_occasion("surprise me") == "date_night"


# --------------------------------------------------------------------------
# Coherence engine: exact math
# --------------------------------------------------------------------------

def test_profile_weights():
    a = ent("a", "A", "movie", ["x", "y"])
    bseed = ent("b", "B", "movie", ["y", "z"])
    prof = TasteProfile.from_seeds([a, bseed])
    assert prof.weight("y") == 1.0
    assert prof.weight("x") == 0.5
    assert prof.weight("unseen") == 0.0


def test_coherence_math_exact():
    a = ent("a", "A", "movie", ["x", "y"])
    bseed = ent("b", "B", "movie", ["y", "z"])
    prof = TasteProfile.from_seeds([a, bseed])
    cand = ent("c", "C", "book", ["y", "z", "w"], pop=0.8)
    other = ent("d", "D", "restaurant", ["z", "w"])
    bd = score_candidate(cand, prof, [other])
    # seed: (w(y)=1.0 + w(z)=0.5 + w(w)=0) / 3 tags = 0.5
    assert abs(bd.seed - 0.5) < 1e-9
    # pair: jaccard({y,z,w}, {z,w}) = 2/3
    assert abs(bd.pair - (2 / 3)) < 1e-9
    # total: 0.6*0.5 + 0.3*(2/3) + 0.1*0.8 = 0.58
    assert abs(bd.total - 0.58) < 1e-9


def test_explanation_uses_real_shared_tags():
    a = ent("a", "A", "movie", ["whimsical", "pastel"])
    prof = TasteProfile.from_seeds([a])
    cand = ent("c", "C", "book", ["whimsical", "obscure-tag"])
    why = explain(cand, prof, [])
    assert "whimsical" in why
    assert "obscure-tag" not in why


def test_incoherent_pick_is_dropped():
    seed = ent("s", "Seed", "movie", ["quiet", "calm"])
    prof = TasteProfile.from_seeds([seed])
    off = ent("off", "Off Taste", "restaurant", ["quantum", "golf", "neon"], pop=0.1)
    pick = choose_pick([(off, 0.05)], prof, [], set())
    assert pick is None, "a pick with no shared tags and no taste-graph affinity must be dropped"


def test_high_affinity_cross_domain_pick_is_chosen():
    # Live-backend case: cross-domain tag vocabularies barely overlap, so a
    # pick may share no tags yet carry a strong taste-graph affinity.
    seed = ent("s", "Seed", "movie", ["quiet", "calm"])
    prof = TasteProfile.from_seeds([seed])
    xd = ent("xd", "Cross Domain", "restaurant", ["quantum", "golf", "neon"], pop=0.5)
    pick = choose_pick([(xd, 0.92)], prof, [], set())
    assert pick is not None and pick.entity.id == xd.id


def test_coherent_pick_is_chosen():
    seed = ent("s", "Seed", "movie", ["quiet", "calm"])
    prof = TasteProfile.from_seeds([seed])
    on = ent("on", "On Taste", "restaurant", ["quiet", "calm", "warm"], pop=0.7)
    pick = choose_pick([(on, 0.5)], prof, [], set())
    assert pick is not None and pick.entity.id == on.id
    assert pick.score.total >= MIN_COHERENCE


# --------------------------------------------------------------------------
# Itinerary assembly
# --------------------------------------------------------------------------

def test_date_night_plan_coherent_and_filled():
    b = FixtureBackend()
    seeds = [BY_SLUG["wes-anderson"], BY_SLUG["radiohead"]]
    plan = build_plan(b, seeds, occasion="date_night", city="Paris")
    by_label = {s.label: s for s in plan.steps}
    assert by_label["The film"].pick.entity.id == BY_SLUG["the-grand-budapest-hotel"].id
    assert by_label["Dinner"].pick.entity.id == BY_SLUG["cafe-lumen"].id
    assert plan.filled >= 5, f"expected >=5 filled slots, got {plan.filled}"


def test_food_crawl_never_repeats_a_pick():
    b = FixtureBackend()
    seeds = [BY_SLUG["everything-everywhere-all-at-once"], BY_SLUG["kendrick-lamar"]]
    plan = build_plan(b, seeds, occasion="friends_visiting")
    rest = [s.pick.entity.id for s in plan.steps
            if s.entity_type == "restaurant" and s.pick is not None]
    assert len(rest) == len(set(rest)), "restaurant slots must not repeat an entity"
    assert plan.filled >= 4


def test_plan_json_structure_and_fixture_label():
    b = FixtureBackend()
    seeds = [BY_SLUG["perfect-days"], BY_SLUG["brian-eno"]]
    plan = build_plan(b, seeds, occasion="solo_recharge")
    d = plan.as_dict()
    assert d["occasion"] == "solo_recharge"
    assert len(d["steps"]) == 5
    assert "fixture" in d["data_source"]
    md = plan.to_markdown()
    assert "fixture" in md.lower()
    assert "Perfect Days" in md
    filled = [s for s in d["steps"] if s["pick"]]
    assert filled and "coherence" in filled[0]["pick"]


# --------------------------------------------------------------------------
# Live Qloo client (mocked transport — no network)
# --------------------------------------------------------------------------

class FakeTransport:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        return self.status, self.payload


def test_live_client_search_request_and_parse():
    payload = {"success": True, "results": [
        {"entity_id": "urn:entity:movie:amelie", "name": "Amélie",
         "type": "movie", "popularity": 0.9,
         "tags": [{"name": "Whimsical", "tag_id": "t1"}]},
    ]}
    t = FakeTransport(payload)
    client = QlooClient(api_key="test-key", transport=t)
    hits = client.search("amelie")
    url, headers = t.calls[0]
    assert url.startswith("https://api.qloo.com/search?")
    assert "query=amelie" in url
    assert headers["X-Api-Key"] == "test-key"
    assert hits and hits[0][0].name == "Amélie"
    assert hits[0][0].tags == ("whimsical",)


def test_live_client_insights_request_and_parse():
    payload = {"success": True, "results": {"entities": [
        {"entity_id": "urn:entity:restaurant:cafe-lumen", "name": "Café Lumen",
         "type": "restaurant", "popularity": 0.8,
         "tags": [{"name": "Candle Lit"}, {"name": "Intimate"}]},
        {"entity_id": "urn:entity:person:wes-anderson", "name": "Wes Anderson",
         "type": "person"},
    ]}}
    t = FakeTransport(payload)
    client = QlooClient(api_key="test-key", transport=t)
    hits = client.related(["urn:entity:person:wes-anderson"], "restaurant", limit=5)
    url, _ = t.calls[0]
    assert "/v2/insights/" in url
    assert "filter.type=urn%3Aentity%3Aplace" in url
    assert "signal.interests.entities=urn%3Aentity%3Aperson%3Awes-anderson" in url
    assert "take=5" in url
    # the seed itself is filtered out of its own recommendations
    assert len(hits) == 1
    assert hits[0][0].tags == ("candle-lit", "intimate")


def test_live_client_missing_key_is_a_clear_error():
    saved = os.environ.pop("QLOO_API_KEY", None)
    try:
        try:
            QlooClient(api_key=None, transport=FakeTransport({}))
            raise AssertionError("expected QlooConfigError")
        except QlooConfigError as e:
            assert "QLOO_API_KEY" in str(e)
    finally:
        if saved is not None:
            os.environ["QLOO_API_KEY"] = saved


def test_live_client_http_error_raises():
    t = FakeTransport({"message": "boom"}, status=500)
    client = QlooClient(api_key="k", transport=t)
    try:
        client.search("x")
        raise AssertionError("expected QlooAPIError")
    except QlooAPIError as e:
        assert e.status == 500
        assert "boom" in str(e)


# --------------------------------------------------------------------------
# Backend selection + CLI
# --------------------------------------------------------------------------

def test_backend_selection_prefers_fixture_offline():
    backend, _ = select_backend(True)
    assert isinstance(backend, FixtureBackend)


def test_backend_selection_without_key_falls_back_with_notice():
    saved = os.environ.pop("QLOO_API_KEY", None)
    try:
        backend, notice = select_backend(False)
        assert isinstance(backend, FixtureBackend)
        assert "QLOO_API_KEY" in notice
    finally:
        if saved is not None:
            os.environ["QLOO_API_KEY"] = saved


def test_cli_free_text_offline(capsys=None):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_main(["I love Wes Anderson films and Radiohead — plan my Friday night",
                       "--offline"])
    assert rc == 0
    out = buf.getvalue()
    assert "VibePilot" in out
    assert "Radiohead" in out


def test_cli_structured_seeds_json():
    import contextlib
    import io
    import json as _json
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli_main(["--seeds", "Perfect Days, Brian Eno",
                       "--occasion", "solo_recharge", "--offline",
                       "--format", "json"])
    assert rc == 0
    d = _json.loads(buf.getvalue())
    assert d["occasion"] == "solo_recharge"
    assert len(d["seeds"]) == 2
