"""Draw a reproducible sample of merged agent PRs that link to an issue, from AIDev.

AIDev (Li, Zhang, Hassan, MSR '26) is CC BY 4.0: https://huggingface.co/datasets/hao-li/AIDev
DuckDB reads only the needed columns of the remote Parquet files.

Usage:
    .venv/bin/python scripts/sample_aidev.py [--per-agent 60] [--seed 7] [--out data/public/aidev_sample.jsonl]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path

import duckdb

DATASET = "hao-li/AIDev"
APP_LANGUAGES = {
    "TypeScript", "JavaScript", "Python", "Go", "Ruby", "PHP", "Java", "Kotlin",
    "Swift", "Dart", "Rust", "C#", "Vue", "Svelte", "Elixir", "Scala",
}


def parquet_urls() -> dict[str, list[str]]:
    # curl, because python.org builds on macOS often lack a linked certificate store.
    raw = subprocess.run(
        ["curl", "-sf", f"https://datasets-server.huggingface.co/parquet?dataset={DATASET}"],
        capture_output=True, text=True, check=True,
    ).stdout
    files = json.loads(raw)["parquet_files"]
    urls: dict[str, list[str]] = defaultdict(list)
    for f in files:
        urls[f["config"]].append(f["url"])
    return urls


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-agent", type=int, default=60)
    ap.add_argument("--per-repo", type=int, default=2)
    ap.add_argument("--min-stars", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="data/public/aidev_sample.jsonl")
    args = ap.parse_args()

    urls = parquet_urls()
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")

    def src(config: str) -> str:
        return "read_parquet([" + ", ".join(f"'{u}'" for u in urls[config]) + "])"

    candidates = con.execute(f"""
        WITH linked AS (SELECT DISTINCT pr_id, issue_id FROM {src('related_issue')}),
             repos AS (SELECT id, full_name, language, CAST(stars AS INT) AS stars, license, is_forked
                       FROM {src('repository')})
        SELECT CAST(p.id AS VARCHAR) AS pr_id, p.number, p.agent, p.html_url, p.merged_at,
               r.full_name, r.language, r.stars, r.license,
               CAST(min(l.issue_id) AS VARCHAR) AS issue_id
        FROM {src('pull_request')} p
        JOIN linked l ON CAST(l.pr_id AS VARCHAR) = CAST(p.id AS VARCHAR)
        JOIN repos r ON CAST(r.id AS VARCHAR) = CAST(p.repo_id AS VARCHAR)
        WHERE p.merged_at IS NOT NULL
          AND lower(CAST(r.is_forked AS VARCHAR)) = 'false'
          AND r.stars >= {args.min_stars}
        GROUP BY ALL
    """).fetchall()
    cols = ["pr_id", "number", "agent", "html_url", "merged_at", "repo", "language", "stars", "license", "issue_id"]
    rows = [dict(zip(cols, c)) for c in candidates if c[6] in APP_LANGUAGES]

    # Stratified draw: N per agent, at most K per repo, fixed seed.
    rng = random.Random(args.seed)
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r["pr_id"]):
        by_agent[r["agent"]].append(r)
    sample = []
    for agent in sorted(by_agent):
        pool = by_agent[agent][:]
        rng.shuffle(pool)
        per_repo: dict[str, int] = defaultdict(int)
        picked = 0
        for r in pool:
            if picked == args.per_agent:
                break
            if per_repo[r["repo"]] >= args.per_repo:
                continue
            per_repo[r["repo"]] += 1
            sample.append(r)
            picked += 1

    # Fetch titles and bodies for just the sampled PRs and their issues.
    pr_ids = ", ".join(f"'{r['pr_id']}'" for r in sample)
    issue_ids = ", ".join(f"'{r['issue_id']}'" for r in sample)
    pr_text = {str(i): (t, b) for i, t, b in con.execute(
        f"SELECT CAST(id AS VARCHAR), title, body FROM {src('pull_request')} WHERE CAST(id AS VARCHAR) IN ({pr_ids})"
    ).fetchall()}
    issue_text = {str(i): (t, b, u) for i, t, b, u in con.execute(
        f"SELECT CAST(id AS VARCHAR), title, body, html_url FROM {src('issue')} WHERE CAST(id AS VARCHAR) IN ({issue_ids})"
    ).fetchall()}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in sample:
            r["pr_title"], r["pr_body"] = pr_text.get(r["pr_id"], (None, None))
            it = issue_text.get(r["issue_id"])
            r["issue_title"], r["issue_body"], r["issue_url"] = it if it else (None, None, None)
            fh.write(json.dumps(r, default=str) + "\n")

    meta = {
        "dataset": DATASET, "drawn_on": dt.date.today().isoformat(), "seed": args.seed,
        "per_agent": args.per_agent, "per_repo": args.per_repo, "min_stars": args.min_stars,
        "candidates_after_filters": len(rows), "sampled": len(sample),
        "by_agent_available": {a: len(v) for a, v in sorted(by_agent.items())},
        "issues_found": sum(1 for r in sample if r["issue_title"] is not None),
    }
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
