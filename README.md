# signoff

A plain-language feed of what your coding agent changed, with the product decisions flagged, and a hold at `git push` for the kinds of decisions you want to approve first.

It is built for a product manager (PM) who works with a coding agent that commits code: you read what changed for users, see which decisions you asked for and which the agent made on its own, and choose which kinds stop for your sign-off.

**Demo:** [the feed for 25 merged agent pull requests in Morphic](https://samyakjain510.github.io/signoff/demo/), an open-source AI search app. The page is one file, [docs/demo/index.html](docs/demo/index.html).

## What it does

For each commit (or merged pull request), signoff:

1. reads the change read-only, plus what you asked for: your messages in the Claude Code session that produced it, or the issue a pull request links;
2. runs exact code checks for things like new packages, database changes, deleted pages, tracking and email sending;
3. asks Claude Haiku, through your own Claude Code with tools switched off, for a two-sentence summary of what changed for users and a list of product decisions, each with its type, who decided (you asked, your request implied it, or the agent's own call), whether a revert can undo it, and the code lines it is based on;
4. checks every quote with a script and applies your sign-off rules.

Decision types: user-facing behavior, scope (more or less than you asked), data and privacy, new dependencies or costs, and removed features. See [docs/decision-types.md](docs/decision-types.md).

## Install

In Claude Code:

```
/plugin marketplace add samyakjain510/signoff
/plugin install signoff@signoff
```

Then ask Claude something like "what did the agent change in this repo this week, and what needs my sign-off?" The skill runs a dry run first and tells you how many model calls it will make.

Without the plugin:

```bash
git clone https://github.com/samyakjain510/signoff && cd signoff
python3 -m signoff scan /path/to/your/repo --limit 20 --text
```

You need Python 3.11 or newer, git, and Claude Code signed in (any plan). For GitHub projects you also need the `gh` CLI. There are no other dependencies.

## Use

```bash
python3 -m signoff scan [REPO] --limit 20 --text        # recent commits in a local repo
python3 -m signoff github OWNER/NAME --prs 20 --agent-only --text
python3 -m signoff feed ~/.signoff/NAME --policy signoff.toml --text   # rebuild with other rules
python3 -m signoff policy > signoff.toml                 # start your own rules
python3 -m signoff hook install                          # hold pushes that need your sign-off
python3 -m signoff approve <commit>                      # approve a held commit (in a terminal)
```

Every run writes `feed.html` to `~/.signoff/NAME/` and caches results, so a second run only pays for new changes. Add `--dry-run` to see the changes and the number of model calls without making any.

## Sign-off rules

Each decision gets one action: **sign-off** (hold it), **notify** (put it on your reading list) or **silent** (keep it in the history). The default holds what a revert can't undo, plus the agent's own calls about data and removed features, and tells you after about the rest.

| | Agent's own call | Implied by your request | You asked for it |
|---|---|---|---|
| User-facing | notify | notify | silent |
| Scope | notify | notify | silent |
| Data and privacy | **sign-off** | notify | silent |
| Dependency or cost | notify | notify | silent |
| Removed feature | **sign-off** | notify | silent |
| Hard to undo | **sign-off** | **sign-off** | notify |

Put a `signoff.toml` at the root of a repo to change them, or change them on the feed page and export the file. Two rules always apply: if the tool says you asked for something, its quote from your request must exist, or the decision counts as the agent's; and a decision whose evidence can't be found in the code is shown but never held.

## The hold at push

`python3 -m signoff hook install` adds a git pre-push hook. Before a push, it reviews the commits being pushed and stops the push if any decision needs your sign-off. Approvals are recorded in `.git/signoff/` and can only be typed by a person in a terminal. Coding agents run commands without a terminal, so an agent that hits the hold can tell you about it but cannot clear it. Git lets anyone skip hooks with `--no-verify`; if you rely on the hold, deny that flag in your agent's permissions.

## What I measured

I ran signoff on my own two projects (60 commits, 59 written with Claude Code) and checked it against what I did later. The method was written down before any run, in [docs/measures.md](docs/measures.md).

- **Approvals asked.** The default rules hold 20 of 60 commits, 5 per active week. Holding every agent decision would hold 48.
- **Catches.** I later reversed or changed 5 decisions that the agent made on its own or that my request only implied. The default holds 2 of them before they ship and shows all 5 in the feed. All 4 commits with an agent decision a revert can't undo are held.
- **Summaries that mislead.** None of 60 tool summaries were judged misleading (95% interval 0 to 6%), by a judge that first had to pass a test against human labels. It failed its first try.
- **Weak spot.** The tool credits decisions to the PM's request too readily. More in [the write-up](docs/essay.md).

Numbers are in [results/](results/), mistakes in [docs/what-went-wrong.md](docs/what-went-wrong.md), and a step-by-step explanation in [docs/learn/](docs/learn/).

## Privacy and safety

- Reading the repo is read-only. The only things written to a repo are the optional hook and the approvals file, both inside `.git/`.
- For local repos, your Claude Code transcripts in `~/.claude/projects` are read on your machine to find your requests. That text goes only into the model call. Pass `--transcripts none` to skip it.
- Model calls run with tools switched off, from an empty folder, so text in a diff can't make the model act.
- Text from diffs is cleaned of terminal control codes before it is printed, and inserted into the feed page as text, never as HTML.

## Limits

- Flags are drafted by a model and can be wrong. Each one quotes the lines it is based on.
- Without a spec (no linked issue, no transcript), every decision counts as the agent's own call, so more gets held.
- The evidence comes from one PM and two small projects.

## Repo layout

- `signoff/`: the tool (standard library only)
- `skills/signoff/`, `.claude-plugin/`: the Claude Code plugin
- `docs/`: the write-up, measures, lessons, log and demo
- `scripts/`, `prompts/`: the study (labeling, judging, replay)
- `results/`: aggregate numbers
- `tests/`: unit tests (`python3 -m unittest tests/test_*.py`)

## License

MIT. Free and open source, with no paid tier.
