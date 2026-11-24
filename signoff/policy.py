"""Control points: the PM chooses which kinds of decision need sign-off.

Each decision gets one action:
    sign-off  hold the change until the PM approves
    notify    show it in the feed as something to read
    silent    keep it in the feed history only

The policy is a small TOML file. See DEFAULT below.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

ACTIONS = ["silent", "notify", "sign-off"]
TYPES = ["user_facing", "scope", "data_privacy", "dependency_cost", "removed_feature"]
WHO = ["agent", "implied", "asked"]

DEFAULT = """\
# signoff policy: which product decisions need your sign-off before they ship.
# For each kind of decision choose "sign-off" (hold for approval), "notify"
# (show it in the feed) or "silent" (keep it in the feed history only).

[agent]            # decisions the agent made without being asked
user_facing = "notify"
scope = "notify"
data_privacy = "sign-off"
dependency_cost = "notify"
removed_feature = "sign-off"

[implied]          # decisions your request implied but did not spell out
default = "notify"

[asked]            # decisions you asked for in so many words
default = "silent"

[hard_to_undo]     # raises the action when a revert can't undo the effect
agent = "sign-off"
implied = "sign-off"
asked = "notify"
"""


def load(path: str | Path | None = None) -> dict:
    return tomllib.loads(Path(path).read_text() if path else DEFAULT)


def rank(a: str) -> int:
    return ACTIONS.index(a)


def action(pol: dict, d: dict) -> str:
    table = pol.get(d["who"], {})
    a = table.get(d["type"], table.get("default", "notify"))
    if d.get("undo") == "hard":
        h = pol.get("hard_to_undo", {}).get(d["who"])
        if h and rank(h) > rank(a):
            a = h
    # A decision whose evidence can't be found in the diff is shown, never held.
    if a == "sign-off" and d.get("evidence_ok") is False:
        a = "notify"
    return a


def change_action(pol: dict, decisions: list[dict]) -> str:
    return max((action(pol, d) for d in decisions), key=rank, default="silent")


def as_matrix(pol: dict) -> dict:
    """Expanded form for the feed page: who -> type -> action, plus hard_to_undo."""
    m = {w: {t: pol.get(w, {}).get(t, pol.get(w, {}).get("default", "notify")) for t in TYPES} for w in WHO}
    m["hard_to_undo"] = {w: pol.get("hard_to_undo", {}).get(w, "") for w in WHO}
    return m
