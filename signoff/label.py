"""Draft reference labels for commits with headless Claude Code (`claude -p`).

Each commit is sent with the PM's request, the commit, code-check findings and
a trimmed diff. Tools are switched off, so text inside a diff cannot make the
model act. Every evidence quote is then checked against the diff.

Usage:
    python3 -m signoff.label <repo_name> [--only SHORT,SHORT] [--model sonnet] [--effort medium] [--force]

Reads data/records/<repo>.jsonl, .requests.jsonl, .checks.jsonl and diffs.
Appends to data/labels/<repo>.jsonl.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROMPT = ROOT / "prompts" / "label_commit.md"
SCHEMA = ROOT / "prompts" / "label_schema.json"

SKIP_FILE = re.compile(
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|\.min\.(js|css)$|"
    r"\.(png|jpe?g|gif|webp|ico|woff2?|ttf|otf|pdf|zip)$|(^|/)(node_modules|dist|\.next)/)"
)
PER_FILE_CHARS = 8_000
TOTAL_DIFF_CHARS = 60_000
REQUEST_CHARS = 10_000


def split_diff(diff: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^(?=diff --git )", diff)
    out = []
    for p in parts:
        if not p.strip():
            continue
        m = re.match(r"diff --git a/(\S+) b/(\S+)", p)
        out.append((m.group(2) if m else "?", p))
    return out


def trim_diff(diff: str) -> tuple[str, list[str], bool]:
    """Drop noise files, cap each file and the total. Returns text, omitted files, and whether anything was cut."""
    kept, omitted, cut, total = [], [], False, 0
    for path, chunk in split_diff(diff):
        if SKIP_FILE.search(path) or "Binary files" in chunk[:400]:
            omitted.append(f"{path} (lock, binary or generated)")
            continue
        if len(chunk) > PER_FILE_CHARS:
            chunk = chunk[:PER_FILE_CHARS] + f"\n[... {len(chunk) - PER_FILE_CHARS} more characters of this file cut ...]\n"
            cut = True
        if total + len(chunk) > TOTAL_DIFF_CHARS:
            omitted.append(f"{path} (cut for length)")
            cut = True
            continue
        kept.append(chunk)
        total += len(chunk)
    return "".join(kept), omitted, cut


def requests_with_carry(repo: str) -> dict[str, dict]:
    """Map sha -> request text. A commit with no new message continues the session's last request."""
    rows = [json.loads(l) for l in open(DATA / "records" / f"{repo}.requests.jsonl")]
    rows.sort(key=lambda r: (r["session"], r["commit_time"] or ""))
    out, last = {}, {}
    for r in rows:
        msgs = [m["text"] for m in r["request"]]
        if msgs:
            text, carried = "\n\n---\n\n".join(msgs), False
            last[r["session"]] = text
        else:
            text, carried = last.get(r["session"], ""), True
        if len(text) > REQUEST_CHARS:
            text = "[... earlier text cut ...]\n" + text[-REQUEST_CHARS:]
        out[r["sha"]] = {"text": text, "carried": carried}
    return out


def build_input(rec: dict, req: dict | None, findings: list[dict], diff_text: str, omitted: list[str]) -> str:
    files = "\n".join(
        f"  {f['status']} {f['path']} (+{f['additions']}/-{f['deletions']})" for f in rec["files"]
    )
    if req and req["text"]:
        note = " (carried over: this commit continues the same request)" if req["carried"] else ""
        request = f"REQUEST{note}:\n{req['text']}"
    else:
        request = "REQUEST: (none found)"
    grouped: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        grouped.setdefault((f["check"], f["file"]), []).append(
            f"line {f['line']}: {f['text']}" if f["line"] else f["text"]
        )
    checks = "\n".join(
        f"  {chk} in {file}: " + "; ".join(v[:4]) + (f" (+{len(v) - 4} more)" if len(v) > 4 else "")
        for (chk, file), v in grouped.items()
    ) or "  (none)"
    omitted_txt = "\n".join(f"  {o}" for o in omitted) or "  (none)"
    return (
        f"{request}\n\n"
        f"COMMIT {rec['short']}: {rec['subject']}\n"
        f"Message:\n{rec['body'] or '(no body)'}\n\n"
        f"Files changed:\n{files}\n\n"
        f"CODE CHECKS:\n{checks}\n\n"
        f"Files left out of the diff below:\n{omitted_txt}\n\n"
        f"DIFF:\n{diff_text}"
    )


def call_claude(prompt_input: str, model: str, effort: str) -> dict:
    cmd = [
        "claude", "-p",
        "--model", model,
        "--effort", effort,
        "--system-prompt-file", str(PROMPT),
        "--json-schema", SCHEMA.read_text(),
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "json",
    ]
    run_dir = DATA / "run"
    run_dir.mkdir(exist_ok=True)
    t0 = time.time()
    res = subprocess.run(cmd, input=prompt_input, capture_output=True, text=True, cwd=run_dir, timeout=600)
    wall = time.time() - t0
    if res.returncode != 0:
        return {"error": (res.stderr or res.stdout)[-800:], "wall_s": wall}
    out = json.loads(res.stdout)
    label = out.get("structured_output")
    if label is None:
        try:
            label = json.loads(out.get("result", ""))
        except json.JSONDecodeError:
            return {"error": "no structured output", "raw": out.get("result", "")[:800], "wall_s": wall}
    return {
        "label": label,
        "usage": out.get("usage", {}),
        "cost_usd_equiv": out.get("total_cost_usd"),
        "duration_ms": out.get("duration_ms"),
        "wall_s": round(wall, 1),
    }


def verify_quotes(label: dict, diff: str) -> tuple[int, int, list[str]]:
    total, ok, bad = 0, 0, []
    for d in label.get("decisions", []):
        for ev in d.get("evidence", []):
            q = ev.get("quote", "").strip().lstrip("+-").strip()
            total += 1
            if q and q in diff:
                ok += 1
            else:
                bad.append(q[:120])
    return ok, total, bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--only", default="")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    recs = [json.loads(l) for l in open(DATA / "records" / f"{args.repo}.jsonl")]
    checks = {json.loads(l)["sha"]: json.loads(l)["findings"] for l in open(DATA / "records" / f"{args.repo}.checks.jsonl")}
    reqs = requests_with_carry(args.repo)
    out_path = DATA / "labels" / f"{args.repo}.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    done = set()
    if out_path.exists() and not args.force:
        done = {json.loads(l)["sha"] for l in out_path.open() if "label" in json.loads(l)}
    only = set(filter(None, args.only.split(",")))

    for rec in recs:
        if rec["is_merge"] or rec["sha"] in done or (only and rec["short"] not in only):
            continue
        diff_file = DATA / "records" / args.repo / f"{rec['short']}.diff"
        diff = diff_file.read_text() if diff_file.exists() else ""
        diff_text, omitted, cut = trim_diff(diff)
        prompt_input = build_input(rec, reqs.get(rec["sha"]), checks.get(rec["sha"], []), diff_text, omitted)
        result = call_claude(prompt_input, args.model, args.effort)
        row = {
            "sha": rec["sha"], "short": rec["short"], "subject": rec["subject"],
            "model": args.model, "effort": args.effort,
            "input_chars": len(prompt_input), "diff_cut": cut,
            "request_carried": (reqs.get(rec["sha"]) or {}).get("carried"),
            **result,
        }
        if "label" in result:
            ok, total, bad = verify_quotes(result["label"], diff)
            row["quotes_verified"], row["quotes_total"], row["quotes_not_found"] = ok, total, bad
        with out_path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
        if "error" in result and re.search(r"limit|rate|quota|overloaded", result["error"], re.I):
            print(f"{rec['short']} stopped: usage or rate limit reached. Re-run later; finished commits are kept.")
            break
        u = result.get("usage", {})
        status = "ok" if "label" in result else f"ERROR {result.get('error', '')[:120]}"
        print(
            f"{rec['short']} {status} | in {u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0)} "
            f"out {u.get('output_tokens', 0)} tok | {result.get('wall_s')}s | "
            f"decisions {len(result.get('label', {}).get('decisions', []))} | quotes {row.get('quotes_verified')}/{row.get('quotes_total')}",
            flush=True,
        )


if __name__ == "__main__":
    main()
