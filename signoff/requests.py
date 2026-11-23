"""Link each commit to the user's request that produced it.

For repos built with Claude Code, the "spec" for a commit is usually the
person's own messages in the session that made it. This finds, for each
commit, the `git commit` command an agent ran (matched by subject line),
then collects the user's messages in that session since the previous commit.

Transcripts stay on this machine. Output goes to the git-ignored data folder.

Usage:
    python -m signoff.requests <records.jsonl> <transcripts_dir> <out.jsonl> [--exclude SESSION_ID ...]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
# Wrappers Claude Code puts around non-typed input (slash commands, hooks, etc.)
COMPACT_PREFIX = "This session is being continued from a previous conversation"
NOISE_TAGS = re.compile(r"<(command-[a-z-]+|local-command-[a-z-]+|bash-[a-z-]+)>.*?</\1>", re.S)


def user_text(rec: dict) -> str | None:
    """The text a person typed, or None for tool results, meta records and Claude's own summaries.

    Two places hold typed text: normal user records, and messages sent while the
    agent was mid-task, which Claude Code stores as a `queued_command` attachment.
    """
    att = rec.get("attachment") if rec.get("type") == "attachment" else None
    if isinstance(att, dict) and att.get("type") == "queued_command":
        human = (att.get("origin") or {}).get("kind") == "human" or att.get("humanTurn")
        prompt = att.get("prompt") or ""
        if isinstance(prompt, list):  # text plus pasted images, as content blocks
            prompt = "\n".join(b.get("text", "") for b in prompt if isinstance(b, dict) and b.get("type") == "text")
        text = REMINDER.sub("", prompt).strip() if human and not rec.get("isSidechain") else ""
        return text or None
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isSidechain"):
        return None
    # When a long session is compacted, Claude Code stores its own summary as a
    # user record. Those are Claude's words, not the person's request.
    if rec.get("isCompactSummary"):
        return None
    content = rec.get("message", {}).get("content")
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        if any(b.get("type") == "tool_result" for b in content if isinstance(b, dict)):
            return None
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return None
    text = NOISE_TAGS.sub("", REMINDER.sub("", "\n".join(parts))).strip()
    if text.startswith(COMPACT_PREFIX):  # older versions may not set the flag
        return None
    return text or None


def commit_commands(rec: dict) -> list[str]:
    """Bash commands in an assistant record that run `git commit`."""
    if rec.get("type") != "assistant":
        return []
    out = []
    for block in rec.get("message", {}).get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Bash":
            cmd = (block.get("input") or {}).get("command", "")
            if "git commit" in cmd or "git -C" in cmd and " commit" in cmd:
                out.append(cmd)
    return out


def load_session(path: Path) -> list[dict]:
    recs = []
    with path.open() as fh:
        for line in fh:
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs


def candidate_files(subjects: list[str], tdir: Path, exclude: set[str]) -> list[Path]:
    """Only open transcripts that mention at least one subject (fast pre-filter with grep)."""
    pattern_file = tdir.parent / ".signoff_subjects.tmp"
    try:
        pattern_file.write_text("\n".join(subjects))
        res = subprocess.run(
            ["grep", "-l", "-F", "-f", str(pattern_file), "--", *map(str, tdir.glob("*.jsonl"))],
            capture_output=True, text=True,
        )
    finally:
        pattern_file.unlink(missing_ok=True)
    return [Path(p) for p in res.stdout.split() if Path(p).stem not in exclude]


def link(records: list[dict], tdir: Path, exclude: set[str]) -> list[dict]:
    subjects = {r["subject"]: r for r in records if not r["is_merge"]}
    found: dict[str, dict] = {}
    for path in candidate_files(list(subjects), tdir, exclude):
        session = load_session(path)
        typed: list[dict] = []  # user messages since the last commit in this session
        for rec in session:
            text = user_text(rec)
            if text:
                # A queued message can also show up later as a normal one; keep it once.
                if not any(m["text"] == text for m in typed):
                    typed.append({"time": rec.get("timestamp"), "text": text})
                continue
            for cmd in commit_commands(rec):
                hit = next((s for s in subjects if s in cmd), None)
                if not hit:
                    continue
                sha = subjects[hit]["sha"]
                t = rec.get("timestamp")
                # A forked session repeats its parent's history; keep the earliest run.
                if sha not in found or (t and t < found[sha]["commit_time"]):
                    found[sha] = {
                        "sha": sha,
                        "short": sha[:7],
                        "subject": hit,
                        "session": path.stem,
                        "commit_time": t,
                        "request": list(typed),
                    }
                typed = []
    return [found[r["sha"]] for r in records if r["sha"] in found]


if __name__ == "__main__":
    args = sys.argv[1:]
    exclude = set()
    if "--exclude" in args:
        i = args.index("--exclude")
        exclude = set(args[i + 1:])
        args = args[:i]
    if len(args) != 3:
        sys.exit(__doc__)
    recs = [json.loads(l) for l in open(args[0])]
    links = link(recs, Path(args[1]).expanduser(), exclude)
    with open(args[2], "w") as fh:
        for row in links:
            fh.write(json.dumps(row) + "\n")
    empty = sum(1 for r in links if not r["request"])
    print(f"{Path(args[0]).stem}: linked {len(links)}/{len(recs)} commits to a session; {empty} with no user message since the previous commit")
