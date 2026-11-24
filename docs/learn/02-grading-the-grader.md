# Lesson 2: Grading the grader

## The problem this step solves

One of the three things this project measures is how often a summary misleads. Nobody can read 120 summaries against 120 diffs by hand, so a model does it. That model is called the judge. But a judge is a model too, and it can be wrong in a consistent direction. Before any number it produces goes in the write-up, the judge itself has to be scored against people.

## Words used here

- **Judge**: a model asked to grade another model's output (here: does this description match this code change?).
- **Calibration**: comparing the judge with human answers on cases where the human answer is already known.
- **Cohen's kappa**: agreement between two raters, adjusted for the agreement you would get by chance. 1 is perfect, 0 is no better than guessing. Two people who always answer "aligned" on a set that is 78% aligned would agree 78% of the time by luck, and kappa corrects for that.
- **Pre-registration**: writing down what you will measure and what counts as a pass before you see any result, so the bar can't drift toward whatever you get.
- **Development and test sets**: you are allowed to look at mistakes on the first and change the method. The second is kept unseen and used once, to score the changed method fairly.

## What we did

1. Took PR-MCI, a research dataset in which two people labeled agent-written pull request descriptions as aligned, partial or misaligned with the code. They agreed with each other at kappa 0.89.
2. Wrote the bar into `docs/measures.md` before running anything: the judge is usable if kappa is at least 0.6.
3. Ran judge v1 on 72 of those PRs (24 per label). It scored 0.29. It failed.
4. Read every disagreement. v1 was too strict: it called 15 of 24 human-"aligned" descriptions "partial" for leaving out details. Some of its catches were fair, but it was applying a different standard from the humans.
5. Wrote v2 with one change (count only significant omissions) and scored it on 71 *different* PRs it had never seen. It passed: 0.69 on aligned vs not, 0.68 on misaligned vs the rest.

## Ideas worth keeping

**A failed check is a result, not a setback.** If we had skipped calibration, the write-up would have said most agent commit messages are flawed. That would have been the judge's strictness, not a fact about the messages.

**Never score a fix on the cases that inspired it.** v2 was written by reading v1's mistakes on the 72 development PRs. Scoring v2 on those same PRs would have rewarded memorizing them. The separate test set is what makes v2's 0.69 believable.

**Report the direction of the error, not just its size.** v2 catches 22 of 24 misleading descriptions, but about 3 in 10 of its "misleading" calls are ones the humans rated only "partial." So it leans harsh, and any rate it reports is more likely too high than too low.

**Some cases can't be graded at all.** One test PR was blocked by a safety filter on every try. It is excluded and counted, not quietly dropped.
