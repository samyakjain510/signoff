# Lesson 1: From commits to decisions

## The problem this step solves

A product manager can't read every line an agent writes. What they need is a short list: *which decisions got made, and which of those did I not make myself?* Before we can build a tool that produces that list, we need examples where we already know the answer. This step builds those examples from Samyak's two repos.

## Words used here

- **Commit**: one saved change to the code, with a short message saying what it does.
- **Diff**: the exact lines a commit adds and removes. It is the ground truth of what changed; the message is only the author's description.
- **Pull request (PR)**: a proposed change that waits for review before it joins the main code. Samyak's repos have none. Agents commit straight to the main line, so any "approve before merge" step needs a different hook.
- **Co-authored-by line**: a note at the end of a commit message naming another author. 59 of 60 commits in the two repos name Claude.

## What we built

1. **Commit records** (`signoff/gitlog.py`). One tidy record per commit: date, author, agent, files changed, and the diff saved beside it.
2. **The request behind each commit** (`signoff/requests.py`). Every commit came out of a Claude Code session. Samyak's messages in that session, since the previous commit, are the closest thing to a spec. We find the `git commit` command in the session transcript and collect the messages before it. 59 of 60 commits link. Transcripts never leave the Mac.
3. **Exact code checks** (`signoff/checks.py`). Some PM calls can be spotted with a plain rule: a new package, a new tracking call, a database change, an email library, a deleted page. Rules are free, fast and explainable, and each finding points to a file and line.
4. **Reference labels** (`signoff/label.py`). Claude (Sonnet) reads the request, the commit, the check findings and the diff, and lists every decision with its type, who made it and whether it can be undone. Each decision must quote lines from the diff, and a script then confirms every quote exists.

## Ideas worth keeping

**Who decided matters as much as what was decided.** In one commit the agent removed the comment-email feature. That looks like a "removed feature" alarm, but Samyak had asked for exactly that. Flagging it would waste his attention. So every decision records whether the PM *asked* for it, whether the request *implied* it, or whether the *agent* chose it. The same commit also permanently deleted stored email preferences from the database. Nobody asked for that, and a revert can't bring the data back. That one should reach the PM.

**False alarms are the enemy.** The first version of the checks fired 187 times on the portfolio site. Almost all were noise: every drawing's `role="img"` accessibility label looked like an access rule. After tightening the rules, 28 findings were left, and they were real. A tool meant to fight approval fatigue can't start by causing it.

**The labeler and the tool should differ.** The labels are the answer key the tool will be scored against later. If the same model with the same inputs wrote both, a high score would only show that the model agrees with itself. The labeler uses a stronger model with the full request and diff. The tool will use a smaller model, and Samyak checks a sample of the labels by hand.

**Verify what you can verify.** "Don't invent quotes" is an instruction a model can ignore. "Every quote must be found in the diff" is a check a script can run. Where a rule can be checked mechanically, it is.
