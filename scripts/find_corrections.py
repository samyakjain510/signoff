"""Ground truth for "the changes that matter": decisions Samyak later reversed or changed.

For each commit whose request has new messages (not carried over), Sonnet sees
that request and every decision the reference labels found in earlier commits
of the same repo, and lists the ones the request reverses or changes. Each
match must quote the request exactly; a script checks the quote.

Usage:
    python3 scripts/find_corrections.py run
    python3 scripts/find_corrections.py list      # print every match for reading by hand
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import llm  # noqa: E402
from signoff.label import requests_with_carry  # noqa: E402
from signoff.review import norm  # noqa: E402

REPOS = ["portfolio", "ktech-interviews"]
DATA = ROOT / "data"
OUT = DATA / "eval" / "corrections.jsonl"


def decisions(repo: str) -> tuple[list[dict], list[dict]]:
    """Commits in time order, and every reference decision with a stable id."""
    recs = {json.loads(l)["sha"]: json.loads(l) for l in open(DATA / "records" / f"{repo}.jsonl")}
    labels = {}
    for l in open(DATA / "labels" / f"{repo}.jsonl"):
        row = json.loads(l)
        if "label" in row:
            labels[row["sha"]] = row["label"]  # later rows (relabels) win
    commits = sorted((r for r in recs.values() if not r["is_merge"]), key=lambda r: r["date"])
    decs = []
    for r in commits:
        for i, d in enumerate(labels.get(r["sha"], {}).get("decisions", [])):
            decs.append({"id": f"{repo[:2]}-{r['short']}-{i}", "sha": r["sha"], "short": r["short"], "date": r["date"],
                         "subject": r["subject"], "type": d["type"], "who": d["who"], "undo": d["undo"], "what": d["what"]})
    return commits, decs


def items() -> list[dict]:
    out = []
    for repo in REPOS:
        commits, decs = decisions(repo)
        reqs = requests_with_carry(repo)
        for c in commits:
            req = reqs.get(c["sha"])
            earlier = [d for d in decs if d["date"] < c["date"]]
            if not req or req["carried"] or not req["text"].strip() or not earlier:
                continue
            out.append({"id": f"{repo}:{c['short']}", "repo": repo, "short": c["short"], "date": c["date"],
                        "request": req["text"], "earlier": earlier})
    return out


def build(it: dict) -> str:
    lines = [f"{d['id']} | {d['date'][:10]} | commit \"{d['subject'][:70]}\" | {d['type']} | {d['what']}" for d in it["earlier"]]
    return f"REQUEST (sent {it['date'][:10]}):\n{it['request']}\n\nEARLIER DECISIONS:\n" + "\n".join(lines)


def run() -> None:
    system = (ROOT / "prompts" / "find_corrections.md").read_text()
    schema = (ROOT / "prompts" / "find_corrections_schema.json").read_text()

    def work(it: dict) -> dict:
        res = llm.call(system, schema, build(it), model="sonnet", effort="medium")
        row = {"id": it["id"], "repo": it["repo"], "short": it["short"], **res}
        if "out" in res:
            valid = {d["id"] for d in it["earlier"]}
            nr = norm(it["request"])
            for m in res["out"]["matches"]:
                m["id_valid"] = m["decision_id"] in valid
                m["quote_ok"] = bool(norm(m["request_quote"])) and norm(m["request_quote"]) in nr
            for o in res["out"]["other_corrections"]:
                o["quote_ok"] = bool(norm(o["request_quote"])) and norm(o["request_quote"]) in nr
        return row

    llm.run_batch(items(), work, OUT, workers=3,
                  describe=lambda r: f"{len(r['out']['matches'])} matches, {len(r['out']['other_corrections'])} other")


def listing() -> None:
    decs = {d["id"]: d for repo in REPOS for d in decisions(repo)[1]}
    for l in OUT.open():
        r = json.loads(l)
        if "out" not in r:
            continue
        for m in r["out"]["matches"]:
            d = decs.get(m["decision_id"], {})
            print(llm.safe(f"[{r['id']}] -> {m['decision_id']} ({d.get('who')}/{d.get('type')}/{d.get('undo')}) {m['kind']}"
                           f" quote_ok={m['quote_ok']} id_ok={m['id_valid']}\n   decision: {d.get('what', '?')}\n"
                           f"   request: \"{m['request_quote'][:200]}\"\n   reason: {m['reason']}"))
        for o in r["out"]["other_corrections"]:
            print(llm.safe(f"[{r['id']}] OTHER quote_ok={o['quote_ok']}: {o['what']}\n   request: \"{o['request_quote'][:200]}\""))


if __name__ == "__main__":
    {"run": run, "list": listing}[sys.argv[1]]()
