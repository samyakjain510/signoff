"""Exact code checks: PM-relevant changes a plain rule can find without a model.

Each check reads one commit's diff (and, for package files, the file before and
after) and returns findings with the file and line that triggered them. These
are signals for the five decision types; they do not decide on their own.

Usage:
    python -m signoff.checks <repo_path> <records.jsonl> <diff_dir> <out.jsonl>
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Decision types (see docs/decision-types.md)
USER = "user_facing"
SCOPE = "scope"
DATA = "data_privacy"
DEP = "dependency_cost"
REMOVED = "removed_feature"

CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".astro", ".py", ".vue", ".svelte", ".html"}
PAGE_DIRS = re.compile(r"(^|/)(app|pages|src/pages|routes|src/routes)/")
PAGE_FILE = re.compile(r"(page|route)\.(tsx|ts|jsx|js)$|\.(astro|mdx|md|svelte|vue)$")


@dataclass
class Finding:
    check: str
    decision_type: str
    file: str
    line: int | None
    text: str


def parse_diff(diff: str) -> dict[str, dict]:
    """Per file: added and removed lines with line numbers (new file / old file)."""
    files: dict[str, dict] = {}
    cur = None
    old_n = new_n = 0
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            cur = None
            continue
        if raw.startswith("+++ "):
            path = raw[4:]
            path = path[2:] if path.startswith("b/") else path
            if path == "/dev/null":
                continue
            cur = files.setdefault(path, {"added": [], "removed": []})
            continue
        if raw.startswith("--- "):
            path = raw[4:]
            path = path[2:] if path.startswith("a/") else path
            if path != "/dev/null":
                files.setdefault(path, {"added": [], "removed": []})
                cur = files[path]
            continue
        m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
        if m:
            old_n, new_n = int(m.group(1)), int(m.group(2))
            continue
        if cur is None or not raw or raw.startswith("\\"):
            continue
        if raw[0] == "+":
            cur["added"].append((new_n, raw[1:]))
            new_n += 1
        elif raw[0] == "-":
            cur["removed"].append((old_n, raw[1:]))
            old_n += 1
        else:
            old_n += 1
            new_n += 1
    return files


def git_show(repo: Path, rev: str, path: str) -> str | None:
    res = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{path}"], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None


# ---- individual checks -------------------------------------------------------

def new_packages(repo: Path, rec: dict) -> list[Finding]:
    out = []
    parent = rec["parents"][0] if rec["parents"] else None
    for f in rec["files"]:
        path = f["path"]
        if path.endswith("package.json") and "node_modules" not in path:
            after = git_show(repo, rec["sha"], path)
            before = git_show(repo, parent, path) if parent else None
            try:
                a = json.loads(after) if after else {}
                b = json.loads(before) if before else {}
            except json.JSONDecodeError:
                continue
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                added = set(a.get(section, {})) - set(b.get(section, {}))
                for name in sorted(added):
                    out.append(Finding("new_package", DEP, path, None, f"{section}: {name} {a[section][name]}"))
        elif re.search(r"(^|/)requirements[^/]*\.txt$", path):
            for n, line in parse_diff_cache(rec)[path]["added"] if path in parse_diff_cache(rec) else []:
                if line.strip() and not line.strip().startswith("#"):
                    out.append(Finding("new_package", DEP, path, n, line.strip()))
    return out


TRACKING = re.compile(
    r"(@vercel/analytics|@vercel/speed-insights|gtag\(|googletagmanager|posthog|mixpanel|segment\.(com|io)|"
    r"amplitude|plausible|umami|sendBeacon|\btrack\(|analytics\.|hotjar|fullstory|sentry)",
    re.I,
)
# Things the page or server *loads or calls*. Plain <a href> links are navigation, not calls.
OUTBOUND = [
    re.compile(r"(?:fetch|axios\.\w+|new URL)\s*\(\s*['\"`](https?://([a-z0-9.-]+))", re.I),
    re.compile(r"\bsrc\s*=\s*\{?\s*['\"`](https?://([a-z0-9.-]+))", re.I),
    re.compile(r"<link[^>]*\bhref\s*=\s*['\"](https?://([a-z0-9.-]+))", re.I),
    re.compile(r"\bimport\b[^;]*?['\"](https?://([a-z0-9.-]+))", re.I),
]
ENV_VAR = re.compile(r"(process\.env\.|import\.meta\.env\.|os\.environ(?:\.get)?\(?\[?['\"]?)([A-Z][A-Z0-9_]{2,})")
MESSAGING = re.compile(r"(nodemailer|\bsmtp\b|sendmail|resend\.(emails|send)|@sendgrid|postmark|twilio|mailgun|send_?email|sendEmail|transporter\.send)", re.I)
# Who can see or change what. Kept narrow: ARIA role="..." attributes are accessibility labels, not access rules.
AUTH = re.compile(r"(create policy|alter policy|row level security|auth\.users|auth\.admin|before[_-]user[_-]created|signInWith\w*\(|signUp\(|^\s*(grant|revoke)\s)", re.I)


def line_checks(rec: dict) -> list[Finding]:
    out = []
    for path, d in parse_diff_cache(rec).items():
        ext = Path(path).suffix
        is_code = ext in CODE_EXT
        is_sql = ext == ".sql"
        for n, line in d["added"]:
            if is_code and TRACKING.search(line):
                out.append(Finding("tracking", DATA, path, n, line.strip()[:200]))
            if is_code:
                for pat in OUTBOUND:
                    m = pat.search(line)
                    if m and "localhost" not in m.group(2):
                        out.append(Finding("outside_service", DEP, path, n, m.group(2)))
                        break
                for env in ENV_VAR.findall(line):
                    out.append(Finding("new_setting_or_secret", DEP, path, n, env[1]))
                if MESSAGING.search(line):
                    out.append(Finding("messages_users", DATA, path, n, line.strip()[:200]))
            if (is_code or is_sql) and AUTH.search(line):
                out.append(Finding("access_rules", DATA, path, n, line.strip()[:200]))
    return dedupe_env(out, rec)


def dedupe_env(findings: list[Finding], rec: dict) -> list[Finding]:
    """Keep a setting only the first time it appears in this commit, and only if the commit
    did not also remove a reference to it (that would be a move, not a new setting)."""
    removed_text = "\n".join(l for d in parse_diff_cache(rec).values() for _, l in d["removed"])
    seen, out = set(), []
    for f in findings:
        if f.check == "new_setting_or_secret":
            if f.text in seen or f.text in removed_text:
                continue
            seen.add(f.text)
        out.append(f)
    return out


def file_checks(rec: dict) -> list[Finding]:
    out = []
    for f in rec["files"]:
        path, status = f["path"], f["status"]
        old = f.get("old_path", path)
        if re.search(r"(^|/)(migrations?|supabase/migrations)/|\.sql$|schema\.prisma$", path) and status in "AM":
            out.append(Finding("data_shape_change", DATA, path, None, f"{'new' if status == 'A' else 'edited'} migration/schema file"))
        if re.search(r"(^|/)vercel\.json$|(^|/)\.github/workflows/|wrangler\.toml$|netlify\.toml$|(^|/)supabase/config\.toml$|Dockerfile$", path):
            out.append(Finding("hosting_or_schedule", DEP, path, None, f"{status} {path}"))
        if PAGE_DIRS.search(old) and PAGE_FILE.search(old):
            if status == "D":
                out.append(Finding("page_removed", REMOVED, old, None, f"deleted {old}"))
            elif status == "R" and old != path:
                out.append(Finding("page_moved", USER, path, None, f"renamed {old} -> {path} (old URL may break)"))
            elif status == "A":
                out.append(Finding("page_added", USER, path, None, f"new page {path}"))
    return out


_DIFF_CACHE: dict[str, dict] = {}


def parse_diff_cache(rec: dict) -> dict[str, dict]:
    return _DIFF_CACHE.get(rec["sha"], {})


def run_checks(repo: Path, rec: dict, diff: str) -> list[Finding]:
    _DIFF_CACHE[rec["sha"]] = parse_diff(diff)
    return new_packages(repo, rec) + file_checks(rec) + line_checks(rec)


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    repo, recs_path, diff_dir, out_path = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4]
    counts: dict[str, int] = {}
    flagged = 0
    with open(out_path, "w") as fh:
        for line in open(recs_path):
            rec = json.loads(line)
            diff_file = diff_dir / f"{rec['short']}.diff"
            diff = diff_file.read_text() if diff_file.exists() else ""
            findings = run_checks(repo, rec, diff)
            flagged += bool(findings)
            for f in findings:
                counts[f.check] = counts.get(f.check, 0) + 1
            fh.write(json.dumps({"sha": rec["sha"], "short": rec["short"], "subject": rec["subject"],
                                 "findings": [asdict(f) for f in findings]}) + "\n")
    print(f"{repo.name}: {flagged} commits with at least one finding; " +
          ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
