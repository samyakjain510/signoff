"""Build a local HTML review sheet: 10 labeled items for the PM to check by hand.

Picks (deterministic, seed 7):
  5 decisions the labeler says the agent made on its own,
  3 decisions the labeler says the PM asked for or implied,
  2 commits where the labeler found no decision.

Usage:
    python3 scripts/review_sheet.py [--out data/review/phase1.html]

The page stays on this machine. It contains private request text and code.
"""
from __future__ import annotations

import argparse
import html
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
REPOS = ["portfolio", "ktech-interviews"]
TYPE_NAMES = {
    "user_facing": "User-facing behavior", "scope": "Scope", "data_privacy": "Data and privacy",
    "dependency_cost": "Dependency or cost", "removed_feature": "Removed feature",
}
WHO_NAMES = {"asked": "you asked for it", "implied": "your request implied it", "agent": "the agent's own call"}


def load():
    items = []
    for repo in REPOS:
        reqs = {}
        for l in open(DATA / "records" / f"{repo}.requests.jsonl"):
            r = json.loads(l)
            reqs[r["sha"]] = "\n\n".join(m["text"] for m in r["request"])
        for l in open(DATA / "labels" / f"{repo}.jsonl"):
            row = json.loads(l)
            if "label" not in row:
                continue
            items.append((repo, row, reqs.get(row["sha"], "")))
    return items


def excerpt(text: str, quote: str, width: int = 420) -> str:
    if not text:
        return "(no new message: this commit continued an earlier request)"
    i = text.find(quote[:40]) if quote else -1
    if i < 0:
        return text[:width] + ("..." if len(text) > width else "")
    start = max(0, i - width // 3)
    return ("..." if start else "") + text[start:start + width] + ("..." if start + width < len(text) else "")


def pick(items, seed=7):
    rng = random.Random(seed)
    agent, asked, empty = [], [], []
    for repo, row, req in items:
        decs = row["label"]["decisions"]
        if not decs:
            empty.append((repo, row, req, None))
        for d in decs:
            (agent if d["who"] == "agent" else asked).append((repo, row, req, d))
    for pool in (agent, asked, empty):
        rng.shuffle(pool)

    def spread(pool, n):
        """Prefer variety: different types, then both repos, then hard-to-undo."""
        chosen, seen_types, seen_commits = [], set(), set()
        for repo, row, req, d in sorted(pool, key=lambda x: (x[3] or {}).get("undo") != "hard"):
            key = (d or {}).get("type")
            if row["sha"] in seen_commits or (key in seen_types and len(seen_types) < 5):
                continue
            chosen.append((repo, row, req, d))
            seen_types.add(key)
            seen_commits.add(row["sha"])
            if len(chosen) == n:
                break
        for x in pool:  # top up if variety rules left gaps
            if len(chosen) == n:
                break
            if x not in chosen and x[1]["sha"] not in seen_commits:
                chosen.append(x)
                seen_commits.add(x[1]["sha"])
        return chosen

    return spread(agent, 5) + spread(asked, 3) + empty[:2]


def radio(name: str, options: list[tuple[str, str]]) -> str:
    return "".join(
        f'<label class="opt"><input type="radio" name="{name}" value="{v}"> {html.escape(t)}</label>'
        for v, t in options
    )


def render(picks) -> str:
    cards = []
    for n, (repo, row, req, d) in enumerate(picks, 1):
        head = (f'<div class="meta">{n} of {len(picks)} · {html.escape(repo)} · '
                f'<code>{row["short"]}</code> {html.escape(row["subject"])}</div>')
        req_html = f'<div class="req"><b>Your request</b><p>{html.escape(excerpt(req, (d or {}).get("request_quote", "")))}</p></div>'
        if d:
            ev = "".join(f'<pre><span class="f">{html.escape(e["file"])}</span>\n{html.escape(e["quote"])}</pre>' for e in d["evidence"][:3])
            body = (
                f'<div class="dec"><span class="tag">{TYPE_NAMES[d["type"]]}</span>'
                f'<span class="tag">labeler says: {WHO_NAMES[d["who"]]}</span>'
                f'<span class="tag">{"hard" if d["undo"] == "hard" else "easy"} to undo</span>'
                f'<p class="what">{html.escape(d["what"])}</p>'
                f'<p class="why">{html.escape(d["why_it_matters"])}</p>{ev}</div>'
            )
            qs = (
                f'<div class="q"><span>Is this a real product decision?</span>{radio(f"q{n}a", [("yes","Yes"),("no","No"),("unsure","Unsure")])}</div>'
                f'<div class="q"><span>Who made it?</span>{radio(f"q{n}b", [("asked","I asked"),("implied","My request implied it"),("agent","Agent\'s own call")])}</div>'
                f'<div class="q"><span>Would you have wanted to approve it before it shipped?</span>{radio(f"q{n}c", [("yes","Yes"),("no","No, telling me after is fine"),("never","No, I don\'t need to hear about it")])}</div>'
            )
        else:
            body = (f'<div class="dec"><span class="tag">labeler found no product decisions</span>'
                    f'<p class="what">{html.escape(row["label"]["user_summary"])}</p></div>')
            qs = (f'<div class="q"><span>Did this commit contain a product decision you care about?</span>'
                  f'{radio(f"q{n}a", [("no","No, nothing missed"),("yes","Yes, something was missed")])}</div>'
                  f'<div class="q"><span>If yes, what? (optional)</span><input class="txt" name="q{n}note"></div>')
        cards.append(f'<section class="card" data-n="{n}">{head}{req_html}{body}{qs}</section>')

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Signoff review</title>
<style>
:root {{ --ink:#1b1b1f; --muted:#62626b; --line:#e4e4ea; --bg:#fafafa; --card:#fff; --accent:#4b2e83; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system, system-ui, sans-serif; }}
main {{ max-width:760px; margin:0 auto; padding:24px 16px 80px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .lede {{ color:var(--muted); margin:0 0 20px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin:0 0 16px; }}
.meta {{ color:var(--muted); font-size:13px; margin-bottom:10px; }} code {{ font-size:12px; }}
.req {{ border-left:3px solid var(--line); padding-left:10px; margin-bottom:12px; }} .req p {{ margin:4px 0 0; white-space:pre-wrap; color:var(--muted); font-size:14px; }}
.tag {{ display:inline-block; font-size:12px; border:1px solid var(--line); border-radius:99px; padding:1px 8px; margin:0 6px 6px 0; }}
.what {{ font-weight:600; margin:6px 0 2px; }} .why {{ margin:0 0 8px; color:var(--muted); }}
pre {{ background:#f4f4f7; border-radius:6px; padding:8px; font-size:12px; overflow-x:auto; white-space:pre-wrap; margin:6px 0; }} .f {{ color:var(--muted); }}
.q {{ border-top:1px solid var(--line); padding-top:10px; margin-top:10px; }} .q > span {{ display:block; font-weight:600; margin-bottom:4px; }}
.opt {{ display:inline-block; margin:2px 14px 2px 0; }} .txt {{ width:100%; padding:6px; border:1px solid var(--line); border-radius:6px; }}
.done {{ position:sticky; bottom:0; background:var(--bg); padding:12px 0; border-top:1px solid var(--line); }}
button {{ background:var(--accent); color:#fff; border:0; border-radius:8px; padding:10px 16px; font-size:15px; cursor:pointer; }}
#out {{ width:100%; min-height:70px; margin-top:8px; font:12px ui-monospace, monospace; }}
</style></head><body><main>
<h1>Check 10 labels</h1>
<p class="lede">Claude drafted these from your requests and the code. Answer what you can. Nothing here leaves your Mac. When done, press the button and paste the line into the chat.</p>
{''.join(cards)}
<div class="done"><button onclick="collect()">Copy my answers</button><textarea id="out" readonly placeholder="Your answers appear here"></textarea></div>
</main><script>
function collect() {{
  const parts = [];
  document.querySelectorAll('.card').forEach(c => {{
    const n = c.dataset.n, vals = [];
    ['a','b','c'].forEach(k => {{ const el = c.querySelector(`input[name="q${{n}}${{k}}"]:checked`); if (c.querySelector(`input[name="q${{n}}${{k}}"]`)) vals.push(el ? el.value : '-'); }});
    const note = c.querySelector(`input[name="q${{n}}note"]`); if (note && note.value) vals.push('"' + note.value + '"');
    parts.push(n + ':' + vals.join(','));
  }});
  const s = 'review ' + parts.join(' | ');
  const out = document.getElementById('out'); out.value = s; out.select();
  try {{ navigator.clipboard.writeText(s); }} catch (e) {{}}
}}
</script></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA / "review" / "phase1.html"))
    args = ap.parse_args()
    picks = pick(load())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(picks))
    key = [{"n": i, "repo": r, "short": row["short"], "decision": d} for i, (r, row, _, d) in enumerate(picks, 1)]
    out.with_suffix(".key.json").write_text(json.dumps(key, indent=2))
    print(f"wrote {out} with {len(picks)} items")


if __name__ == "__main__":
    main()
