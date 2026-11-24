# Lesson 4: Control points and what they cost

## The problem this step solves

A PM can't approve every change, and the 93% essay shows what happens when they try: they stop reading. So the question is which changes to hold, and what each choice costs in interruptions and buys in catches.

## Words used here

- **Control point**: a place in the workflow where a change waits for a person. Here it is `git push`, because Samyak's agents commit straight to the main branch and there are no pull requests to review.
- **Policy**: the rule that decides which changes stop at the control point.
- **Approval load**: how often the PM is stopped.
- **Hit rate**: of the changes a policy stops, the share that held something the PM later reversed. The 93% essay argues that if nearly every request is approved, the product is asking about the wrong things.
- **Pre-push hook**: a script git runs before a push. If it fails, the push does not happen.

## What we did

Six policies were fixed in advance and replayed over the 60 commits. Policies A to C need no model. D to F use the tool's flags.

| Policy | Commits held | Per active week | Later-corrected decisions held (of 5) | Holds that touched anything later corrected |
|---|---|---|---|---|
| A. Every commit | 60 | 15.0 | 5 | 13 of 60 (22%) |
| B. Paths, like CODEOWNERS | 40 | 10.0 | 4 | 12 of 40 (30%) |
| C. Code checks, no model | 21 | 5.2 | 3 | 9 of 21 (43%) |
| D. Tool, any decision | 56 | 14.0 | 5 | 13 of 56 (23%) |
| E. Tool, agent decisions | 48 | 12.0 | 4 | 11 of 48 (23%) |
| F. Tool, default tiers | 20 | 5.0 | 2 (all 5 shown) | 7 of 20 (35%) |

## Ideas worth keeping

**Every policy mostly asks about things the PM keeps.** Even the best hit rate means more than half of the holds were for changes he never went back on. That is the 93% problem showing up inside a smarter gate.

**Free rules hold their own.** Plain code checks (new packages, database changes, deleted pages, email libraries) held about as many commits as the model-based default and caught about as much. What the model adds is the explanation: a plain summary, who decided, and the evidence lines.

**Hold by reversibility.** All 4 commits containing an agent decision that a revert can't undo (deleted data, for example) are held by the default. That is the one clean result here, and it matches the essay's tiers.

**"Who decided" is the weak link.** The tool (Haiku) called 158 of its 274 decisions the agent's own, where the reference labels say 50 of 149. And in 16 cases where the reference says the agent decided, the tool said the PM asked. That is the risky direction, because it hides a decision behind the PM's own words. The quote check only proves the phrase exists in the request; it can't prove the phrase supports the decision.

**A gate has to be stable.** Run twice on the same 20 commits, the hold decision matched on 19.

**A gate an agent can approve is not a gate.** Approvals can only be typed in a terminal. Coding agents run commands without one, so an agent that hits the hold can report it but cannot clear it. It could still bypass git hooks with `--no-verify`, so a team that relies on the hold should also deny that flag in the agent's permissions.
