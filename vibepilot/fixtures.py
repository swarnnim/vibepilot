"""A bundled mini taste-graph for offline demos and tests.

This is a *hand-built stand-in* for Qloo's 250M-entity graph: 58 entities
across film, music, dining, books, fashion and destinations, organized in
three taste clusters (auteur-whimsical, maximalist-energy, calm-recharge)
with shared taste tags and explicit affinity edges. It exists so the full
VibePilot pipeline — seed resolution, cross-domain expansion, coherence
scoring, itinerary assembly — runs with zero network and zero API key.

Everything produced through this backend is labeled as fixture data in the
plan output. It is a demo graph, not real Qloo data.
"""

from __future__ import annotations

import re

from .backend import TasteBackend
from .models import Entity, normalize_tag

# ---------------------------------------------------------------------------
# Entity table: (id slug, name, type, tags, popularity, city, blurb)
# ---------------------------------------------------------------------------

_ROWS = [
    # --- people (typical seeds) -------------------------------------------
    ("wes-anderson", "Wes Anderson", "person",
     ["symmetrical", "whimsical", "pastel", "meticulous", "deadpan"], 0.92, "",
     "director of meticulously symmetrical, pastel storybook films"),
    ("sofia-coppola", "Sofia Coppola", "person",
     ["melancholic", "wistful", "pastel", "nocturnal", "tender"], 0.78, "",
     "director of wistful, neon-and-pastel drift films"),

    # --- cluster A: auteur whimsical --------------------------------------
    ("the-grand-budapest-hotel", "The Grand Budapest Hotel", "movie",
     ["symmetrical", "whimsical", "pastel", "meticulous", "melancholic"], 0.95, "",
     "a storybook hotel caper composed like a dollhouse diorama"),
    ("moonrise-kingdom", "Moonrise Kingdom", "movie",
     ["whimsical", "nostalgic", "earnest", "pastel", "meticulous"], 0.88, "",
     "two earnest runaways in a hand-stitched 1965 New England"),
    ("amelie", "Amélie", "movie",
     ["whimsical", "parisian", "romantic", "quirky", "saturated"], 0.90, "",
     "a shy Parisian matchmaker in a saturated green-and-red Montmartre"),
    ("lost-in-translation", "Lost in Translation", "movie",
     ["melancholic", "nocturnal", "wistful", "tender", "urban"], 0.87, "",
     "two insomniacs drifting through nocturnal Tokyo"),
    ("in-the-mood-for-love", "In the Mood for Love", "movie",
     ["melancholic", "romantic", "meticulous", "saturated", "wistful"], 0.85, "",
     "restrained longing shot in saturated reds and greens"),
    ("her", "Her", "movie",
     ["melancholic", "tender", "soft", "futuristic", "philosophical"], 0.84, "",
     "a soft-focus near-future love story in warm pastels"),

    ("radiohead", "Radiohead", "music_artist",
     ["melancholic", "angular", "atmospheric", "intricate", "nocturnal"], 0.93, "",
     "angular, atmospheric art-rock for beautiful unease"),
    ("sufjan-stevens", "Sufjan Stevens", "music_artist",
     ["whimsical", "earnest", "orchestral", "melancholic", "meticulous"], 0.82, "",
     "orchestral folk arranged with obsessive, tender detail"),
    ("the-national", "The National", "music_artist",
     ["melancholic", "brooding", "literary", "nocturnal"], 0.80, "",
     "brooding, literary baritone rock for late hours"),
    ("belle-and-sebastian", "Belle and Sebastian", "music_artist",
     ["whimsical", "twee", "literary", "earnest"], 0.72, "",
     "twee, bookish indie-pop with a wink"),
    ("portishead", "Portishead", "music_artist",
     ["nocturnal", "melancholic", "cinematic", "atmospheric"], 0.76, "",
     "cinematic trip-hop, all smoke and strings"),
    ("nick-drake", "Nick Drake", "music_artist",
     ["melancholic", "pastoral", "gentle", "wistful"], 0.74, "",
     "pastoral fingerpicked folk, gentle and wistful"),

    ("cafe-lumen", "Café Lumen", "restaurant",
     ["whimsical", "intimate", "meticulous", "parisian", "candlelit"], 0.80, "Paris",
     "a jewel-box Parisian bistro plating every dish like a miniature"),
    ("sable-and-smoke", "Sable & Smoke", "restaurant",
     ["nocturnal", "moody", "cinematic", "intimate"], 0.77, "New York",
     "a candlelit basement kitchen of smoked, moody small plates"),
    ("nonnas-table", "Nonna's Table", "restaurant",
     ["earnest", "nostalgic", "rustic", "warm"], 0.75, "Rome",
     "hand-cut pasta and red-check nostalgia, no shortcuts"),
    ("the-nightjar", "The Nightjar", "restaurant",
     ["nocturnal", "quirky", "intimate", "cinematic"], 0.73, "London",
     "a speakeasy supper club hidden behind a bookcase door"),

    ("the-little-prince", "The Little Prince", "book",
     ["whimsical", "earnest", "philosophical", "tender"], 0.88, "",
     "a philosophical fable about seeing with the heart"),
    ("kafka-on-the-shore", "Kafka on the Shore", "book",
     ["dreamlike", "melancholic", "surreal", "literary"], 0.83, "",
     "Murakami's dreamlike dual odyssey of fate and talking cats"),
    ("norwegian-wood", "Norwegian Wood", "book",
     ["melancholic", "nostalgic", "literary", "wistful"], 0.81, "",
     "Murakami's nostalgic novel of young love and loss in 1960s Tokyo"),
    ("the-elegance-of-the-hedgehog", "The Elegance of the Hedgehog", "book",
     ["parisian", "philosophical", "whimsical", "literary"], 0.70, "",
     "a Parisian concierge's secret philosophical life"),

    ("jacquemus", "Jacquemus", "fashion_brand",
     ["whimsical", "pastel", "surreal", "parisian"], 0.79, "",
     "surreal pastel tailoring and tiny bags, worn with a grin"),
    ("apc", "A.P.C.", "fashion_brand",
     ["meticulous", "parisian", "minimal", "muted"], 0.74, "",
     "meticulous Parisian minimalism in muted tones"),
    ("margaret-howell", "Margaret Howell", "fashion_brand",
     ["pastoral", "meticulous", "muted", "gentle"], 0.66, "",
     "pastoral British tailoring, quiet and exact"),

    ("montmartre-paris", "Montmartre, Paris", "destination",
     ["whimsical", "parisian", "romantic", "nostalgic"], 0.90, "Paris",
     "cobblestone lanes, accordion corners and the Sacré-Cœur at dusk"),
    ("budapest-district-vii", "Budapest's District VII", "destination",
     ["grand", "melancholic", "faded", "meticulous"], 0.76, "Budapest",
     "faded grand facades and ruin bars in the old Jewish quarter"),
    ("gion-kyoto", "Gion, Kyoto", "destination",
     ["meticulous", "nostalgic", "nocturnal", "quiet"], 0.85, "Kyoto",
     "lantern-lit wooden machiya streets at nightfall"),

    # --- cluster B: maximalist energy --------------------------------------
    ("everything-everywhere-all-at-once", "Everything Everywhere All at Once", "movie",
     ["maximalist", "surreal", "heartfelt", "chaotic", "inventive"], 0.91, "",
     "a maximalist multiverse hug with googly eyes"),
    ("mad-max-fury-road", "Mad Max: Fury Road", "movie",
     ["kinetic", "visceral", "relentless", "saturated"], 0.89, "",
     "a relentless two-hour chase in saturated desert orange"),
    ("spider-man-into-the-spider-verse", "Spider-Man: Into the Spider-Verse", "movie",
     ["kinetic", "colorful", "inventive", "playful"], 0.90, "",
     "a kinetic comic book exploded into color"),

    ("kendrick-lamar", "Kendrick Lamar", "music_artist",
     ["kinetic", "literary", "layered", "bold"], 0.92, "",
     "layered, literary rap with stadium voltage"),
    ("daft-punk", "Daft Punk", "music_artist",
     ["kinetic", "euphoric", "robotic", "nocturnal"], 0.88, "",
     "robotic disco euphoria for the small hours"),
    ("charli-xcx", "Charli XCX", "music_artist",
     ["kinetic", "neon", "chaotic", "playful", "bold"], 0.84, "",
     "neon brat-pop, chaotic and self-aware"),
    ("beyonce", "Beyoncé", "music_artist",
     ["bold", "maximalist", "joyful", "meticulous"], 0.93, "",
     "maximalist pop spectacle executed meticulously"),

    ("seoul-smoke-bbq", "Seoul Smoke BBQ", "restaurant",
     ["communal", "smoky", "interactive", "bold", "kinetic"], 0.82, "Los Angeles",
     "grill-it-yourself Korean BBQ, loud and communal"),
    ("taco-truck-el-sol", "Taco Truck El Sol", "restaurant",
     ["vibrant", "casual", "street", "colorful", "bold"], 0.78, "Mexico City",
     "al pastor carved off the trompo under string lights"),
    ("smash-and-sons", "Smash & Sons", "restaurant",
     ["bold", "casual", "loud", "playful"], 0.71, "New York",
     "double smash burgers and a jukebox stuck on loud"),

    ("kitchen-confidential", "Kitchen Confidential", "book",
     ["raw", "visceral", "culinary", "bold"], 0.80, "",
     "Bourdain's raw, visceral memoir of kitchen life"),
    ("the-hitchhikers-guide-to-the-galaxy", "The Hitchhiker's Guide to the Galaxy", "book",
     ["absurd", "playful", "surreal", "inventive"], 0.89, "",
     "absurd, playful sci-fi comedy — don't panic"),

    ("moschino", "Moschino", "fashion_brand",
     ["maximalist", "playful", "bold", "surreal"], 0.72, "",
     "maximalist fashion with its tongue firmly in cheek"),

    ("shinjuku-tokyo", "Shinjuku, Tokyo", "destination",
     ["neon", "kinetic", "dense", "nocturnal"], 0.91, "Tokyo",
     "neon canyons, six-seat bars and 3am ramen"),
    ("roma-norte-mexico-city", "Roma Norte, Mexico City", "destination",
     ["vibrant", "colorful", "street", "joyful"], 0.80, "Mexico City",
     "tree-lined, colorful streets of mezcal bars and bookshops"),

    # --- cluster C: calm recharge ------------------------------------------
    ("perfect-days", "Perfect Days", "movie",
     ["quiet", "ritual", "gentle", "observational"], 0.86, "",
     "Wenders' quiet ode to a Tokyo toilet cleaner's ritual days"),
    ("paterson", "Paterson", "movie",
     ["quiet", "poetic", "gentle", "observational"], 0.80, "",
     "a bus driver poet's quiet week, observed gently"),
    ("columbus", "Columbus", "movie",
     ["quiet", "architectural", "tender", "minimal"], 0.77, "",
     "a quiet, architectural two-hander about grief and buildings"),

    ("brian-eno", "Brian Eno", "music_artist",
     ["ambient", "spacious", "calm", "minimal"], 0.85, "",
     "ambient soundscapes engineered for spacious calm"),
    ("nils-frahm", "Nils Frahm", "music_artist",
     ["minimal", "spacious", "calm", "intricate"], 0.76, "",
     "felt-piano minimalism, intricate and unhurried"),
    ("khruangbin", "Khruangbin", "music_artist",
     ["warm", "groovy", "mellow", "pastoral"], 0.81, "",
     "warm, mellow global-funk grooves"),

    ("stillwater-tea-house", "Stillwater Tea House", "restaurant",
     ["calm", "ritual", "quiet", "meticulous"], 0.78, "Kyoto",
     "a hushed tea room where every pour is a small ceremony"),
    ("the-garden-cafe", "The Garden Café", "restaurant",
     ["calm", "pastoral", "light", "warm"], 0.73, "Copenhagen",
     "a greenhouse café of light, herbs and slow lunches"),

    ("the-little-book-of-hygge", "The Little Book of Hygge", "book",
     ["cozy", "warm", "calm", "ritual"], 0.75, "",
     "the Danish art of cozy, warm ritual"),
    ("when-breath-becomes-air", "When Breath Becomes Air", "book",
     ["reflective", "tender", "philosophical", "quiet"], 0.82, "",
     "a neurosurgeon's reflective, tender memoir on mortality"),
    ("the-essential-haiku", "The Essential Haiku", "book",
     ["minimal", "quiet", "nature", "reflective"], 0.68, "",
     "minimal verses of nature and stillness"),

    ("cos", "COS", "fashion_brand",
     ["minimal", "architectural", "calm", "muted"], 0.77, "",
     "architectural minimalism in calm, muted cloth"),

    ("philosophers-path-kyoto", "The Philosopher's Path, Kyoto", "destination",
     ["quiet", "reflective", "nature", "ritual"], 0.84, "Kyoto",
     "a canal-side walk of temples, cats and falling blossom"),
    ("nyhavn-copenhagen", "Nyhavn, Copenhagen", "destination",
     ["cozy", "calm", "colorful", "warm"], 0.83, "Copenhagen",
     "colorful harbor houses and the warm hum of hygge"),
    ("kew-gardens-london", "Kew Gardens, London", "destination",
     ["calm", "green", "nature", "spacious"], 0.80, "London",
     "spacious glasshouses and green calm in the city"),
]


def _urn(entity_type: str, slug: str) -> str:
    return f"urn:entity:{entity_type}:{slug}"


ENTITIES = [
    Entity(
        id=_urn(t, slug),
        name=name,
        type=t,
        tags=tuple(tags),
        popularity=pop,
        city=city,
        blurb=blurb,
    )
    for (slug, name, t, tags, pop, city, blurb) in _ROWS
]

BY_ID = {e.id: e for e in ENTITIES}
BY_SLUG = {e.id.rsplit(":", 1)[-1]: e for e in ENTITIES}

# ---------------------------------------------------------------------------
# Affinity edges: hand-set connections the tag overlap alone would underrate
# (a director and his film, a novelist and his city...). Symmetric, 0..1.
# ---------------------------------------------------------------------------

_EDGE_PAIRS = [
    ("wes-anderson", "the-grand-budapest-hotel", 1.00),
    ("wes-anderson", "moonrise-kingdom", 0.95),
    ("wes-anderson", "cafe-lumen", 0.65),
    ("wes-anderson", "jacquemus", 0.60),
    ("wes-anderson", "montmartre-paris", 0.60),
    ("wes-anderson", "sufjan-stevens", 0.62),
    ("sofia-coppola", "lost-in-translation", 0.95),
    ("sofia-coppola", "her", 0.60),
    ("the-grand-budapest-hotel", "budapest-district-vii", 0.85),
    ("the-grand-budapest-hotel", "cafe-lumen", 0.62),
    ("amelie", "montmartre-paris", 0.90),
    ("amelie", "the-elegance-of-the-hedgehog", 0.60),
    ("radiohead", "portishead", 0.70),
    ("radiohead", "the-national", 0.65),
    ("radiohead", "sable-and-smoke", 0.60),
    ("radiohead", "lost-in-translation", 0.55),
    ("radiohead", "the-nightjar", 0.52),
    ("kafka-on-the-shore", "norwegian-wood", 0.80),
    ("kafka-on-the-shore", "gion-kyoto", 0.45),
    ("nick-drake", "margaret-howell", 0.55),
    ("everything-everywhere-all-at-once", "spider-man-into-the-spider-verse", 0.60),
    ("everything-everywhere-all-at-once", "charli-xcx", 0.50),
    ("everything-everywhere-all-at-once", "the-hitchhikers-guide-to-the-galaxy", 0.65),
    ("kendrick-lamar", "kitchen-confidential", 0.40),
    ("kendrick-lamar", "seoul-smoke-bbq", 0.45),
    ("daft-punk", "shinjuku-tokyo", 0.60),
    ("beyonce", "moschino", 0.55),
    ("mad-max-fury-road", "smash-and-sons", 0.40),
    ("perfect-days", "philosophers-path-kyoto", 0.80),
    ("perfect-days", "stillwater-tea-house", 0.70),
    ("perfect-days", "the-essential-haiku", 0.60),
    ("paterson", "columbus", 0.65),
    ("brian-eno", "nils-frahm", 0.80),
    ("brian-eno", "kew-gardens-london", 0.50),
    ("brian-eno", "cos", 0.45),
    ("khruangbin", "the-garden-cafe", 0.55),
    ("the-little-book-of-hygge", "nyhavn-copenhagen", 0.85),
    ("the-little-book-of-hygge", "the-garden-cafe", 0.60),
]

EDGES: dict = {}
for _a, _b, _w in _EDGE_PAIRS:
    EDGES[(BY_SLUG[_a].id, BY_SLUG[_b].id)] = _w
    EDGES[(BY_SLUG[_b].id, BY_SLUG[_a].id)] = _w


def edge_weight(id_a: str, id_b: str) -> float:
    return EDGES.get((id_a, id_b), 0.0)


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str):
    return _WORD.findall(text.lower())


def _tag_overlap(a: Entity, b_tags: set) -> float:
    """Jaccard overlap between an entity's tags and a tag set."""
    at = set(a.tags)
    if not at or not b_tags:
        return 0.0
    return len(at & b_tags) / len(at | b_tags)


class FixtureBackend(TasteBackend):
    """Offline backend over the bundled mini taste-graph."""

    label = "bundled fixture taste-graph (offline demo data — not live Qloo)"

    def __init__(self, entities=None):
        self._entities = list(entities) if entities is not None else list(ENTITIES)

    def all_entities(self):
        return list(self._entities)

    # -- search -------------------------------------------------------------
    def search(self, query, entity_type=None, limit=5):
        q = query.strip().lower()
        if not q:
            return []
        q_tokens = set(_tokens(q))
        scored = []
        for e in self._entities:
            if entity_type and e.type != entity_type:
                continue
            name_l = e.name.lower()
            score = 0.0
            if name_l == q:
                score = 1.0
            elif q in name_l or name_l in q:
                score = 0.9
            else:
                name_tokens = set(_tokens(e.name))
                hit = len(q_tokens & name_tokens)
                if hit:
                    score = 0.45 + 0.45 * (hit / max(len(name_tokens), 1))
                else:
                    tag_hit = len(q_tokens & {normalize_tag(t) for t in e.tags})
                    if tag_hit:
                        score = 0.3 + 0.1 * tag_hit
            if score > 0:
                scored.append((e, round(score, 4)))
        scored.sort(key=lambda p: (-p[1], -p[0].popularity, p[0].name))
        return scored[:limit]

    # -- cross-domain expansion ----------------------------------------------
    def related(self, seed_ids, target_type, limit=8):
        local = {e.id: e for e in self._entities}
        seeds = [local[s] for s in seed_ids if s in local]
        if not seeds:  # fall back to the global table
            seeds = [BY_ID[s] for s in seed_ids if s in BY_ID]
        if not seeds:
            return []
        seed_tag_union: set = set()
        for s in seeds:
            seed_tag_union |= set(s.tags)
        seed_id_set = {s.id for s in seeds}
        out = []
        for e in self._entities:
            if e.type != target_type or e.id in seed_id_set:
                continue
            overlap = _tag_overlap(e, seed_tag_union)
            edge = max((edge_weight(e.id, s.id) for s in seeds), default=0.0)
            affinity = 0.60 * overlap + 0.30 * edge + 0.10 * e.popularity
            if affinity > 0.02:
                out.append((e, round(affinity, 4)))
        out.sort(key=lambda p: (-p[1], -p[0].popularity, p[0].name))
        return out[:limit]
