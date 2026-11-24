"""Turn the Phase 1 records of Samyak's two repos into tool input ("changes").

Uses the same request text the reference labels saw (label.requests_with_carry),
the same code-check findings and the same saved diffs, so the tool and the
labeler differ only in model and prompt.

Usage: python3 scripts/own_changes.py   -> data/eval/<repo>/changes.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import sources  # noqa: E402
from signoff.label import requests_with_carry  # noqa: E402

REPOS = ["portfolio", "ktech-interviews"]
DATA = ROOT / "data"


def build(repo: str) -> list[dict]:
    recs = [json.loads(l) for l in open(DATA / "records" / f"{repo}.jsonl")]
    checks = {json.loads(l)["sha"]: json.loads(l)["findings"] for l in open(DATA / "records" / f"{repo}.checks.jsonl")}
    reqs = requests_with_carry(repo)
    out = []
    for rec in recs:
        if rec["is_merge"]:
            continue
        req = reqs.get(rec["sha"], {"text": "", "carried": False})
        out.append(sources.make_change(
            id=rec["short"], kind="commit", title=rec["subject"], date=rec["date"], url="", agent=rec["agent"],
            agent_text=(rec["subject"] + "\n\n" + rec["body"]).strip(),
            spec=req["text"], spec_source="your messages in the Claude Code session" if req["text"] else "",
            spec_carried=req["carried"], files=rec["files"], findings=checks.get(rec["sha"], []),
            diff_path=DATA / "records" / repo / f"{rec['short']}.diff"))
    return out


if __name__ == "__main__":
    for repo in REPOS:
        changes = build(repo)
        d = DATA / "eval" / repo
        d.mkdir(parents=True, exist_ok=True)
        with (d / "changes.jsonl").open("w") as fh:
            for ch in changes:
                fh.write(json.dumps(ch) + "\n")
        print(repo, len(changes), "changes,", sum(1 for c in changes if c["spec"]), "with a request")
