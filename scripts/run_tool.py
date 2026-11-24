"""Run the tool (Haiku) on the prepared changes of Samyak's repos.

Usage: python3 scripts/run_tool.py   -> data/eval/<repo>/reviews.jsonl (resumable)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import llm, review  # noqa: E402

for repo in ["portfolio", "ktech-interviews"]:
    d = ROOT / "data" / "eval" / repo
    changes = [json.loads(l) for l in open(d / "changes.jsonl")]
    print(f"== {repo}", flush=True)
    llm.run_batch(changes, lambda ch: review.review(ch, model="haiku"), d / "reviews.jsonl", workers=3,
                  describe=lambda r: f"{len(r['out']['decisions'])} decisions")
