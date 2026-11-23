# What went wrong

Mistakes and surprises, and what changed because of them. Material for the write-up.

## 2026-11-22: the first code checks raised 125 false alarms on a site with no logins

The first version of the "access rules" check matched any line containing `role=`. Every SVG drawing in the portfolio carries `role="img"`, an accessibility label for screen readers, so the check fired 125 times on a site that has no user accounts. The "outside service" check also counted ordinary links to papers and LinkedIn as if the site were calling those services.

**What changed:** the access check now looks only for database policies, sign-in calls and `grant`/`revoke`. The outside-service check counts only things the page loads or calls (`fetch`, `src=`, `<link href>`, `import`), and ignores links a visitor clicks. Portfolio findings dropped from 187 to 28, and the ones left are real (new pages, new packages, Google Fonts).

**Why it matters:** a noisy flag is how approval fatigue starts. Every rule now gets its trigger text inspected before its count is trusted.

## 2026-11-23: the "request" behind a commit was missing a third of what Samyak said

Reviewing the labels turned up two gaps in how we read his requests out of Claude Code transcripts.

1. **Claude's own summaries were counted as his words.** When a long session runs out of room, Claude Code writes a summary of the work so far and stores it as if the user had sent it. Four commits had this summary in their "request." Labels built on it said "you asked for this" based on Claude's paraphrase.
2. **Messages sent while the agent was working were missed.** When Samyak types while Claude is mid-task, Claude Code stores the message as a queued attachment instead of a normal user message. 19 of 60 commits (almost a third) had at least one of these missing from their request. In one case he asked for separate Interviews and Internships sections mid-task, and the label said the agent had invented the split.

**What changed:** summaries are skipped (by flag and by their fixed opening line), and mid-task messages from a human are read in. Unit tests cover both. The 21 affected commits were relabeled (two were hit by both gaps), and the old labels are kept in `data/labels/superseded.jsonl` so the effect can be measured.

**Why it matters:** "who decided" is the field that keeps the tool from nagging a PM about their own decisions. If the tool can't see everything the PM said, it will wrongly blame the agent. Mid-task steering is common in Samyak's work, so any oversight tool for agent-written code has to read it.

## 2026-11-23: the labeler reported a message mismatch in 55 of 60 commits

The labeling prompt asked for a note whenever the diff holds "significant changes the message does not mention." Nearly every multi-part commit trips that, so the count is useless as a finding. The hand-labeled research set (PR-MCI) found partial or misaligned descriptions in about a quarter of its sample.

**What changed:** nothing yet. The mismatch notes are not reported as a result. Phase 2 will define the threshold before measuring, and calibrate the judge against the PR-MCI human labels first.

## 2026-11-22: one public diff contained terminal control codes

Fetching 360 public agent PRs, GitHub's CLI refused to print one diff because it contained terminal escape sequences: hidden codes that can change what a terminal shows or does. It is probably colored test output, but a tool that reads strangers' code can't assume that.

**What changed:** the tool never prints raw diffs to a terminal. Diffs are written to files and passed to the model as data with tools switched off. Final sample: 349 diffs fetched, 4 skipped as over 300 KB (3 Cursor, 1 Codex), 7 unavailable (6 deleted PRs or repos, 1 with control codes). Each agent keeps at least 54 PRs.

## 2026-11-22: commit IDs were not in the session transcripts

The plan was to match each commit to the Claude Code session that made it by searching transcripts for the commit ID. That found nothing, because commits were made in quiet mode and git printed no ID. The IDs only appeared later, when Claude listed the history.

**What changed:** we now match on the `git commit` command itself, using the commit's subject line, and take the earliest match so forked sessions don't double count. 59 of 60 commits link. The one miss was made by a setup tool, not an agent.
