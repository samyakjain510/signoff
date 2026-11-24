"""Replay the sign-off policies over Samyak's 60 commits and compute the measures
fixed in docs/measures.md.

Usage: python3 scripts/analyze.py   -> results/own_repos.json and a printed summary
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import checks, policy, stats  # noqa: E402

REPOS = ["portfolio", "ktech-interviews"]
DATA = ROOT / "data"
PATH_RULES = [
    checks.PAGE_DIRS,
    re.compile(r"(^|/)(migrations?)/|\.sql$|schema\.prisma$"),
    re.compile(r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|Gemfile|go\.mod|Cargo\.toml)$"),
    re.compile(r"(^|/)(vercel\.json|netlify\.toml|wrangler\.toml|Dockerfile)$|(^|/)\.github/workflows/|(^|/)supabase/config\.toml$"),
    re.compile(r"(^|/)\.env[^/]*$"),
]
POLICIES = ["A", "B", "C", "D", "E", "F"]
POLICY_NAMES = {"A": "Every commit", "B": "Paths (CODEOWNERS-style)", "C": "Code checks only", "D": "Tool, any decision",
                "E": "Tool, agent decisions", "F": "Tool, default tiers", "F_ref": "Default tiers on reference labels"}


def jl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open()] if path.exists() else []


def files_of(d: dict) -> set[str]:
    return {e.get("file", "") for e in d.get("evidence", []) if e.get("file")}


def load() -> dict:
    commits, ref, tool, findings = [], {}, {}, {}
    for repo in REPOS:
        for r in jl(DATA / "records" / f"{repo}.jsonl"):
            if not r["is_merge"]:
                r["repo"] = repo
                commits.append(r)
        for row in jl(DATA / "labels" / f"{repo}.jsonl"):
            if "label" in row:
                ref[row["sha"]] = row["label"]["decisions"]
        for row in jl(DATA / "records" / f"{repo}.checks.jsonl"):
            findings[row["sha"]] = row["findings"]
        short2sha = {c["short"]: c["sha"] for c in commits if c["repo"] == repo}
        for row in jl(DATA / "eval" / repo / "reviews.jsonl"):
            if "out" in row:
                tool[short2sha[row["id"]]] = row
    return {"commits": commits, "ref": ref, "tool": tool, "findings": findings}


def ground_truth(d: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Decisions Samyak later reversed or changed, after Claude's hand review."""
    review_path = DATA / "eval" / "corrections_review.json"
    rejected = set(json.loads(review_path.read_text())["rejected"]) if review_path.exists() else set()
    by_id = {}
    for c in d["commits"]:
        for i, dec in enumerate(d["ref"].get(c["sha"], [])):
            by_id[f"{c['repo'][:2]}-{c['short']}-{i}"] = {**dec, "sha": c["sha"], "short": c["short"], "repo": c["repo"],
                                                         "date": c["date"], "subject": c["subject"]}
    hit: dict[str, dict] = {}
    other = []
    for row in jl(DATA / "eval" / "corrections.jsonl"):
        if "out" not in row:
            continue
        for m in row["out"]["matches"]:
            key = f"{row['id']}|{m['decision_id']}"
            if not (m["quote_ok"] and m["id_valid"]) or key in rejected:
                continue
            g = hit.setdefault(m["decision_id"], {**by_id[m["decision_id"]], "id": m["decision_id"], "corrected_by": []})
            g["corrected_by"].append({"request": row["id"], "kind": m["kind"], "quote": m["request_quote"]})
        for o in row["out"]["other_corrections"]:
            key = f"{row['id']}|other|{o['request_quote'][:40]}"
            if o["quote_ok"] and key not in rejected:
                other.append({"request": row["id"], **o})
    g_all = list(hit.values())
    return [g for g in g_all if g["who"] in ("agent", "implied")], [g for g in g_all if g["who"] == "asked"], other


def tool_policy_actions(row: dict, pol: dict) -> list[tuple[dict, str]]:
    return [(dec, policy.action(pol, dec)) for dec in row["out"]["decisions"]]


def held(d: dict, p: str) -> dict[str, list]:
    """Policy -> {sha: decisions that triggered the hold} (empty list for non-tool policies)."""
    out: dict[str, list] = {}
    default = policy.load()
    for c in d["commits"]:
        sha = c["sha"]
        paths = [f["path"] for f in c["files"]] + [f.get("old_path", "") for f in c["files"]]
        row = d["tool"].get(sha)
        decs = row["out"]["decisions"] if row else []
        if p == "A":
            out[sha] = []
        elif p == "B" and any(rx.search(x) for x in paths if x for rx in PATH_RULES):
            out[sha] = []
        elif p == "C" and d["findings"].get(sha):
            out[sha] = []
        elif p == "D":
            trig = [x for x in decs if x.get("evidence_ok")]
            if trig:
                out[sha] = trig
        elif p == "E":
            trig = [x for x in decs if x.get("evidence_ok") and x["who"] == "agent"]
            if trig:
                out[sha] = trig
        elif p == "F":
            trig = [x for x, a in tool_policy_actions(row, default) if a == "sign-off"] if row else []
            if trig:
                out[sha] = trig
        elif p == "F_ref":
            trig = [x for x in d["ref"].get(sha, []) if policy.action(default, {**x, "evidence_ok": True}) == "sign-off"]
            if trig:
                out[sha] = trig
    return out


def matches(tool_dec: dict, ref_dec: dict) -> bool:
    tf, rf = files_of(tool_dec), files_of(ref_dec)
    if rf and tf:
        return bool(tf & rf)
    return tool_dec["type"] == ref_dec["type"]


def week(date: str) -> tuple[int, int]:
    return datetime.fromisoformat(date).isocalendar()[:2]


def analyze() -> dict:
    d = load()
    g_agent, g_asked, g_other = ground_truth(d)
    g_by_sha = defaultdict(list)
    for g in g_agent:
        g_by_sha[g["sha"]].append(g)
    weeks = {week(c["date"]) for c in d["commits"]}
    days = {c["date"][:10] for c in d["commits"]}
    default = policy.load()
    res: dict = {"commits": len(d["commits"]), "active_weeks": len(weeks), "active_days": len(days),
                 "commits_reviewed_by_tool": len(d["tool"]),
                 "ground_truth": {"agent_or_implied_later_corrected": len(g_agent), "asked_then_changed": len(g_asked),
                                  "corrections_matching_no_listed_decision": len(g_other),
                                  "hard_to_undo_in_g": sum(g["undo"] == "hard" for g in g_agent),
                                  "commits_with_g": len(g_by_sha)},
                 "policies": {}}
    for p in POLICIES + ["F_ref"]:
        h = held(d, p)
        n = len(h)
        caught_commit = sum(1 for g in g_agent if g["sha"] in h)
        row = {"name": POLICY_NAMES[p], "held_commits": n, "held_share": stats.pct(n, len(d["commits"])),
               "per_active_week": round(n / len(weeks), 1),
               "g_commit_held": stats.pct(caught_commit, len(g_agent)),
               "g_commit_held_ci95": [round(x, 2) for x in stats.wilson(caught_commit, len(g_agent))],
               "hit_rate": stats.pct(sum(1 for sha in h if sha in g_by_sha), n)}
        if p in ("D", "E", "F"):
            caught_dec = sum(1 for g in g_agent if any(matches(t, g) for t in h.get(g["sha"], [])))
            row["g_decision_held"] = stats.pct(caught_dec, len(g_agent))
            row["g_decision_held_ci95"] = [round(x, 2) for x in stats.wilson(caught_dec, len(g_agent))]
        res["policies"][p] = row
    # Shown at all under the default tiers (sign-off or notify), at decision level.
    shown = 0
    for g in g_agent:
        row = d["tool"].get(g["sha"])
        if row and any(matches(t, g) and a in ("notify", "sign-off") for t, a in tool_policy_actions(row, default)):
            shown += 1
    res["policies"]["F"]["g_decision_shown"] = stats.pct(shown, len(g_agent))
    res["policies"]["F"]["g_decision_shown_ci95"] = [round(x, 2) for x in stats.wilson(shown, len(g_agent))]
    notify_commits = 0
    for c in d["commits"]:
        row = d["tool"].get(c["sha"])
        if row and policy.change_action(default, row["out"]["decisions"]) == "notify":
            notify_commits += 1
    res["policies"]["F"]["notify_only_commits"] = notify_commits

    # Tool vs reference labels.
    tp_tool = tp_ref = n_tool = n_ref = n_ref_agent = tp_ref_agent = 0
    who_pairs = []
    unverified = 0
    who_downgraded = 0
    for c in d["commits"]:
        row = d["tool"].get(c["sha"])
        if not row:
            continue
        T, R = row["out"]["decisions"], d["ref"].get(c["sha"], [])
        n_tool += len(T)
        n_ref += len(R)
        unverified += sum(1 for t in T if not t.get("evidence_ok"))
        who_downgraded += sum(1 for t in T if t.get("who_note"))
        tp_tool += sum(1 for t in T if any(matches(t, r) for r in R))
        for r in R:
            m = [t for t in T if matches(t, r)]
            if m:
                tp_ref += 1
                same_type = [t for t in m if t["type"] == r["type"]] or m
                who_pairs.append((r["who"], same_type[0]["who"]))
            if r["who"] == "agent":
                n_ref_agent += 1
                tp_ref_agent += bool(m)
    res["tool_vs_reference"] = {
        "tool_decisions": n_tool, "reference_decisions": n_ref,
        "precision": stats.pct(tp_tool, n_tool), "recall": stats.pct(tp_ref, n_ref),
        "recall_agent_decisions": stats.pct(tp_ref_agent, n_ref_agent),
        "who_agreement": stats.pct(sum(a == b for a, b in who_pairs), len(who_pairs)),
        "who_kappa": round(stats.cohen_kappa([a for a, _ in who_pairs], [b for _, b in who_pairs]), 3) if who_pairs else None,
        "tool_decisions_with_no_verified_evidence": stats.pct(unverified, n_tool),
        "tool_who_downgraded_for_missing_quote": stats.pct(who_downgraded, n_tool),
        "tool_who_counts": dict(Counter(t["who"] for row in d["tool"].values() for t in row["out"]["decisions"])),
        "reference_who_counts": dict(Counter(r["who"] for c in d["commits"] for r in d["ref"].get(c["sha"], []))),
    }
    # Tool recall on the decisions that mattered, regardless of policy.
    res["tool_vs_reference"]["recall_on_g"] = stats.pct(
        sum(1 for g in g_agent if d["tool"].get(g["sha"]) and any(matches(t, g) for t in d["tool"][g["sha"]]["out"]["decisions"])),
        len(g_agent))

    # Summaries that mislead (judge v2, PM scope).
    labels = {}
    for row in jl(DATA / "eval" / "judge_own.jsonl"):
        if "out" in row:
            labels[row["id"]] = row["out"]["label"]
    pairs = []
    for c in d["commits"]:
        k = f"{c['repo']}:{c['short']}"
        if f"{k}:tool" in labels and f"{k}:msg" in labels:
            pairs.append((labels[f"{k}:tool"], labels[f"{k}:msg"]))
    if pairs:
        n = len(pairs)
        tm = sum(a == "misaligned" for a, _ in pairs)
        mm = sum(b == "misaligned" for _, b in pairs)
        only_tool = sum(a == "misaligned" and b != "misaligned" for a, b in pairs)
        only_msg = sum(b == "misaligned" and a != "misaligned" for a, b in pairs)
        k_ = only_tool + only_msg
        p_sign = min(1.0, 2 * sum(math.comb(k_, i) for i in range(0, min(only_tool, only_msg) + 1)) / 2 ** k_) if k_ else 1.0
        res["summaries"] = {
            "pairs": n,
            "tool_summary": dict(Counter(a for a, _ in pairs)), "commit_message": dict(Counter(b for _, b in pairs)),
            "tool_misleads": stats.pct(tm, n), "tool_misleads_ci95": [round(x, 2) for x in stats.wilson(tm, n)],
            "message_misleads": stats.pct(mm, n), "message_misleads_ci95": [round(x, 2) for x in stats.wilson(mm, n)],
            "discordant_tool_only": only_tool, "discordant_message_only": only_msg, "sign_test_p": round(p_sign, 4),
        }

    # Cost of the tool runs.
    toks = [sum(r["usage"].get(k, 0) for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            for r in d["tool"].values()]
    walls = [r["wall_s"] for r in d["tool"].values()]
    if toks:
        res["tool_cost"] = {"calls": len(toks), "input_tokens_total": sum(toks), "input_tokens_mean": sum(toks) // len(toks),
                            "seconds_mean": round(sum(walls) / len(walls), 1),
                            "api_equivalent_usd": round(sum(r.get("cost_usd_equiv") or 0 for r in d["tool"].values()), 2)}
    res["g_list"] = [{"id": g["id"], "repo": g["repo"], "short": g["short"], "type": g["type"], "who": g["who"],
                      "undo": g["undo"], "what": g["what"],
                      "held_F": g["sha"] in held(d, "F"),
                      "corrected_by": [x["request"] for x in g["corrected_by"]]} for g in g_agent]
    return res


if __name__ == "__main__":
    out = analyze()
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "own_repos.json").write_text(json.dumps(out, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "g_list"}, indent=2))
