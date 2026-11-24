"""signoff: a plain-language feed of what your coding agent changed, with the
product decisions flagged and the ones you choose held for your sign-off.

    python3 -m signoff scan [REPO] [--limit 20] [--since "2 weeks ago"]
    python3 -m signoff github OWNER/NAME [--prs 20] [--agent-only]
    python3 -m signoff feed OUT_DIR [--policy signoff.toml] [--text]
    python3 -m signoff policy > signoff.toml

The model work runs through your own Claude Code (`claude -p`, Haiku by
default, tools off). Reading the repo is read-only. Results go to
~/.signoff/<name>/ unless you pass --out.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import feed, llm, policy, review, sources

HOME = Path.home() / ".signoff"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open()] if path.exists() else []


def latest_reviews(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in load_jsonl(path):
        if "out" in row or row["id"] not in out:
            out[row["id"]] = row
    return out


def need_tools(*names: str) -> None:
    missing = [n for n in names if not shutil.which(n)]
    if missing:
        sys.exit(f"signoff needs {', '.join(missing)} on your PATH.")


def run(changes: list[dict], out: Path, name: str, args) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with (out / "changes.jsonl").open("w") as fh:
        for ch in changes:
            fh.write(json.dumps(ch) + "\n")
    done = {k for k, v in latest_reviews(out / "reviews.jsonl").items() if "out" in v}
    todo = [c for c in changes if c["id"] not in done]
    print(f"{len(changes)} changes; {len(todo)} need a model call ({args.model}, {args.workers} at a time).", flush=True)
    if args.dry_run:
        for c in changes:
            print(llm.safe(f"  {c['id']}  {c['date'][:10]}  {c['title'][:80]}"))
        return
    llm.run_batch(todo, lambda ch: review.review(ch, model=args.model), out / "reviews.jsonl",
                  workers=args.workers, describe=lambda r: f"{len(r['out']['decisions'])} decisions")
    show(out, name, args.policy, args.text)


def show(out: Path, name: str, policy_path: str | None, text: bool) -> None:
    changes = load_jsonl(out / "changes.jsonl")
    page, txt = feed.write(out, name, changes, latest_reviews(out / "reviews.jsonl"), policy.load(policy_path))
    if text:
        print(txt)
    print(f"Feed: {page}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="signoff", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default="haiku", help="Claude model alias for the review (default: haiku)")
    common.add_argument("--workers", type=int, default=2, help="model calls at a time (default: 2)")
    common.add_argument("--policy", help="a signoff.toml file (default: the built-in tiers)")
    common.add_argument("--out", help="where to write results (default: ~/.signoff/<name>)")
    common.add_argument("--dry-run", action="store_true", help="list the changes and stop before any model call")
    common.add_argument("--text", action="store_true", help="also print the feed as text")

    s = sub.add_parser("scan", parents=[common], help="review commits in a local git repo")
    s.add_argument("repo", nargs="?", default=".")
    s.add_argument("--limit", type=int, default=20, help="most recent N commits (default: 20)")
    s.add_argument("--since", help='only commits after this date, e.g. "2 weeks ago"')
    s.add_argument("--agent-only", action="store_true", help="only commits an agent co-wrote")
    s.add_argument("--transcripts", default="auto",
                   help="Claude Code transcripts to read your requests from: auto (~/.claude/projects), none, or a folder")

    g = sub.add_parser("github", parents=[common], help="review merged pull requests on GitHub (read-only, via gh)")
    g.add_argument("repo", help="OWNER/NAME")
    g.add_argument("--prs", type=int, default=20, help="most recent N merged PRs (default: 20)")
    g.add_argument("--numbers", help="comma-separated PR numbers instead of the most recent ones")
    g.add_argument("--agent-only", action="store_true", help="only PRs an agent opened")

    f = sub.add_parser("feed", help="rebuild the feed from earlier results")
    f.add_argument("out")
    f.add_argument("--policy")
    f.add_argument("--text", action="store_true")

    sub.add_parser("policy", help="print the default sign-off rules as a starting signoff.toml")

    args = ap.parse_args()
    if args.cmd == "policy":
        print(policy.DEFAULT, end="")
    elif args.cmd == "feed":
        out = Path(args.out).expanduser()
        show(out, out.name, args.policy, args.text)
    elif args.cmd == "scan":
        need_tools("git", "claude")
        repo = Path(args.repo).expanduser().resolve()
        if args.transcripts == "none":
            tdir = None
        elif args.transcripts == "auto":
            tdir = Path.home() / ".claude" / "projects"
            tdir = tdir if tdir.exists() else None
        else:
            tdir = Path(args.transcripts).expanduser()
        out = Path(args.out).expanduser() if args.out else HOME / repo.name
        changes = sources.git_changes(repo, out, since=args.since, limit=args.limit, transcripts=tdir,
                                      agent_only=args.agent_only)
        run(changes, out, repo.name, args)
    elif args.cmd == "github":
        need_tools("gh", "claude")
        name = args.repo.split("/")[-1]
        out = Path(args.out).expanduser() if args.out else HOME / args.repo.replace("/", "__")
        numbers = [int(n) for n in args.numbers.split(",")] if args.numbers else None
        changes = sources.github_changes(args.repo, out, prs=args.prs, agent_only=args.agent_only, numbers=numbers)
        run(changes, out, name, args)


if __name__ == "__main__":
    main()
