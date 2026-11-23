# What went wrong

Mistakes and surprises, and what changed because of them. Material for the write-up.

## 2026-11-22: the first code checks raised 125 false alarms on a site with no logins

The first version of the "access rules" check matched any line containing `role=`. Every SVG drawing in the portfolio carries `role="img"`, an accessibility label for screen readers, so the check fired 125 times on a site that has no user accounts. The "outside service" check also counted ordinary links to papers and LinkedIn as if the site were calling those services.

**What changed:** the access check now looks only for database policies, sign-in calls and `grant`/`revoke`. The outside-service check counts only things the page loads or calls (`fetch`, `src=`, `<link href>`, `import`), and ignores links a visitor clicks. Portfolio findings dropped from 187 to 28, and the ones left are real (new pages, new packages, Google Fonts).

**Why it matters:** a noisy flag is how approval fatigue starts. Every rule now gets its trigger text inspected before its count is trusted.

## 2026-11-22: commit IDs were not in the session transcripts

The plan was to match each commit to the Claude Code session that made it by searching transcripts for the commit ID. That found nothing, because commits were made in quiet mode and git printed no ID. The IDs only appeared later, when Claude listed the history.

**What changed:** we now match on the `git commit` command itself, using the commit's subject line, and take the earliest match so forked sessions don't double count. 59 of 60 commits link. The one miss was made by a setup tool, not an agent.
