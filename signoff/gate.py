"""A control point at `git push`: hold commits whose decisions need the PM's sign-off.

Installed as a git pre-push hook (`python3 -m signoff hook install`), it reviews
the commits about to be pushed, applies the sign-off rules and blocks the push
if any decision needs sign-off that a person has not approved.

Approvals are kept in .git/signoff/approved.jsonl, outside the code, and can
only be recorded from an interactive terminal. A coding agent runs commands
without one, so it cannot approve its own change.
"""
from __future__ import annotations

import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import gitlog, llm, policy, review, sources, feed

ZERO = "0" * 40
HOOK = """#!/bin/sh
# Installed by signoff: hold pushes that contain product decisions needing your sign-off.
# Remove this file to turn it off.
PYTHONPATH="{root}${{PYTHONPATH:+:$PYTHONPATH}}" exec python3 -m signoff gate --repo "$(git rev-parse --show-toplevel)" "$@"
"""


def git_dir(repo: Path) -> Path:
    return Path(gitlog.git(repo, "rev-parse", "--absolute-git-dir").strip())


def approvals_file(repo: Path) -> Path:
    return git_dir(repo) / "signoff" / "approved.jsonl"


def approved(repo: Path) -> set[str]:
    p = approvals_file(repo)
    return {json.loads(l)["sha"] for l in p.open()} if p.exists() else set()


def pending(repo: Path, lines: list[str] | None) -> list[str]:
    """Commits a push would send. `lines` is what git gives a pre-push hook on stdin."""
    shas: list[str] = []
    if lines:
        for line in lines:
            parts = line.split()
            if len(parts) != 4 or parts[1] == ZERO:
                continue  # malformed, or deleting a remote branch
            local, remote = parts[1], parts[3]
            rng = [local, f"^{remote}"] if remote != ZERO else [local, "--not", "--remotes"]
            shas += gitlog.git(repo, "rev-list", "--reverse", "--no-merges", *rng).split()
    else:
        shas = gitlog.git(repo, "rev-list", "--reverse", "--no-merges", "HEAD", "--not", "--remotes").split()
    return list(dict.fromkeys(shas))


def repo_policy(repo: Path, path: str | None) -> dict:
    if path:
        return policy.load(path)
    own = repo / "signoff.toml"
    return policy.load(own) if own.exists() else policy.load()


def check(repo: Path, out: Path, pol: dict, transcripts: Path | None, model: str = "haiku",
          lines: list[str] | None = None) -> int:
    repo = repo.resolve()
    ok = approved(repo)
    todo = [s for s in pending(repo, lines) if s not in ok]
    if not todo:
        return 0
    changes = sources.git_changes(repo, out, transcripts=transcripts, shas=todo)
    rev_path = out / "reviews.jsonl"
    done = {r["id"] for r in (json.loads(l) for l in rev_path.open()) if "out" in r} if rev_path.exists() else set()
    need = [c for c in changes if c["id"] not in done]
    if need:
        print(f"signoff: reviewing {len(need)} commit(s) before the push ({model})...", file=sys.stderr, flush=True)
        # max_waits=0: never stall a push waiting for a usage limit to reset.
        llm.run_batch(need, lambda ch: review.review(ch, model=model), rev_path, workers=2, max_waits=0,
                      describe=lambda r: f"{len(r['out']['decisions'])} decisions")
    reviews: dict[str, dict] = {}
    for line in rev_path.open():
        r = json.loads(line)
        if "out" in r or r["id"] not in reviews:
            reviews[r["id"]] = r
    held = []
    for ch in changes:
        r = reviews.get(ch["id"], {})
        if "out" not in r:
            held.append((ch, [], "could not be reviewed: " + r.get("error", "no result")[:160]))
            continue
        decs = [d for d in r["out"]["decisions"] if policy.action(pol, d) == "sign-off"]
        if decs:
            held.append((ch, decs, ""))
    page, _ = feed.write(out, repo.name, changes, reviews, pol)
    if not held:
        print(f"signoff: {len(changes)} commit(s) checked; nothing needs your sign-off.", file=sys.stderr)
        return 0
    lines_out = [f"signoff: this push is on hold. {len(held)} commit(s) contain decisions that need your sign-off:", ""]
    for ch, decs, why in held:
        lines_out.append(f"  {ch['id']}  {ch['title']}")
        if why:
            lines_out.append(f"      {why}")
        for d in decs:
            lines_out.append(f"      - {feed.TYPE_NAMES[d['type']]}, {feed.WHO_NAMES[d['who']].lower()}, "
                             f"{'hard' if d['undo'] == 'hard' else 'easy'} to undo: {d['what']}")
        lines_out.append("")
    ids = " ".join(ch["id"] for ch, _, _ in held)
    lines_out += [f"Full feed: {page}",
                  "After reading, approve them yourself in a terminal (an agent cannot), then push again:",
                  f"  PYTHONPATH={Path(__file__).resolve().parent.parent} python3 -m signoff approve {ids}"]
    print(llm.safe("\n".join(lines_out)), file=sys.stderr)
    return 1


def approve(repo: Path, ids: list[str], stdin=sys.stdin) -> int:
    if not stdin.isatty():
        print("signoff: approvals must be typed by a person in a terminal. An agent cannot approve its own change.",
              file=sys.stderr)
        return 2
    repo = repo.resolve()
    shas = []
    for i in ids:
        try:
            sha = gitlog.git(repo, "rev-parse", "--verify", "-q", f"{i}^{{commit}}").strip()
        except Exception:
            sha = ""
        if not sha:
            print(f"signoff: no commit {i}", file=sys.stderr)
            return 1
        shas.append(sha)
    for sha in shas:
        print(llm.safe(f"  {sha[:7]}  {gitlog.git(repo, 'show', '-s', '--format=%s', sha).strip()}"))
    try:
        answer = input(f"Type yes to approve {len(shas)} commit(s): ")
    except EOFError:
        answer = ""
    if answer.strip().lower() != "yes":
        print("Nothing approved.")
        return 1
    p = approvals_file(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        for sha in shas:
            fh.write(json.dumps({"sha": sha, "by": getpass.getuser(),
                                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}) + "\n")
    print(f"Approved {len(shas)} commit(s). Push again.")
    return 0


def install_hook(repo: Path, force: bool = False) -> int:
    hook = git_dir(repo.resolve()) / "hooks" / "pre-push"
    if hook.exists() and not force and "signoff" not in hook.read_text(errors="replace"):
        print(f"signoff: {hook} already exists and is not signoff's. Pass --force to replace it.", file=sys.stderr)
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(HOOK.format(root=Path(__file__).resolve().parent.parent))
    os.chmod(hook, 0o755)
    print(f"Installed {hook}. Pushes from this repo now stop for decisions that need your sign-off.")
    return 0
