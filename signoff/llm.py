"""Call headless Claude Code (`claude -p`) with tools off and a JSON schema.

All model work in signoff goes through the user's own Claude Code. Nothing here
holds an API key or calls a paid API directly.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Iterable

# Claude Code reads CLAUDE.md files from the working directory and its parents.
# Running from an empty folder keeps a project's own instructions out of the prompt.
RUN_DIR = Path(tempfile.gettempdir()) / "signoff-run"
LIMIT = re.compile(r"usage limit|rate.?limit|limit reached|limit.*resets|quota|overloaded|\b429\b|\b529\b", re.I)


def call(system_prompt: str, schema: str, text: str, model: str, effort: str | None = None,
         timeout: int = 600) -> dict:
    """One model call. Returns {"out": parsed JSON, "usage": ...} or {"error": ...}."""
    cmd = [
        "claude", "-p",
        "--model", model,
        "--system-prompt", system_prompt,
        "--json-schema", schema,
        "--tools", "",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--output-format", "json",
    ]
    if effort:
        cmd += ["--effort", effort]
    RUN_DIR.mkdir(exist_ok=True)
    t0 = time.time()
    try:
        res = subprocess.run(cmd, input=text, capture_output=True, text=True, cwd=RUN_DIR, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout}s", "wall_s": round(time.time() - t0, 1)}
    wall = round(time.time() - t0, 1)
    if res.returncode != 0:
        return {"error": (res.stderr or res.stdout)[-800:], "wall_s": wall}
    try:
        out = json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"error": "unreadable output: " + res.stdout[-400:], "wall_s": wall}
    if out.get("is_error"):
        return {"error": str(out.get("result", ""))[-800:], "wall_s": wall}
    parsed = out.get("structured_output")
    if parsed is None:
        try:
            parsed = json.loads(out.get("result", ""))
        except (json.JSONDecodeError, TypeError):
            return {"error": "no structured output", "raw": str(out.get("result", ""))[:800], "wall_s": wall}
    return {
        "out": parsed,
        "usage": out.get("usage", {}),
        "cost_usd_equiv": out.get("total_cost_usd"),
        "wall_s": wall,
    }


def tokens_in(usage: dict) -> int:
    return sum(usage.get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))


def run_batch(items: Iterable[dict], work: Callable[[dict], dict], out_path: Path, key: str = "id",
              workers: int = 3, wait_s: int = 1200, max_waits: int = 15,
              describe: Callable[[dict], str] | None = None) -> None:
    """Run `work` over items, appending one JSON row per item to out_path.

    Resumable: items with a row that has no "error" are skipped. When Claude
    Code reports a usage limit, the worker waits and retries the same item.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.open():
            row = json.loads(line)
            if "error" not in row:
                done.add(row[key])
    todo = [it for it in items if it[key] not in done]
    print(f"{len(done)} already done, {len(todo)} to run, {workers} at a time", flush=True)
    lock = threading.Lock()

    def one(item: dict) -> None:
        for _ in range(max_waits + 1):
            row = work(item)
            err = row.get("error", "")
            if err and LIMIT.search(err):
                print(f"{item[key]}: usage limit reached, waiting {wait_s // 60} min", flush=True)
                time.sleep(wait_s)
                continue
            break
        row.setdefault(key, item[key])
        with lock:
            with out_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            status = "ERROR " + row["error"][:100].replace("\n", " ") if "error" in row else (describe(row) if describe else "ok")
            print(f"{item[key]} {status} | {tokens_in(row.get('usage', {}))} tok in | {row.get('wall_s')}s", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))


def safe(text: str) -> str:
    """Remove terminal control codes before printing text that came from a diff."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x1b.", "", text)
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)


if __name__ == "__main__":
    sys.exit("signoff.llm is a library module")
