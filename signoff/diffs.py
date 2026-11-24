"""Fit a diff into a model's input without dropping the files a PM cares about most.

Files are ranked. Tier 0 (database changes, access rules, package lists, hosting
and secrets) is always kept, cut per file only if huge. Lower tiers fill the
remaining room in order: pages and UI, then other source, then tests and docs.
Lock files, binaries and build output are never sent.
"""
from __future__ import annotations

import re

NOISE = re.compile(
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|composer\.lock|Gemfile\.lock|"
    r"\.min\.(js|css)$|\.map$|\.(png|jpe?g|gif|webp|ico|svgz|woff2?|ttf|otf|eot|pdf|zip|gz|mp4|mov|mp3)$|"
    r"(^|/)(node_modules|dist|build|\.next|\.astro|vendor)/)"
)
TIERS = [
    (0, re.compile(r"(^|/)(migrations?|supabase|prisma|db)/|\.sql$|schema\.prisma$", re.I)),
    (0, re.compile(r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|Pipfile|setup\.py|setup\.cfg|"
                   r"Gemfile|go\.mod|Cargo\.toml|composer\.json|build\.gradle(\.kts)?|pom\.xml)$")),
    (0, re.compile(r"(^|/)(\.env[^/]*|vercel\.json|netlify\.toml|wrangler\.(toml|jsonc?)|Dockerfile|docker-compose[^/]*|"
                   r"fly\.toml|render\.yaml|app\.yaml|firebase\.json|middleware\.[jt]s)$|\.github/workflows/", re.I)),
    (0, re.compile(r"(auth|policy|policies|permission|rls|privacy|consent|analytics|tracking|email|mail)", re.I)),
    (3, re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress|fixtures?)/|\.(test|spec)\.[a-z]+$|_test\.(py|go)$", re.I)),
    (3, re.compile(r"(^|/)(docs?)/|(^|/)(README|CHANGELOG|CONTRIBUTING|CLAUDE|AGENTS|LICENSE)[^/]*$", re.I)),
    (1, re.compile(r"(^|/)(app|pages|routes|views|templates|components|layouts|screens|public|content)/|"
                   r"\.(astro|tsx|jsx|vue|svelte|html|mdx|css|scss)$", re.I)),
]
PER_FILE_CHARS = 8_000
TIER0_FILE_CHARS = 16_000
TOTAL_CHARS = 60_000


def tier(path: str) -> int:
    for t, rx in TIERS:
        if rx.search(path):
            return t
    return 2


def split(diff: str) -> list[tuple[str, str]]:
    """Split a unified git diff into (path, chunk) pairs."""
    out = []
    for part in re.split(r"(?m)^(?=diff --git )", diff):
        if not part.strip():
            continue
        m = re.match(r"diff --git a/(\S+) b/(\S+)", part)
        out.append((m.group(2) if m else "?", part))
    return out


def fit(diff: str, total: int = TOTAL_CHARS) -> tuple[str, list[str], bool]:
    """Return (diff text to send, omitted file notes, whether anything was cut)."""
    files = []
    omitted: list[str] = []
    for i, (path, chunk) in enumerate(split(diff)):
        if NOISE.search(path) or "Binary files" in chunk[:400]:
            omitted.append(f"{path} (lock, binary or generated)")
            continue
        files.append((tier(path), i, path, chunk))
    files.sort()
    kept, used, cut = [], 0, False
    for t, i, path, chunk in files:
        cap = TIER0_FILE_CHARS if t == 0 else PER_FILE_CHARS
        if len(chunk) > cap:
            chunk = chunk[:cap] + f"\n[... {len(chunk) - cap} more characters of this file cut ...]\n"
            cut = True
        if t > 0 and used + len(chunk) > total:
            omitted.append(f"{path} (cut for length)")
            cut = True
            continue
        kept.append((i, chunk))
        used += len(chunk)
    kept.sort()
    return "".join(c for _, c in kept), omitted, cut
