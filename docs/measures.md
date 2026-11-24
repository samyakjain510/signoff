# Measures, fixed before running

Written on 2026-11-23, before the tool or the judge had been run on any commit. Anything changed after a result came in is logged in `what-went-wrong.md` with the numbers before and after.

## What gets measured

The brief asks three things: does the PM catch the changes that matter, how many approvals does the tool ask for, and how often does a summary mislead.

### 1. Catch rate

**What "matters" means.** The 93% essay names the measure that matters most: "actions later reversed or regretted." So the ground truth comes from what Samyak did later. A decision *mattered* if a later request of his reversed or changed it.

- Source: every commit's request text (his messages in the Claude Code session that produced it), read in time order.
- For each later request, a model (Sonnet) is shown the decisions made in earlier commits of the same repo and asked which ones the request reverses or changes. Every match must quote his request exactly, and a script checks the quote. It also lists corrections that match no listed decision, which counts what the labeler missed.
- Claude reads every match by hand and logs any it rejects.
- Ground truth G: decisions the agent made on its own or that his request only implied (`who` = agent or implied) that he later reversed or changed. Decisions he asked for and later changed are reported apart, as changes of mind.

**Primary metric:** the share of G whose commit a policy holds for sign-off before it ships. **Secondary:** the share of G the PM is shown at all (sign-off or notify).

### 2. Approval load

- Commits held for sign-off, under each policy below, in total and per active week (weeks with at least one commit).
- Hit rate: the share of sign-off requests that contain a decision in G. The 93% essay argues a prompt should be refused often enough that people keep reading it, and this is the closest measure available without a live study.

### 3. Summaries that mislead

A judge model (Sonnet) compares a description with the diff and labels it with the PR-MCI scheme: aligned, partial (true but leaves out something the reader needs), or misaligned (claims something the diff does not do, or describes a different change).

- **Calibration first.** The judge labels 72 PRs from PR-MCI's human-labeled validation set (24 per human label, drawn with seed 7 from PRs short enough to fit without cutting). The judge is usable if Cohen's kappa against the human consensus is at least 0.6 on aligned vs not aligned. The 3-way kappa and per-label recall are reported either way.
- **Then:** the judge labels the tool's summary and the agent's own commit message for every commit, with the PM scope (only changes users would notice and product decisions count). "Misleads" means misaligned. Partial is reported separately as "incomplete."

### 4. Tool vs reference labels

Decision-level agreement between the tool (Haiku) and the reference labels (Sonnet): a tool decision matches a reference decision when they are in the same commit and their evidence shares a file. Reported as precision and recall, overall and for agent-made decisions, plus agreement on `who`.

### Update, 2026-11-23: the judge failed calibration, and a second version is tested on fresh PRs

Judge v1 scored kappa 0.29 on aligned vs not aligned (bar 0.6). It marked 15 of 24 human-aligned PRs as partial for leaving out details the annotators did not count. On misaligned vs the rest it reached 0.63, but that was not the registered test. Details are in `what-went-wrong.md`.

Judge v2 changes one thing: it only counts significant omissions. It was written after reading v1's disagreements on the 72 dev PRs, so it is scored on a separate test set it never saw. The test set has 24 aligned and 24 partial PRs, the 11 unused misaligned validation PRs, and 13 misaligned PRs from PR-MCI's second labeled set.

Fixed before running v2:

- v2 is used for summaries only if kappa is at least 0.6 on misaligned vs the rest, since "misleads" means misaligned. Aligned vs not is reported too, with the same 0.6 bar.
- If v2 fails, the essay reports judge results only as rough estimates with the calibration numbers next to them, and leans on cases read by hand.
- There will be no v3 tuned on the test set.

## Policies compared

Fixed now. Each one decides which commits are held for sign-off.

| Policy | Holds a commit when |
|---|---|
| A. Every commit | always |
| B. Paths (like CODEOWNERS) | it touches pages or routes, database migrations or SQL, package lists, hosting or workflow config, or env files |
| C. Code checks only | any exact code check fires (no model) |
| D. Tool, any decision | the tool lists any product decision |
| E. Tool, agent decisions | the tool lists a decision the agent made on its own |
| F. Tool, default tiers | the tool lists an agent or implied decision that is hard to undo, or an agent decision about data and privacy or a removed feature. Other agent decisions are shown as notices. |

Policy F is the shipped default. It follows the essay's tiers: hold what can't be undone, tell after for what can.

Two product rules apply to every tool policy (D, E, F), fixed before the first run:

- If the tool says the PM asked for or implied a decision, its quote from the request must be found in the request text. If it is not, the decision is treated as the agent's own call. The rule errs toward showing the PM more.
- If none of a decision's evidence quotes are found in the diff, the decision can be shown as a notice but never holds a change for sign-off.

## Models and freezing

- Reference labels: Sonnet, medium effort (Phase 1, done).
- Tool: Haiku. Its prompt is frozen after a format check on 3 commits. It is not tuned against any measure.
- Judge: Sonnet, medium effort. Its prompt is frozen before calibration.
- Correction finder: Sonnet, medium effort.
- All calls run through `claude -p` on the Pro plan with tools switched off.

### Added 2026-11-23, before running: stability

A gate that gives a different answer each time it runs is hard to trust. The tool is run a second time on 20 of the 60 commits (drawn with seed 7). Reported: how often the commit's outcome under the default tiers (held, to read, quiet) is the same on both runs, and how the number of decisions differs.

## Known limits, stated in advance

- One PM, two repos, 60 commits. The results describe this person's work, not PMs in general.
- G only contains what Samyak noticed and corrected. A decision that mattered but that he never noticed is invisible to it, so catch rate against G is an upper bound on what the tool would catch against everything that mattered.
- The reference labels were drafted by Sonnet and not checked line by line by a person. Only quote checks and the correction cross-check validate them.
- The judge is calibrated on engineer-facing PR descriptions (reviewer scope) and then used with PM scope.
