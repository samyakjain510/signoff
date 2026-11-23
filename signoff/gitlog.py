"""Turn a git repo's history into one JSON record per commit.

Read-only: this only runs `git log`/`git show`/`git rev-list` against the repo.

Usage:
    python -m signoff.gitlog <repo_path> <out_dir>

Writes:
    <out_dir>/<repo_name>.jsonl      one record per commit, oldest first
    <out_dir>/<repo_name>/<sha>.diff the full patch for each non-merge commit
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Who co-wrote the commit, judged from "Co-Authored-By:" trailers.
AGENT_NAMES = {
    "claude": re.compile(r"\bclaude\b|anthropic", re.I),
    "copilot": re.compile(r"copilot", re.I),
    "cursor": re.compile(r"\bcursor\b", re.I),
    "codex": re.compile(r"codex|openai", re.I),
    "devin": re.compile(r"devin", re.I),
}
TRAILER = re.compile(r"^co-authored-by:\s*(.+)$", re.I | re.M)
SEP = "\x1e"  # record separator, never appears in commit text


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def parse_numstat_z(raw: str) -> dict[str, tuple[int | None, int | None]]:
    """Lines added/removed per path. Binary files report None."""
    out: dict[str, tuple[int | None, int | None]] = {}
    tokens = raw.split("\0")
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.strip():
            i += 1
            continue
        adds, dels, path = tok.lstrip("\n").split("\t", 2)
        if path == "":  # rename or copy: next two tokens are old and new path
            path = tokens[i + 2]
            i += 3
        else:
            i += 1
        a = None if adds == "-" else int(adds)
        d = None if dels == "-" else int(dels)
        out[path] = (a, d)
    return out


def parse_name_status_z(raw: str) -> list[dict]:
    """File status per path: A added, M modified, D deleted, R renamed, C copied."""
    files = []
    tokens = [t for t in raw.split("\0")]
    i = 0
    while i < len(tokens):
        status = tokens[i].strip()
        if not status:
            i += 1
            continue
        if status[0] in "RC":
            files.append({"status": status[0], "old_path": tokens[i + 1], "path": tokens[i + 2]})
            i += 3
        else:
            files.append({"status": status[0], "path": tokens[i + 1]})
            i += 2
    return files


def agent_of(co_authors: list[str]) -> str | None:
    for name, pat in AGENT_NAMES.items():
        if any(pat.search(c) for c in co_authors):
            return name
    return None


def commit_record(repo: Path, sha: str, main_shas: set[str]) -> tuple[dict, str]:
    fmt = SEP.join(["%H", "%P", "%aI", "%an", "%s", "%b"])
    full, parents, date, author, subject, body = git(
        repo, "show", "-s", f"--format={fmt}", sha
    ).split(SEP)
    parents = parents.split()
    co_authors = [c.strip() for c in TRAILER.findall(body)]
    rec = {
        "repo": repo.name,
        "sha": full,
        "short": full[:7],
        "parents": parents,
        "is_merge": len(parents) > 1,
        "on_main": full in main_shas,
        "date": date,
        "author": author,
        "subject": subject,
        "body": body.strip(),
        "co_authors": co_authors,
        "agent": agent_of(co_authors),
        "files": [],
    }
    diff = ""
    if not rec["is_merge"]:
        stats = parse_numstat_z(git(repo, "show", "--format=", "-M", "--numstat", "-z", full))
        files = parse_name_status_z(git(repo, "show", "--format=", "-M", "--name-status", "-z", full))
        for f in files:
            a, d = stats.get(f["path"], (None, None))
            f["additions"], f["deletions"] = a, d
        rec["files"] = files
        diff = git(repo, "show", "--format=", "-M", "--patch", full)
    rec["files_changed"] = len(rec["files"])
    rec["additions"] = sum(f["additions"] or 0 for f in rec["files"])
    rec["deletions"] = sum(f["deletions"] or 0 for f in rec["files"])
    rec["diff_chars"] = len(diff)
    return rec, diff


def extract(repo: Path, out_dir: Path) -> list[dict]:
    repo = repo.resolve()
    main_ref = "origin/main" if git(repo, "branch", "-r").strip() else "main"
    main_shas = set(git(repo, "rev-list", main_ref).split())
    shas = git(repo, "rev-list", "--remotes", "--branches", "--reverse", "--topo-order").split()
    diff_dir = out_dir / repo.name
    diff_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for sha in shas:
        rec, diff = commit_record(repo, sha, main_shas)
        if diff:
            (diff_dir / f"{rec['short']}.diff").write_text(diff)
        records.append(rec)
    with (out_dir / f"{repo.name}.jsonl").open("w") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return records


def summary(records: list[dict]) -> str:
    n = len(records)
    agent = sum(1 for r in records if r["agent"])
    merges = sum(1 for r in records if r["is_merge"])
    sizes = sorted(r["files_changed"] for r in records if not r["is_merge"])
    median = sizes[len(sizes) // 2] if sizes else 0
    return (
        f"{n} commits, {agent} co-written by an agent, {merges} merges, "
        f"median {median} files per commit, largest {max(sizes, default=0)}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    recs = extract(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{Path(sys.argv[1]).name}: {summary(recs)}")
