# Decision types

Every change goes into the feed. A **flag** means the change contains a product decision a PM would want to know was made. Each flag records three things:

1. **Type**: which kind of decision (five types below).
2. **Who decided**: whether the PM asked for it or the agent chose it.
3. **Undo**: whether reverting the code also reverses the effect.

A PM's sign-off policy is written in these terms, for example: "stop for any data-and-privacy decision the agent made on its own, and for anything that is hard to undo."

## The five types

### 1. User-facing behavior
Users would notice the change: what they see, what they can do, defaults, flows, or wording that changes meaning.

Does not count: refactors, performance work with no visible effect, typo fixes, internal tooling, tests.

Code checks: `page_added`, `page_moved`. Everything else needs judgment.

### 2. Scope
The change does more than was asked, or less. Extra features, skipped parts of the request, or edits to unrelated areas.

This type needs a request to compare against. In Samyak's repos the request is his messages in the Claude Code session that produced the commit (see `signoff/requests.py`). In public repos it is the linked issue.

Code checks: none. Always judgment.

### 3. Data and privacy
What data is collected, stored, shown, shared or deleted, and who can see or change it. Includes tracking, sign-in, access rules, messages sent to users, changes to how stored data is shaped, and third parties that receive visitor data.

Code checks: `tracking`, `access_rules`, `messages_users`, `data_shape_change`.

### 4. Dependency or cost
Anything new that can break, send a bill or need upkeep: packages, outside services, secrets and settings, scheduled jobs, hosting configuration.

Code checks: `new_package`, `outside_service`, `new_setting_or_secret`, `hosting_or_schedule`.

### 5. Removed or weakened feature
Something users had is gone, hidden or harder to reach.

Code checks: `page_removed`. Everything else needs judgment.

## Who decided

| Value | Meaning | Example |
|---|---|---|
| `asked` | The request asked for it in so many words. | Samyak asked to replace comment emails with a notifications box, so removing the emails was his call (commit `09c9667`). |
| `implied` | A sensible reading of the request needs it, though it wasn't spelled out. | Adding a database column to store a field the request asked for. |
| `agent` | The agent chose it without being asked. | An extra feature that rode along in the same commit. |

By default, only `agent` decisions are candidates for sign-off. Asking a PM to approve what they already asked for is the fastest way to teach them to click yes without reading.

## Undo

| Value | Meaning |
|---|---|
| `easy` | Reverting the commit puts things back as they were. |
| `hard` | Some effect survives a revert: data deleted or reshaped, messages already sent to users, data already shared with a third party, public links broken, money committed. |

This follows the reversibility tiers in the essay "How to keep human in the loop meaningful when people approve 93% of AI agent requests."

## Not a flag

Refactors, tests, docs, formatting, version bumps of existing packages with no behavior change, and developer tooling. These still appear in the feed, briefly.

## Code checks

`signoff/checks.py` runs these. They are exact and cheap, and each finding points to the file and line that triggered it. A finding is a signal, not a verdict: the labeler and the PM still decide whether it is a real decision.

| Check | Type | What it looks for | Known false alarms |
|---|---|---|---|
| `new_package` | Dependency or cost | A package name added to `package.json` or `requirements*.txt` | Dev-only tools |
| `outside_service` | Dependency or cost | Code that loads or calls an outside host (`fetch`, `src=`, `<link href>`, `import` from a URL) | None seen yet. Plain `<a href>` links are ignored on purpose. |
| `new_setting_or_secret` | Dependency or cost | A new environment variable read in code | Renamed variables |
| `hosting_or_schedule` | Dependency or cost | Edits to `vercel.json`, GitHub workflows, Docker or other hosting files | Cosmetic config edits |
| `tracking` | Data and privacy | Analytics or tracking libraries and calls | Words like `track(` used for other things |
| `access_rules` | Data and privacy | Database access policies, sign-in calls, `grant`/`revoke` | None seen yet. ARIA `role="..."` attributes are excluded. |
| `messages_users` | Data and privacy | Email and messaging libraries and send calls | Mentions in code comments |
| `data_shape_change` | Data and privacy | New or edited migration or schema files | None seen yet |
| `page_added` / `page_moved` | User-facing behavior | Page files added or renamed | Draft pages not linked anywhere |
| `page_removed` | Removed feature | Page files deleted | Pages replaced under a new name |
