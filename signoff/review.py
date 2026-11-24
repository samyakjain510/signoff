"""The model step: one call per change, producing the feed summary and the decision flags.

The model gets the PM's spec, the agent's own description, the file list, code
check findings and a diff trimmed by importance. Tools are off. Afterwards a
script checks every quote: evidence must be in the diff, and a claim that the
PM asked for something must quote the spec.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import diffs, llm

HERE = Path(__file__).resolve().parent
PROMPT = HERE / "prompts" / "review.md"
SCHEMA = HERE / "prompts" / "review_schema.json"


def norm(s: str) -> str:
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def build_input(ch: dict, diff_text: str, omitted: list[str]) -> str:
    if ch["spec"]:
        note = " (carried over: this change continues an earlier request)" if ch["spec_carried"] else ""
        spec = f"SPEC{note}, from {ch['spec_source']}:\n{ch['spec']}"
    else:
        spec = "SPEC: (none found)"
    files = "\n".join(f"  {f['status']} {f['path']} (+{f.get('additions')}/-{f.get('deletions')})" for f in ch["files"])
    grouped: dict[tuple[str, str], list[str]] = {}
    for f in ch["findings"]:
        grouped.setdefault((f["check"], f["file"]), []).append(f"line {f['line']}: {f['text']}" if f["line"] else f["text"])
    found = "\n".join(
        f"  {c} in {file}: " + "; ".join(v[:4]) + (f" (+{len(v) - 4} more)" if len(v) > 4 else "")
        for (c, file), v in grouped.items()) or "  (none)"
    left_out = "\n".join(f"  {o}" for o in omitted) or "  (none)"
    return (
        f"{spec}\n\n"
        f"AGENT'S DESCRIPTION:\n{ch['agent_text'] or '(none)'}\n\n"
        f"CHANGE {ch['id']}: {ch['title']}\nFiles changed:\n{files}\n\n"
        f"CODE CHECKS:\n{found}\n\n"
        f"Files left out of the diff below:\n{left_out}\n\n"
        f"DIFF:\n{diff_text}"
    )


def check_output(out: dict, spec: str, diff: str) -> dict:
    nd, ns = norm(diff), norm(spec)
    for d in out.get("decisions", []):
        for ev in d.get("evidence", []):
            q = norm(ev.get("quote", "").strip().lstrip("+-"))
            ev["verified"] = bool(q) and q in nd
        d["evidence_ok"] = any(ev["verified"] for ev in d.get("evidence", []))
        d["who_model"] = d["who"]
        rq = norm(d.get("request_quote", ""))
        if d["who"] in ("asked", "implied") and not (rq and rq in ns):
            d["who"] = "agent"
            d["who_note"] = "the quoted request was not found in the spec"
    sq = norm(out.get("spec_quote", ""))
    out["spec_quote_ok"] = bool(sq) and sq in ns
    return out


def review(ch: dict, model: str = "haiku", effort: str | None = None) -> dict:
    path = Path(ch["diff_path"])
    diff = path.read_text(errors="replace") if path.exists() else ""  # an empty commit has no diff
    text, omitted, cut = diffs.fit(diff)
    inp = build_input(ch, text, omitted)
    res = llm.call(PROMPT.read_text(), SCHEMA.read_text(), inp, model=model, effort=effort)
    row = {"id": ch["id"], "model": model, "diff_cut": cut, "omitted": omitted, "input_chars": len(inp), **res}
    if "out" in res:
        row["out"] = check_output(res["out"], ch["spec"], diff)
    return row
