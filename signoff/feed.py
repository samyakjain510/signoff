"""Render the feed: a self-contained HTML page, or plain text for a terminal.

The page embeds the reviews as data and applies the sign-off rules in the
browser, so the PM can change a rule and see at once how many changes it holds.
All text from diffs and messages is inserted as text, never as HTML.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import llm, policy

TYPE_NAMES = {"user_facing": "User-facing", "scope": "Scope", "data_privacy": "Data and privacy",
              "dependency_cost": "Dependency or cost", "removed_feature": "Removed feature"}
WHO_NAMES = {"agent": "Agent's own call", "implied": "Implied by the request", "asked": "Asked for"}


def feed_data(name: str, changes: list[dict], reviews: dict[str, dict], pol: dict) -> dict:
    items = []
    for ch in changes:
        r = reviews.get(ch["id"], {})
        out = r.get("out")
        items.append({
            "id": ch["id"], "kind": ch["kind"], "title": ch["title"], "date": ch["date"][:10], "url": ch["url"],
            "agent": ch.get("agent"), "spec_source": ch.get("spec_source", ""), "spec_carried": ch.get("spec_carried", False),
            "spec_quote": (out or {}).get("spec_quote", "") if (out or {}).get("spec_quote_ok") else "",
            "summary": (out or {}).get("summary", ""), "error": "" if out else (r.get("error", "not reviewed yet")[:200]),
            "diff_cut": r.get("diff_cut", False),
            "decisions": [{k: d.get(k) for k in ("type", "who", "who_model", "who_note", "undo", "what", "why_it_matters",
                                                 "evidence", "request_quote", "evidence_ok")}
                          for d in (out or {}).get("decisions", [])],
            "checks": sorted({f["check"] for f in ch.get("findings", [])}),
        })
    dates = [i["date"] for i in items if i["date"]]
    return {"name": name, "from": min(dates, default=""), "to": max(dates, default=""),
            "policy": policy.as_matrix(pol), "default_policy": policy.as_matrix(policy.load()),
            "types": TYPE_NAMES, "who": WHO_NAMES, "changes": items}


def text_feed(data: dict) -> str:
    pol = data["policy"]

    def act(d):
        a = pol[d["who"]][d["type"]]
        h = pol["hard_to_undo"].get(d["who"]) if d["undo"] == "hard" else ""
        if h and policy.rank(h) > policy.rank(a):
            a = h
        return "notify" if a == "sign-off" and d.get("evidence_ok") is False else a

    lines, held, notes = [], 0, 0
    for c in reversed(data["changes"]):
        acts = [act(d) for d in c["decisions"]]
        top = max(acts, key=policy.rank, default="silent")
        if top == "silent":
            continue
        held += top == "sign-off"
        notes += top == "notify"
        lines.append(f"[{'NEEDS SIGN-OFF' if top == 'sign-off' else 'TO READ'}] {c['id']} {c['date']}  {c['title']}")
        if c["summary"]:
            lines.append(f"    {c['summary']}")
        for d, a in zip(c["decisions"], acts):
            if a != "silent":
                lines.append(f"    - {TYPE_NAMES[d['type']]}, {WHO_NAMES[d['who']].lower()}, "
                             f"{'hard' if d['undo'] == 'hard' else 'easy'} to undo: {d['what']}")
        lines.append("")
    head = f"{data['name']}: {len(data['changes'])} changes, {held} need sign-off, {notes} to read.\n"
    return llm.safe(head + "\n" + "\n".join(lines))


def html_feed(data: dict) -> str:
    blob = json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return PAGE.replace("__DATA__", blob).replace("__TITLE__", "Signoff feed")


def write(out_dir: Path, name: str, changes: list[dict], reviews: dict[str, dict], pol: dict) -> tuple[Path, str]:
    data = feed_data(name, changes, reviews, pol)
    page = out_dir / "feed.html"
    page.write_text(html_feed(data))
    return page, text_feed(data)


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root { --bg:#f7f7f5; --card:#ffffff; --ink:#1c1c1e; --muted:#5f6068; --line:#e3e3e0; --soft:#f0f0ed;
  --hold:#b4232a; --hold-bg:#fbeaea; --read:#8a5a00; --read-bg:#fdf3dc; --quiet:#5f6068; --quiet-bg:#efefec;
  --accent:#2f4b8f; --ok:#2e7d4f; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#151517; --card:#1e1e21; --ink:#ececef; --muted:#a1a1a9; --line:#33333a; --soft:#26262b;
  --hold:#ff8a8f; --hold-bg:#3a1d20; --read:#f2c46b; --read-bg:#3a2f17; --quiet:#a1a1a9; --quiet-bg:#2a2a2f;
  --accent:#9db4ff; --ok:#7fd3a0; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; }
main { max-width:820px; margin:0 auto; padding:28px 16px 80px; }
h1 { font-size:24px; line-height:1.25; margin:0 0 4px; }
.sub { color:var(--muted); margin:0 0 18px; }
.tiles { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:0 0 16px; }
.tile { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px; cursor:pointer; text-align:left; color:inherit; font:inherit; }
.tile b { display:block; font-size:24px; line-height:1.1; }
.tile span { color:var(--muted); font-size:13px; }
.tile[aria-pressed="true"] { outline:2px solid var(--accent); }
details.rules { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin:0 0 16px; }
details.rules summary { cursor:pointer; font-weight:600; }
.rules p { color:var(--muted); font-size:13px; margin:6px 0 10px; }
.grid { width:100%; border-collapse:collapse; font-size:13px; }
.grid th, .grid td { padding:5px 4px; border-top:1px solid var(--line); text-align:left; vertical-align:middle; }
.grid th { font-weight:600; color:var(--muted); }
.grid select { width:100%; font:inherit; padding:3px; border:1px solid var(--line); border-radius:6px; background:var(--soft); color:var(--ink); }
.rowbtns { display:flex; gap:8px; margin-top:10px; flex-wrap:wrap; }
button.small { font:inherit; font-size:13px; padding:5px 10px; border-radius:7px; border:1px solid var(--line); background:var(--soft); color:var(--ink); cursor:pointer; }
textarea.toml { width:100%; min-height:150px; font:12px ui-monospace, Menlo, monospace; margin-top:8px; background:var(--soft); color:var(--ink); border:1px solid var(--line); border-radius:6px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px; margin:0 0 12px; overflow-wrap:anywhere; }
.top { display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; }
.pill { font-size:12px; font-weight:600; border-radius:99px; padding:1px 9px; white-space:nowrap; }
.pill.sign-off { color:var(--hold); background:var(--hold-bg); }
.pill.notify { color:var(--read); background:var(--read-bg); }
.pill.silent { color:var(--quiet); background:var(--quiet-bg); }
.title { font-weight:600; }
.title a { color:inherit; }
.meta { color:var(--muted); font-size:13px; margin:2px 0 8px; }
.summary { margin:0 0 8px; }
.spec { border-left:3px solid var(--line); padding-left:10px; color:var(--muted); font-size:14px; margin:0 0 8px; }
.dec { border-top:1px solid var(--line); padding:8px 0 2px; }
.dec .what { font-weight:600; margin:4px 0 0; }
.dec .why { color:var(--muted); margin:0; font-size:14px; }
.chip { display:inline-block; font-size:12px; border:1px solid var(--line); border-radius:99px; padding:0 8px; margin:0 4px 2px 0; color:var(--muted); }
.dec.dim { opacity:.6; }
details.ev summary { cursor:pointer; color:var(--muted); font-size:13px; margin-top:4px; }
pre { background:var(--soft); border-radius:6px; padding:8px; font-size:12px; white-space:pre-wrap; overflow-wrap:anywhere; margin:6px 0; }
.f { color:var(--muted); }
.warn { color:var(--read); font-size:13px; }
.empty { color:var(--muted); text-align:center; padding:30px 0; }
footer { color:var(--muted); font-size:13px; margin-top:28px; }
@media (max-width:520px) { .tiles { grid-template-columns:1fr; } .tile b { display:inline; font-size:18px; margin-right:6px; } }
</style></head><body><main>
<h1 id="h"></h1><p class="sub" id="sub"></p>
<div class="tiles">
  <button class="tile" data-f="sign-off"><b id="n-hold">0</b><span>need your sign-off</span></button>
  <button class="tile" data-f="notify"><b id="n-read">0</b><span>to read when you can</span></button>
  <button class="tile" data-f="all"><b id="n-all">0</b><span>changes in all</span></button>
</div>
<details class="rules"><summary>Sign-off rules</summary>
<p>Choose what happens to each kind of decision. "Sign-off" holds the change for your approval, "Notify" puts it on your reading list, and "Silent" keeps it in the history only. A decision whose evidence could not be found in the code is never held.</p>
<table class="grid" id="grid"></table>
<div class="rowbtns"><button class="small" id="reset">Reset to the default</button><button class="small" id="export">Show as signoff.toml</button></div>
<textarea class="toml" id="toml" hidden readonly></textarea>
</details>
<div id="list"></div>
<footer>Made by signoff. Summaries and flags are drafted by a model from the diff and can be wrong; each flag quotes the lines it is based on.</footer>
</main>
<script>
const DATA = __DATA__;
const ACT = ["silent", "notify", "sign-off"], WHO = ["agent", "implied", "asked"];
const LABEL = {"sign-off": "Sign-off", "notify": "Notify", "silent": "Silent"};
const STATUS = {"sign-off": "Needs sign-off", "notify": "To read", "silent": "Quiet"};
const KEY = "signoff-policy-" + DATA.name;
let pol = JSON.parse(JSON.stringify(DATA.policy)), filter = "sign-off";
try { const s = localStorage.getItem(KEY); if (s) pol = JSON.parse(s); } catch (e) {}
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const rank = a => ACT.indexOf(a);
function act(d) {
  let a = pol[d.who][d.type];
  const h = d.undo === "hard" ? pol.hard_to_undo[d.who] : "";
  if (h && rank(h) > rank(a)) a = h;
  if (a === "sign-off" && d.evidence_ok === false) a = "notify";
  return a;
}
function top(c) { return c.decisions.reduce((m, d) => rank(act(d)) > rank(m) ? act(d) : m, "silent"); }
function save() { try { localStorage.setItem(KEY, JSON.stringify(pol)); } catch (e) {} }
function select(val, onchange, allowBlank) {
  const s = el("select");
  (allowBlank ? [""].concat(ACT) : ACT).forEach(a => { const o = el("option", null, a ? LABEL[a] : "No change"); o.value = a; if (a === val) o.selected = true; s.appendChild(o); });
  s.addEventListener("change", () => { onchange(s.value); save(); render(); });
  return s;
}
function grid() {
  const g = document.getElementById("grid"); g.textContent = "";
  const hr = el("tr"); hr.appendChild(el("th", null, "Decision type"));
  WHO.forEach(w => hr.appendChild(el("th", null, DATA.who[w]))); g.appendChild(hr);
  Object.keys(DATA.types).forEach(t => {
    const tr = el("tr"); tr.appendChild(el("td", null, DATA.types[t]));
    WHO.forEach(w => { const td = el("td"); td.appendChild(select(pol[w][t], v => pol[w][t] = v)); tr.appendChild(td); });
    g.appendChild(tr);
  });
  const tr = el("tr"); tr.appendChild(el("td", null, "If hard to undo, raise to"));
  WHO.forEach(w => { const td = el("td"); td.appendChild(select(pol.hard_to_undo[w] || "", v => pol.hard_to_undo[w] = v, true)); tr.appendChild(td); });
  g.appendChild(tr);
}
function toml() {
  const lines = ["# signoff policy, exported from the feed page"];
  WHO.forEach(w => { lines.push("", "[" + w + "]"); Object.keys(DATA.types).forEach(t => lines.push(t + ' = "' + pol[w][t] + '"')); });
  lines.push("", "[hard_to_undo]"); WHO.forEach(w => { if (pol.hard_to_undo[w]) lines.push(w + ' = "' + pol.hard_to_undo[w] + '"'); });
  return lines.join("\n");
}
function card(c) {
  const a = top(c), box = el("section", "card"), t = el("div", "top");
  t.appendChild(el("span", "pill " + a, STATUS[a]));
  const title = el("span", "title");
  if (c.url) { const l = el("a", null, c.title); l.href = c.url; l.rel = "noopener"; title.appendChild(l); } else title.textContent = c.title;
  t.appendChild(title); box.appendChild(t);
  box.appendChild(el("div", "meta", [c.id, c.date, c.agent ? "written by " + c.agent : ""].filter(Boolean).join(" · ")));
  if (c.error) box.appendChild(el("p", "warn", "Not reviewed: " + c.error));
  if (c.summary) box.appendChild(el("p", "summary", c.summary));
  if (c.spec_quote) box.appendChild(el("p", "spec", "From the request: “" + c.spec_quote + "”"));
  else if (c.spec_source === "") box.appendChild(el("p", "spec", "No request or spec found for this change, so every decision counts as the agent's own call."));
  if (c.diff_cut) box.appendChild(el("p", "warn", "The diff was long and was trimmed; less important files were left out."));
  c.decisions.forEach(d => {
    const x = act(d), dv = el("div", "dec" + (x === "silent" ? " dim" : ""));
    [DATA.types[d.type], DATA.who[d.who], d.undo === "hard" ? "Hard to undo" : "Easy to undo", LABEL[x]].forEach(s => dv.appendChild(el("span", "chip", s)));
    dv.appendChild(el("p", "what", d.what)); dv.appendChild(el("p", "why", d.why_it_matters));
    if (d.who_note) dv.appendChild(el("p", "warn", "Marked as the agent's call: " + d.who_note + "."));
    if (d.request_quote && d.who !== "agent") dv.appendChild(el("p", "why", "Request: “" + d.request_quote + "”"));
    if (d.evidence && d.evidence.length) {
      const ev = el("details", "ev"); ev.appendChild(el("summary", null, "Evidence (" + d.evidence.length + ")" + (d.evidence_ok === false ? ", not found in the code" : "")));
      d.evidence.forEach(e => { const p = el("pre"); p.appendChild(el("span", "f", e.file + (e.verified ? "" : "  (not found in the diff)"))); p.appendChild(document.createTextNode("\n" + e.quote)); ev.appendChild(p); });
      dv.appendChild(ev);
    }
    box.appendChild(dv);
  });
  if (!c.decisions.length && !c.error) box.appendChild(el("p", "why", "No product decisions found."));
  return box;
}
function render() {
  const tops = DATA.changes.map(top);
  document.getElementById("n-hold").textContent = tops.filter(a => a === "sign-off").length;
  document.getElementById("n-read").textContent = tops.filter(a => a === "notify").length;
  document.getElementById("n-all").textContent = DATA.changes.length;
  document.querySelectorAll(".tile").forEach(b => b.setAttribute("aria-pressed", b.dataset.f === filter));
  const list = document.getElementById("list"); list.textContent = "";
  const shown = DATA.changes.slice().reverse().filter(c => filter === "all" || top(c) === filter);
  shown.forEach(c => list.appendChild(card(c)));
  if (!shown.length) list.appendChild(el("p", "empty", filter === "sign-off" ? "Nothing is waiting for your sign-off." : "Nothing here."));
  const tx = document.getElementById("toml"); if (!tx.hidden) tx.value = toml();
}
document.getElementById("h").textContent = "What changed in " + DATA.name;
document.getElementById("sub").textContent = DATA.changes.length + " changes" + (DATA.from ? ", " + DATA.from + " to " + DATA.to : "");
document.querySelectorAll(".tile").forEach(b => b.addEventListener("click", () => { filter = b.dataset.f; render(); }));
document.getElementById("reset").addEventListener("click", () => { pol = JSON.parse(JSON.stringify(DATA.default_policy)); save(); grid(); render(); });
document.getElementById("export").addEventListener("click", () => { const tx = document.getElementById("toml"); tx.hidden = !tx.hidden; tx.value = toml(); });
grid(); render();
</script></body></html>
"""
