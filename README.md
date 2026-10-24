# VibePilot — an agent with a sense of taste

**Built for the Qloo Agentic Hackathon on Devpost.**

> "I love Wes Anderson films and Radiohead — plan my Friday night."
>
> One line in. A whole evening out — the look, the neighborhood, dinner,
> a film, the soundtrack home, and a book for the shelf — where every pick
> shares the same taste DNA, and every pick *says why it belongs*.

## The problem: agents are culturally blind

Today's agents can reason, plan and book — but they have no idea what
*goes with what*. Ask a generic agent to plan a night around your love of
Wes Anderson and it will hand you five independent top-10 lists: a popular
restaurant, a popular film, a popular playlist, stapled together. The
lists are fine. The evening is incoherent. Nothing rhymes.

Culture doesn't work in silos. The person who loves symmetrical, pastel,
melancholic films also tends to love a certain kind of bistro, a certain
kind of novel, a certain neighborhood at dusk. That cross-domain structure
— *taste* — is exactly what Qloo's graph encodes across 250M+ entities in
music, film, dining, fashion, travel, books and brands.

**VibePilot gives an agent that cultural intelligence.** It resolves one
line of taste into Qloo entities, expands those seeds *across* domains
through the taste graph, and then — the part a raw recommender doesn't
do — runs a **coherence engine** over the candidates so the final plan
feels like one taste, not five lists.

## What it does

```
$ vibepilot "I love Wes Anderson films and Radiohead — plan my Friday night" --city Paris

# VibePilot — Date night in Paris
Seeds: Wes Anderson · Radiohead
Taste profile: whimsical · pastel · meticulous · melancholic · symmetrical

17:00 — The look: Jacquemus
  Why: shares "pastel, whimsical" with your seeds.
17:45 — Set the scene: Montmartre, Paris
  Why: shares "whimsical" with your seeds; echoes Jacquemus through "parisian, whimsical".
19:00 — Dinner: Café Lumen
  Why: shares "meticulous, whimsical" with your seeds; echoes Jacquemus through "parisian, whimsical".
21:15 — The film: The Grand Budapest Hotel
  Why: shares "melancholic, meticulous, pastel" with your seeds.
23:00 — The soundtrack home: Sufjan Stevens
  Why: shares "melancholic, meticulous, whimsical" with your seeds; echoes
       The Grand Budapest Hotel through "melancholic, meticulous".
Take home: The Elegance of the Hedgehog
```

Three occasion templates ship today:

| Occasion | How it triggers | Slots |
|---|---|---|
| **Date night** | "date night", a partner mention, or default | the look → set the scene → dinner → film → soundtrack → take-home book |
| **Solo recharge** | "solo", "recharge", "me time" | slow start → read → wander → one film → wind-down music |
| **Friends visiting** | "friends visiting", "food crawl" | first bite → main event → walk it off → late-night finish → playlist |

Output is Markdown for humans or JSON for other agents (`--format json`),
so VibePilot can sit inside a larger agent stack as a "taste subroutine":
give it seeds, get back a coherent, self-explaining plan object.

## How it works

### 1. Seed resolution — free text → Qloo entities
The line is split into candidate phrases, planning filler is stripped,
and each phrase is resolved through Qloo's entity search (`GET /search`).
"Wes Anderson films" and "Radiohead" become entity URNs — the entry
points into the taste graph.

### 2. Cross-domain expansion — Qloo insights
For each itinerary slot, VibePilot queries Qloo's Insights API
(`GET /v2/insights/`) with the seed URNs as `signal.interests.entities`
and `filter.type` set to the slot's domain — `urn:entity:restaurant`,
`urn:entity:movie`, `urn:entity:music_artist`, `urn:entity:book`,
`urn:entity:fashion_brand`, `urn:entity:destination`. This is the
non-obvious move: the *same* two seeds fan out into six cultural domains
through one graph, instead of six disconnected searches.

### 3. The coherence engine — the creative core
Candidates from Qloo arrive with **taste tags**. VibePilot distills the
seeds into a weighted *taste profile* (a tag in both seeds counts double),
then fills slots greedily. Each candidate is scored:

```
coherence = 0.60 × seed affinity      (its tags vs. the seed profile)
          + 0.30 × pairwise coherence (its tags vs. picks already chosen)
          + 0.10 × popularity         (tiebreak toward loved things)
```

Two design choices matter:

* **Pairwise coherence.** A pick isn't just "close to your taste" — it
  must rhyme with the picks already in the plan. That's why the bistro
  echoes the film, and the book echoes the bistro.
* **An honest floor.** Picks scoring under 0.16 are *dropped*, and the
  slot is left explicitly open ("no pick in the graph cleared the
  coherence bar") rather than padded with a random crowd-pleaser. A
  tasteful gap beats an incoherent filler — and in JSON mode downstream
  agents can see and handle the gap.

Every pick's explanation is generated from the actual shared tags —
"shares 'melancholic, meticulous' with your seeds; echoes The Grand
Budapest Hotel through 'pastel, whimsical'" — so a human can audit *why*
the agent thinks these things belong together.

### Architecture

```
vibepilot/
  cli.py          CLI: prompt/--seeds in, Markdown/JSON plan out
  textparse.py    free text -> seed phrases, occasion + city detection
  backend.py      TasteBackend interface (search + related)
  qloo_client.py  live backend: Qloo /search + /v2/insights, X-Api-Key auth
  fixtures.py     offline backend: bundled 58-entity mini taste-graph
  coherence.py    taste profile, scoring, greedy selection, explanations
  planner.py      occasion templates, slot assembly, Markdown/JSON render
  models.py       the Entity model shared by both backends
```

Both backends implement the same two-operation interface, so the planner,
coherence engine and tests never know (or care) which graph they're
talking to. Plans always print their data source — live Qloo output and
fixture output are labeled differently, on purpose.

## Quickstart

**Offline demo (no key, no network)** — runs against the bundled fixture
taste-graph, a hand-built 58-entity stand-in with three taste clusters:

```bash
./demo.sh                     # 3 scenarios end-to-end
python3 run_tests.py          # 24 tests, all offline
python3 -m vibepilot "I love Wes Anderson films and Radiohead — plan my Friday night" --offline
```

**Live mode** — plan from the real Qloo graph:

```bash
export QLOO_API_KEY=<your key>
python3 -m vibepilot "I love Wes Anderson films and Radiohead — plan my Friday night"
python3 -m vibepilot --seeds "Perfect Days, Brian Eno" --occasion solo_recharge --format json
```

Pure Python 3 standard library. No pip installs, no other services, $0 to
run in offline mode.

## Why this matters

* **For people:** planning a night that *feels like you* currently takes
  an hour of tab-hopping across review sites that don't know each other.
  VibePilot does it from one sentence, and explains itself.
* **For agents:** taste is a missing primitive. Any agent that books,
  recommends, gifts, or plans on someone's behalf needs to know not just
  what they like, but what *fits together*. VibePilot packages that as a
  small, testable, JSON-speaking component.
* **For Qloo:** this is the taste graph used the way it wants to be used —
  not as a lookup table, but as the connective tissue between domains,
  with tags doing real algorithmic work (scoring, filtering, explaining).

## Honest limitations

* **The fixture graph is small** (58 entities, 3 taste clusters) and
  hand-built; it demonstrates the full pipeline faithfully but its
  recommendations are illustrative. Live mode removes this limit — the
  coherence engine is graph-size-agnostic.
* **Live mode needs your own Qloo API key** (`QLOO_API_KEY`). Request
  construction, auth headers and response parsing are covered by tests
  with a mocked transport; no key is bundled, by design.
* **Qloo search results are tag-light** compared to insights results, so
  in live mode the seed profile can be thinner than the candidates'
  vocabulary; pairwise coherence compensates once the first pick lands.
* **Tag-overlap is a proxy for taste**, not taste itself — Qloo's affinity
  scores do the heavy graph lifting; the coherence layer adds
  cross-pick consistency and explainability on top.
* City is a **soft preference** (local picks win ties), not a hard
  geographic filter, in both backends.

## Tests

`python3 run_tests.py` — 24 stdlib-only tests, zero network: fixture
search and cross-domain expansion, free-text seed resolution (including
the word-boundary regression that kept the film *Her* from being detected
inside "Everyw**her**e"), exact coherence math, the incoherent-pick drop
rule, the no-repeat rule for food crawls, live-client URL/header
construction and response parsing against a mocked transport, and CLI
end-to-end runs.
