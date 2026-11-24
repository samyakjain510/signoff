"""Where changes come from: commits in a local repo, or merged pull requests on GitHub.

Both are read-only. A "change" is a plain dict:
    id, kind ("commit" or "pr"), title, date, url, agent (name or None),
    agent_text (the agent's own commit message or PR description),
    spec (what the PM asked for, in their words), spec_source, spec_carried,
    files [{status, path, additions, deletions}], findings (exact code checks),
    diff_path (the full diff, saved to a file and never printed).
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict
from pathlib import Path

from . import checks, gitlog, requests

SPEC_CHARS = 10_000
AGENT_PR = re.compile(
    r"(chatgpt\.com/codex|app\.devin\.ai|Generated with \[?Claude Code|co-authored-by:\s*claude|"
    r"cursor\.com/(agents|background)|copilot-swe-agent|devin-ai-integration)", re.I)
AGENT_LOGINS = {"Copilot": "copilot", "devin-ai-integration[bot]": "devin", "cursor[bot]": "cursor",
                "claude[bot]": "claude", "chatgpt-codex-connector[bot]": "codex"}


def make_change(*, id: str, kind: str, title: str, date: str, url: str, agent: str | None, agent_text: str,
                spec: str, spec_source: str, spec_carried: bool, files: list[dict], findings: list[dict],
                diff_path: Path) -> dict:
    if len(spec) > SPEC_CHARS:
        spec = "[... earlier text cut ...]\n" + spec[-SPEC_CHARS:]
    return {"id": id, "kind": kind, "title": title, "date": date, "url": url, "agent": agent,
            "agent_text": agent_text, "spec": spec, "spec_source": spec_source, "spec_carried": spec_carried,
            "files": files, "findings": findings, "diff_path": str(diff_path)}


# ---- local git ----------------------------------------------------------------

def github_url(repo: Path) -> str | None:
    res = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+/[^/]+?)(\.git)?$", res.stdout.strip())
    return f"https://github.com/{m.group(1)}" if m else None


def carry_requests(links: list[dict]) -> dict[str, dict]:
    """sha -> {"text", "carried"}. A commit with no new message continues its session's last request."""
    rows = sorted(links, key=lambda r: (r["session"], r["commit_time"] or ""))
    out, last = {}, {}
    for r in rows:
        msgs = [m["text"] for m in r["request"]]
        if msgs:
            text, carried = "\n\n---\n\n".join(msgs), False
            last[r["session"]] = text
        else:
            text, carried = last.get(r["session"], ""), True
        out[r["sha"]] = {"text": text, "carried": carried}
    return out


def git_changes(repo: Path, out_dir: Path, since: str | None = None, limit: int | None = None,
                transcripts: Path | None = None, agent_only: bool = False) -> list[dict]:
    repo = repo.resolve()
    args = ["rev-list", "--reverse", "--no-merges"] + ([f"--since={since}"] if since else []) + ["HEAD"]
    shas = gitlog.git(repo, *args).split()
    if limit:
        shas = shas[-limit:]
    head = set(gitlog.git(repo, "rev-list", "HEAD").split())
    diff_dir = out_dir / "diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    recs = []
    for sha in shas:
        rec, diff = gitlog.commit_record(repo, sha, head)
        (diff_dir / f"{rec['short']}.diff").write_text(diff)
        recs.append(rec)
    if agent_only:
        recs = [r for r in recs if r["agent"]]
    reqs = carry_requests(requests.link(recs, transcripts, set())) if transcripts else {}
    base = github_url(repo)
    changes = []
    for rec in recs:
        diff_path = diff_dir / f"{rec['short']}.diff"
        findings = [asdict(f) for f in checks.run_checks(repo, rec, diff_path.read_text())]
        req = reqs.get(rec["sha"], {"text": "", "carried": False})
        changes.append(make_change(
            id=rec["short"], kind="commit", title=rec["subject"], date=rec["date"],
            url=f"{base}/commit/{rec['sha']}" if base else "", agent=rec["agent"],
            agent_text=(rec["subject"] + "\n\n" + rec["body"]).strip(),
            spec=req["text"], spec_source="your messages in the Claude Code session" if req["text"] else "",
            spec_carried=req["carried"], files=rec["files"], findings=findings, diff_path=diff_path))
    return changes


# ---- GitHub pull requests (read-only, through the gh CLI) ---------------------

def gh_json(path: str) -> object:
    res = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"gh api {path}: {res.stderr.strip()[:300]}")
    return json.loads(res.stdout)


def gh_diff(repo: str, number: int, dest: Path, max_bytes: int = 2_000_000) -> bool:
    """Save a PR's diff to a file. The diff is never printed: it may hold terminal control codes."""
    res = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.diff", f"repos/{repo}/pulls/{number}"],
                         capture_output=True)
    if res.returncode != 0 or len(res.stdout) > max_bytes:
        return False
    dest.write_bytes(res.stdout)
    return True


def pr_agent(pr: dict) -> str | None:
    login = (pr.get("user") or {}).get("login", "")
    if login in AGENT_LOGINS:
        return AGENT_LOGINS[login]
    text = (pr.get("body") or "") + " " + (pr.get("head") or {}).get("ref", "")
    m = AGENT_PR.search(text)
    if m:
        s = m.group(0).lower()
        for name in ("codex", "devin", "claude", "cursor", "copilot"):
            if name in s:
                return name
        return "agent"
    ref = (pr.get("head") or {}).get("ref", "")
    for name in ("codex", "devin", "claude", "cursor", "copilot"):
        if ref.startswith(name + "/") or ref.startswith(name + "-"):
            return name
    return None


ISSUE_REF = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s+#(\d+)", re.I)


def linked_issue(repo: str, pr: dict) -> tuple[str, str]:
    m = ISSUE_REF.search(pr.get("body") or "")
    if not m:
        return "", ""
    try:
        issue = gh_json(f"repos/{repo}/issues/{m.group(1)}")
    except RuntimeError:
        return "", ""
    text = f"{issue.get('title', '')}\n\n{issue.get('body') or ''}".strip()
    return text, f"issue #{m.group(1)}"


def github_changes(repo: str, out_dir: Path, prs: int = 20, agent_only: bool = False,
                   numbers: list[int] | None = None) -> list[dict]:
    diff_dir = out_dir / "diffs"
    diff_dir.mkdir(parents=True, exist_ok=True)
    if numbers:
        pulls = [gh_json(f"repos/{repo}/pulls/{n}") for n in numbers]
    else:
        pulls, page = [], 1
        while len(pulls) < prs and page <= 10:
            batch = gh_json(f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}")
            if not batch:
                break
            for pr in batch:
                if pr.get("merged_at") and (not agent_only or pr_agent(pr)):
                    pulls.append(pr)
            page += 1
        pulls = pulls[:prs]
    changes = []
    for pr in sorted(pulls, key=lambda p: p.get("merged_at") or ""):
        n = pr["number"]
        dest = diff_dir / f"pr{n}.diff"
        if not dest.exists() and not gh_diff(repo, n, dest):
            continue
        files = [{"status": {"added": "A", "removed": "D", "renamed": "R"}.get(f["status"], "M"),
                  "path": f["filename"], **({"old_path": f["previous_filename"]} if f.get("previous_filename") else {}),
                  "additions": f.get("additions"), "deletions": f.get("deletions")}
                 for f in gh_json(f"repos/{repo}/pulls/{n}/files?per_page=100")]
        rec = {"sha": f"pr{n}", "short": f"pr{n}", "files": files, "parents": []}
        findings = [asdict(f) for f in checks.run_checks(None, rec, dest.read_text(errors="replace"))]
        spec, spec_source = linked_issue(repo, pr)
        changes.append(make_change(
            id=f"pr{n}", kind="pr", title=pr.get("title", ""), date=pr.get("merged_at") or "",
            url=pr.get("html_url", ""), agent=pr_agent(pr),
            agent_text=(pr.get("title", "") + "\n\n" + (pr.get("body") or "")).strip(),
            spec=spec, spec_source=spec_source, spec_carried=False, files=files, findings=findings, diff_path=dest))
    return changes
