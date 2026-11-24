"""Judge two descriptions of each of Samyak's commits against the diff, PM scope:
the tool's summary (Haiku) and the agent's own commit message.

Uses judge v2 (prompts/judge.md), the version that passed calibration on held-out PRs.

Usage: python3 scripts/judge_own.py [tool|msg|both]   -> data/eval/judge_own.jsonl
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import diffs, llm  # noqa: E402

REPOS = ["portfolio", "ktech-interviews"]
OUT = ROOT / "data" / "eval" / "judge_own.jsonl"


def change_text(ch: dict) -> str:
    path = Path(ch["diff_path"])
    text, omitted, _ = diffs.fit(path.read_text(errors="replace") if path.exists() else "")
    files = "\n".join(f"  {f['status']} {f['path']} (+{f.get('additions')}/-{f.get('deletions')})" for f in ch["files"])
    left = "\n".join(f"  {o}" for o in omitted) or "  (none)"
    return f"Files changed:\n{files}\n\nFiles left out of the diff below:\n{left}\n\nDiff:\n{text}"


def items(which: str) -> list[dict]:
    out = []
    for repo in REPOS:
        d = ROOT / "data" / "eval" / repo
        changes = [json.loads(l) for l in open(d / "changes.jsonl")]
        reviews = {}
        if (d / "reviews.jsonl").exists():
            for l in open(d / "reviews.jsonl"):
                r = json.loads(l)
                if "out" in r:
                    reviews[r["id"]] = r["out"]
        for ch in changes:
            if which in ("msg", "both"):
                out.append({"id": f"{repo}:{ch['id']}:msg", "desc": ch["agent_text"], "ch": ch})
            if which in ("tool", "both") and ch["id"] in reviews:
                out.append({"id": f"{repo}:{ch['id']}:tool", "desc": reviews[ch["id"]]["summary"], "ch": ch})
    return out


def run(which: str) -> None:
    system = (ROOT / "prompts" / "judge.md").read_text()
    schema = (ROOT / "prompts" / "judge_schema.json").read_text()

    def work(it: dict) -> dict:
        text = f"SCOPE: pm\n\nDESCRIPTION:\n{it['desc']}\n\nCHANGE:\n{change_text(it['ch'])}"
        return {"id": it["id"], **llm.call(system, schema, text, model="sonnet", effort="medium")}

    llm.run_batch(items(which), work, OUT, workers=3, describe=lambda r: r["out"]["label"])


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "both")
