You help study how a product manager (PM) oversees a coding agent. You will see one REQUEST the PM sent the agent, and a list of EARLIER DECISIONS: product decisions found in changes the agent made before this request, in the same project.

Find the earlier decisions this request reverses or changes.

- reverse: the PM asks to undo, remove or roll back what the decision put in place.
- change: the PM keeps the thing but asks to alter the choice itself (different wording, behavior, default, placement, data handling, provider), because the earlier choice was not what they wanted.

Do not count:
- asking for more on top of an earlier decision (extending is not correcting);
- reporting a bug or crash in carrying out a decision, unless the PM also changes the choice;
- general new work that happens to touch the same page or file;
- the PM repeating or confirming something.

For each match, copy the exact words from REQUEST that show it into request_quote (a short phrase is enough; copy it exactly), and give a one-sentence reason.

Also list in other_corrections any place where the request clearly reverses or changes something the agent did earlier that matches none of the listed decisions. Copy the exact words into request_quote.

Be strict. If you are unsure whether a request corrects a decision, leave it out. Most requests correct nothing.
