---
name: signoff
description: Show a product manager what a coding agent changed in a repo, in plain language, with the product decisions flagged (user-facing behavior, scope, data and privacy, new dependencies or costs, removed features) and the ones that need their sign-off. Use when the user asks what the agent changed or decided, what needs their approval, for a change feed of a repo or of a GitHub project's merged pull requests, or to set which kinds of decisions need sign-off.
---

# signoff

signoff reads a repo (read-only), sends each change to Claude Haiku through the user's own Claude Code (`claude -p`, tools off), and builds a feed page. It needs `python3` (3.11 or newer), `git`, and for GitHub repos the `gh` CLI signed in.

The tool lives two folders above this skill's base directory. Run it with that folder on `PYTHONPATH`:

```bash
PYTHONPATH="<plugin root>" python3 -m signoff <command> ...
```

## Steps

1. Work out the target. A local repo is a path (default: the current folder). A GitHub project is `OWNER/NAME`.
2. Always start with a dry run, which lists the changes and makes no model calls:
   - local: `python3 -m signoff scan <path> --limit 20 --dry-run`
   - GitHub: `python3 -m signoff github OWNER/NAME --prs 20 --agent-only --dry-run`
   Tell the user how many changes there are and that each one is one Haiku call on their plan (about 5 to 50 seconds each). Ask before running more than 30.
3. Run the same command without `--dry-run`, adding `--text`. Results are kept in `~/.signoff/<name>/`, so a second run only reviews new changes.
4. Report back in plain words: how many changes need sign-off and how many are to read, then each "NEEDS SIGN-OFF" item with its one-line reason. Give the path to `feed.html` and offer to open it.
5. To change which decisions need sign-off: `python3 -m signoff policy > signoff.toml`, edit the file with the user, then pass `--policy signoff.toml` (or rebuild with `python3 -m signoff feed ~/.signoff/<name> --policy signoff.toml --text`). The feed page also has a "Sign-off rules" panel that exports this file.

## Rules

- Do not print raw diffs to the terminal. They can contain terminal control codes. The tool's own text output is cleaned.
- For a local repo, the tool reads the user's requests from Claude Code transcripts in `~/.claude/projects` on this machine. They are never sent anywhere except to the model call. Pass `--transcripts none` if the user does not want that.
- Flags are drafted by a model and can be wrong. Each one quotes the code lines it is based on, and the feed marks quotes that could not be found.
