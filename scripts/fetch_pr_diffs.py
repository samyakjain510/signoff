"""Fetch size info and the full diff for each sampled public PR, read-only, via `gh`.

Usage:
    python3 scripts/fetch_pr_diffs.py data/public/aidev_sample.jsonl data/public/aidev_diffs [--max-kb 300]

Writes <out_dir>/<pr_id>.diff and <out_dir>/index.jsonl (one row per PR with
status: ok, too_large, or error, plus additions/deletions/changed_files).
Re-running skips PRs already fetched.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", "api", *args], capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sample")
    ap.add_argument("out_dir")
    ap.add_argument("--max-kb", type=int, default=300)
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.jsonl"
    done = set()
    if index_path.exists():
        done = {json.loads(l)["pr_id"] for l in index_path.open()}

    rows = [json.loads(l) for l in open(args.sample)]
    with index_path.open("a") as idx:
        for i, r in enumerate(rows, 1):
            if r["pr_id"] in done:
                continue
            m = re.match(r"https://github.com/([^/]+/[^/]+)/pull/(\d+)", r["html_url"])
            repo, num = m.group(1), m.group(2)
            row = {"pr_id": r["pr_id"], "repo": repo, "number": int(num)}
            meta = gh(f"repos/{repo}/pulls/{num}")
            if meta.returncode != 0:
                row.update(status="error", error=meta.stderr.strip()[:200])
            else:
                j = json.loads(meta.stdout)
                row.update(additions=j["additions"], deletions=j["deletions"],
                           changed_files=j["changed_files"], merged=j.get("merged"))
                diff = gh("-H", "Accept: application/vnd.github.diff", f"repos/{repo}/pulls/{num}")
                if diff.returncode != 0:
                    row.update(status="error", error=diff.stderr.strip()[:200])
                elif len(diff.stdout) > args.max_kb * 1024:
                    row.update(status="too_large", diff_kb=round(len(diff.stdout) / 1024))
                else:
                    (out / f"{r['pr_id']}.diff").write_text(diff.stdout)
                    row.update(status="ok", diff_kb=round(len(diff.stdout) / 1024, 1))
            idx.write(json.dumps(row) + "\n")
            idx.flush()
            if i % 50 == 0:
                print(f"{i}/{len(rows)}", flush=True)
    rows_out = [json.loads(l) for l in index_path.open()]
    counts: dict[str, int] = {}
    for r in rows_out:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("done:", counts)


if __name__ == "__main__":
    main()
