#!/usr/bin/env bash
# VibePilot end-to-end demo — fully offline (fixture taste-graph), no API key.
# For live mode: export QLOO_API_KEY=... and drop --offline.
set -euo pipefail
cd "$(dirname "$0")"

echo "==================================================================="
echo "SCENARIO 1 — Date night, from one free-text line (film + music seeds)"
echo "==================================================================="
python3 -m vibepilot "I love Wes Anderson films and Radiohead — plan my Friday night" --city Paris --offline

echo
echo "==================================================================="
echo "SCENARIO 2 — Solo recharge, structured seeds (a film + ambient music)"
echo "==================================================================="
python3 -m vibepilot --seeds "Perfect Days, Brian Eno" --occasion solo_recharge --offline

echo
echo "==================================================================="
echo "SCENARIO 3 — Friends visiting: a food crawl from maximalist taste"
echo "==================================================================="
python3 -m vibepilot "My friends are visiting and we love Everything Everywhere All at Once and Kendrick Lamar — plan a food crawl" --offline
