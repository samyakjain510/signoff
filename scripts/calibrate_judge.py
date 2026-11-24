"""Calibrate the judge against PR-MCI's human labels before trusting it.

Draws 24 PRs per human consensus label (aligned, partial, misaligned) from the
PR-MCI validation set, keeping only PRs whose annotation file fits without
cutting (60,000 characters before the annotation section). The judge sees what
the annotators saw: title, description, file list and patches. The human labels
and notes are removed first.

Two sets, never overlapping:
  dev   24 per label from the validation set. Judge v1 was scored here, and v2
        was written after reading v1's disagreements on this set.
  test  PRs v2 never saw: 24 aligned and 24 partial from the unused validation
        PRs, all 11 unused misaligned ones, and 13 more misaligned PRs from
        PR-MCI's second labeled set (the RQ2 taxonomy), to reach 24.

Usage:
    python3 scripts/calibrate_judge.py run SET TAG PROMPT    # e.g. run test v2 prompts/judge.md
    python3 scripts/calibrate_judge.py report SET TAG

PR-MCI has no license, so its data stays in git-ignored data/ and only
aggregate numbers are written to results/.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from signoff import llm, stats  # noqa: E402

MCI = ROOT / "data" / "public" / "PR-MCI" / "data"
JUDGE_DIR = ROOT / "data" / "judge"
PER_LABEL = 24
MAX_CHARS = 60_000
H = {
    "title": "## 📝 PR Title", "body": "## 📄 PR Description (Body)", "stats": "## 📈 Code Change Statistics",
    "files": "## 📁 Files Changed", "patches": "## 🔧 Code Patches (Full Diffs)", "end": "## 🔖 ANNOTATION SECTION",
}


def section(md: str, start: str, end: str) -> str:
    i, j = md.find(start), md.find(end)
    if i < 0 or j < 0:
        return ""
    return md[i + len(start):j].strip().strip("-").strip()


def unfence(s: str) -> str:
    s = s.strip()
    if s.startswith("```") and s.endswith("```"):
        s = s[3:-3]
    return s.strip()


def build(md: str) -> str:
    title = unfence(section(md, H["title"], H["body"]))
    body = unfence(section(md, H["body"], H["files"]))
    stat = section(md, H["stats"], H["title"])
    files = section(md, H["files"], H["patches"])
    patches = section(md, H["patches"], H["end"])
    return (
        "SCOPE: reviewer\n\n"
        f"DESCRIPTION:\nTitle: {title}\n\n{body or '(empty)'}\n\n"
        f"CHANGE:\n{stat}\n\nFiles changed: {files}\n\nDiff (one ---FILE--- block per file):\n{patches}"
    )


def fits(filename: str) -> bool:
    md = (MCI / "manual_annotations" / filename).read_text()
    i = md.find(H["end"])
    return 0 <= i <= MAX_CHARS


def dev_sample() -> list[dict]:
    rows = list(csv.DictReader(open(MCI / "manual_annotations_validation.csv")))
    rows.sort(key=lambda r: r["pr_id"])
    pools: dict[str, list[dict]] = {}
    for r in rows:
        if fits(r["filename"]):
            pools.setdefault(r["consensus_label"], []).append(r)
    rng = random.Random(7)
    picked = []
    for label in ("aligned", "partial", "misaligned"):
        picked += rng.sample(pools[label], PER_LABEL)
    return [{"id": r["pr_id"], "file": r["filename"], "human": r["consensus_label"], "source": "validation"} for r in picked]


def test_sample() -> list[dict]:
    dev = {it["id"] for it in dev_sample()}
    val = sorted(csv.DictReader(open(MCI / "manual_annotations_validation.csv")), key=lambda r: r["pr_id"])
    pools: dict[str, list[dict]] = {}
    for r in val:
        if r["pr_id"] not in dev and fits(r["filename"]):
            pools.setdefault(r["consensus_label"], []).append(r)
    rng = random.Random(11)
    picked = [{"id": r["pr_id"], "file": r["filename"], "human": r["consensus_label"], "source": "validation"}
              for label in ("aligned", "partial") for r in rng.sample(pools[label], PER_LABEL)]
    picked += [{"id": r["pr_id"], "file": r["filename"], "human": "misaligned", "source": "validation"}
               for r in pools["misaligned"]]
    val_ids = {r["pr_id"] for r in val}
    names = {f.split("_")[1]: f for f in (p.name for p in (MCI / "manual_annotations").glob("pr_*.md"))}
    tax = sorted(csv.DictReader(open(MCI / "manual_annotations_rq2_taxonomy.csv", encoding="utf-8-sig")), key=lambda r: r["pr_id"])
    extra = [r for r in tax if r["manual_label"] == "misaligned" and r["pr_id"] not in val_ids
             and r["pr_id"] in names and fits(names[r["pr_id"]])]
    need = PER_LABEL - len(pools["misaligned"])
    picked += [{"id": r["pr_id"], "file": names[r["pr_id"]], "human": "misaligned", "source": "rq2"}
               for r in rng.sample(extra, need)]
    assert not dev & {p["id"] for p in picked}
    return picked


SETS = {"dev": dev_sample, "test": test_sample}


def run(set_name: str, tag: str, prompt: str) -> None:
    system = (ROOT / prompt).read_text()
    schema = (ROOT / "prompts" / "judge_schema.json").read_text()
    items = SETS[set_name]()

    def work(it: dict) -> dict:
        text = build((MCI / "manual_annotations" / it["file"]).read_text())
        res = llm.call(system, schema, text, model="sonnet", effort="medium")
        return {"id": it["id"], "input_chars": len(text), "prompt": prompt, **res}

    llm.run_batch(items, work, JUDGE_DIR / f"calibration_{set_name}_{tag}.jsonl", workers=3,
                  describe=lambda r: r["out"]["label"])


def agreement(items: list[dict], got: dict[str, str]) -> dict:
    ids = [it["id"] for it in items if it["id"] in got]
    human = [next(it["human"] for it in items if it["id"] == i) for i in ids]
    judge = [got[i] for i in ids]
    hb = ["aligned" if h == "aligned" else "not" for h in human]
    jb = ["aligned" if j == "aligned" else "not" for j in judge]
    hm = ["mis" if h == "misaligned" else "rest" for h in human]
    jm = ["mis" if j == "misaligned" else "rest" for j in judge]
    confusion = Counter(zip(human, judge))
    return {
        "n": len(ids),
        "human_labels": dict(Counter(human)),
        "kappa_aligned_vs_not": round(stats.cohen_kappa(hb, jb), 3),
        "kappa_aligned_vs_not_ci95": [round(x, 3) for x in stats.kappa_ci(hb, jb)],
        "kappa_misaligned_vs_rest": round(stats.cohen_kappa(hm, jm), 3),
        "kappa_misaligned_vs_rest_ci95": [round(x, 3) for x in stats.kappa_ci(hm, jm)],
        "kappa_3way": round(stats.cohen_kappa(human, judge), 3),
        "accuracy_3way": round(sum(x == y for x, y in zip(human, judge)) / len(ids), 3),
        "recall": {lab: stats.pct(confusion[(lab, lab)], human.count(lab)) for lab in ("aligned", "partial", "misaligned")},
        "misaligned_precision": stats.pct(confusion[("misaligned", "misaligned")], judge.count("misaligned")),
        "confusion_human_to_judge": {f"{h}->{j}": c for (h, j), c in sorted(confusion.items())},
    }


def report(set_name: str, tag: str) -> None:
    items = SETS[set_name]()
    got, usage_in = {}, 0
    for line in (JUDGE_DIR / f"calibration_{set_name}_{tag}.jsonl").open():
        r = json.loads(line)
        if "out" in r:
            got[r["id"]] = r["out"]["label"]
            usage_in += llm.tokens_in(r.get("usage", {}))
    res = {"set": set_name, "judge": tag, "all": agreement(items, got)}
    if set_name == "test":
        res["validation_only"] = agreement([it for it in items if it["source"] == "validation"], got)
    res["passes_bar_aligned_vs_not"] = res["all"]["kappa_aligned_vs_not"] >= 0.6
    res["passes_bar_misaligned_vs_rest"] = res["all"]["kappa_misaligned_vs_rest"] >= 0.6
    res["input_tokens"] = usage_in
    out = ROOT / "results" / f"judge_calibration_{set_name}_{tag}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    {"run": run, "report": report}[sys.argv[1]](*sys.argv[2:])
