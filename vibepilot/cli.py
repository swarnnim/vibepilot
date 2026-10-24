"""VibePilot command line.

Examples:
    vibepilot "I love Wes Anderson films and Radiohead — plan my Friday night"
    vibepilot "My friends are visiting and love Kendrick Lamar — food crawl"
    vibepilot --seeds "Perfect Days, Brian Eno" --occasion solo_recharge
    vibepilot --seeds "Wes Anderson, Radiohead" --city Paris --format json

Backend selection: live Qloo when ``QLOO_API_KEY`` is set, the bundled
fixture taste-graph otherwise (or with ``--offline``). The plan itself
always states which data it used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import textparse
from .fixtures import FixtureBackend
from .planner import OCCASIONS, build_plan
from .qloo_client import QlooClient, QlooConfigError


def select_backend(offline: bool):
    """Return (backend, notice). Falls back to fixtures with a clear notice."""
    if offline:
        return FixtureBackend(), "offline mode requested — using fixture taste-graph"
    if os.environ.get("QLOO_API_KEY"):
        try:
            return QlooClient(), ""
        except QlooConfigError as e:
            return FixtureBackend(), f"{e} Falling back to fixture taste-graph."
    return (
        FixtureBackend(),
        "QLOO_API_KEY is not set — using the bundled fixture taste-graph "
        "(offline demo data). Set QLOO_API_KEY to plan from the live Qloo graph.",
    )


def seeds_from_names(names: str, backend):
    seeds, missed = [], []
    for name in (n.strip() for n in names.split(",")):
        if not name:
            continue
        hits = backend.search(name, limit=3)
        if hits and hits[0][1] >= 0.45:
            seeds.append(hits[0][0])
        else:
            missed.append(name)
    return seeds, missed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="vibepilot",
        description="One line of taste in — a coherent, Qloo-powered plan out.",
    )
    ap.add_argument("prompt", nargs="?", default="",
                    help='free text, e.g. "I love Wes Anderson films and Radiohead — plan my Friday night"')
    ap.add_argument("--seeds", default="",
                    help='comma-separated seed names, e.g. "Wes Anderson, Radiohead"')
    ap.add_argument("--city", default="", help="city preference (soft — local picks win ties)")
    ap.add_argument("--occasion", choices=sorted(OCCASIONS), default="",
                    help="plan template (auto-detected from the prompt when omitted)")
    ap.add_argument("--offline", action="store_true",
                    help="force the bundled fixture taste-graph")
    ap.add_argument("--format", choices=("md", "json"), default="md", dest="fmt")
    ap.add_argument("--out", default="", help="write the plan to this file instead of stdout")
    args = ap.parse_args(argv)

    backend, notice = select_backend(args.offline)
    if notice:
        print(f"[vibepilot] {notice}", file=sys.stderr)

    if args.seeds:
        seeds, missed = seeds_from_names(args.seeds, backend)
        for m in missed:
            print(f"[vibepilot] could not resolve seed: {m!r}", file=sys.stderr)
        occasion = args.occasion or "date_night"
        city = args.city
    elif args.prompt:
        seeds = textparse.resolve_seeds(args.prompt, backend)
        occasion = args.occasion or textparse.detect_occasion(args.prompt)
        known = {e.city for e in backend.all_entities()}
        city = args.city or textparse.detect_city(args.prompt, known)
    else:
        ap.print_usage(sys.stderr)
        print("error: give a prompt or --seeds", file=sys.stderr)
        return 2

    if not seeds:
        print("error: no seeds could be resolved from that input — "
              "try naming a film, artist, book or place you love.", file=sys.stderr)
        return 2

    plan = build_plan(backend, seeds, occasion=occasion, city=city)
    rendered = json.dumps(plan.as_dict(), indent=2) if args.fmt == "json" else plan.to_markdown()
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
        print(f"[vibepilot] plan written to {args.out}", file=sys.stderr)
    else:
        print(rendered)
    return 0
