"""Run the tool a second time on 20 of the 60 commits and compare outcomes.

Usage: python3 scripts/stability.py run | report
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import llm, policy, review, stats  # noqa: E402

REPOS = ["portfolio", "ktech-interviews"]
OUT = ROOT / "data" / "eval" / "rerun.jsonl"


def changes() -> list[dict]:
    out = []
    for repo in REPOS:
        for l in open(ROOT / "data" / "eval" / repo / "changes.jsonl"):
            ch = json.loads(l)
            ch["id"] = f"{repo}:{ch['id']}"
            out.append(ch)
    return random.Random(7).sample(sorted(out, key=lambda c: c["id"]), 20)


def first_run() -> dict[str, dict]:
    got = {}
    for repo in REPOS:
        for l in open(ROOT / "data" / "eval" / repo / "reviews.jsonl"):
            r = json.loads(l)
            if "out" in r:
                got[f"{repo}:{r['id']}"] = r["out"]
    return got


def run() -> None:
    llm.run_batch(changes(), lambda ch: review.review(ch, model="haiku"), OUT, workers=3,
                  describe=lambda r: f"{len(r['out']['decisions'])} decisions")


def report() -> None:
    pol = policy.load()
    a = first_run()
    b = {json.loads(l)["id"]: json.loads(l)["out"] for l in OUT.open() if "out" in json.loads(l)}
    ids = [c["id"] for c in changes() if c["id"] in a and c["id"] in b]
    acts = [(policy.change_action(pol, a[i]["decisions"]), policy.change_action(pol, b[i]["decisions"])) for i in ids]
    held = [(x == "sign-off", y == "sign-off") for x, y in acts]
    nd = [(len(a[i]["decisions"]), len(b[i]["decisions"])) for i in ids]
    res = {
        "commits": len(ids),
        "same_outcome": stats.pct(sum(x == y for x, y in acts), len(ids)),
        "same_hold_decision": stats.pct(sum(x == y for x, y in held), len(ids)),
        "held_first_run": sum(x for x, _ in held), "held_second_run": sum(y for _, y in held),
        "outcome_pairs": {f"{x}->{y}": n for (x, y), n in sorted(Counter(acts).items())},
        "decisions_first_run": sum(x for x, _ in nd), "decisions_second_run": sum(y for _, y in nd),
        "mean_abs_difference_in_decisions": round(sum(abs(x - y) for x, y in nd) / len(nd), 1),
    }
    (ROOT / "results" / "stability.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    {"run": run, "report": report}[sys.argv[1]]()
