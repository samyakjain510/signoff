# Lesson 3: What the PM actually corrected

## The problem this step solves

"Did the tool catch the changes that matter?" needs a list of the changes that matter. Asking a model to decide what matters would only measure the model's taste. The 93% essay names a better test: actions that were later reversed or regretted. Samyak's own later requests are a record of exactly that.

## Words used here

- **Ground truth**: the answer key a method is scored against.
- **Behavioral ground truth**: an answer key taken from what people did, instead of what anyone says they would do.
- **Base rate**: how common something is before any tool looks at it. A tool that flags 1 in 3 commits is impressive if 1 in 30 commits matter and unimpressive if 1 in 3 do.

## What we did

1. For each of 44 requests with new messages, Sonnet saw the request and every decision found in earlier commits of the same repo, and listed the ones the request reverses or changes. Every match had to quote Samyak's words exactly, and a script checked the quote.
2. Claude read all 35 matches and rejected one ("give similar treatment to the Writing section as well" adds to earlier work; it does not correct it).
3. The answer key, G, is the decisions the agent made on its own, or that his request only implied, that he later reversed or changed.

## What we found

- G has 5 decisions, in 5 commits. That is too few to measure a catch rate precisely: a tool that catches 2 of 5 has a 95% interval from 12% to 77%.
- He went back on his *own* requests far more often than on the agent's choices: 13 of 63 decisions he asked for (21%), 4 of 36 his requests implied (11%), and 1 of 50 the agent made on its own (2%).
- 12 more corrections matched no decision at all. Almost all were wording and content: page intros, subheadings, titles, a salary figure in a drafted post.

## Ideas worth keeping

**Behavior can't tell "fine" from "unseen."** He corrected 1 of the agent's 50 own calls. Either 49 were fine, or he never noticed them. Nothing in the record separates the two. This is the gap the canary idea in the 93% essay exists to close: plant a known-bad change and see whether it is caught. It is also why the one question on the review sheet only he can answer, "would you have wanted to approve this before it shipped?", is worth more than another hundred model calls.

**Taste is not a decision type.** On a portfolio site, most of what the owner cares about is wording and look. A gate built on the five decision types will not see it. A feed that summarizes every change still helps, because it is where a PM notices "that heading is wrong" without opening a diff.

**Small numbers deserve their intervals.** Every rate in the write-up that rests on G carries its interval, so a reader can see how little five cases can prove.
