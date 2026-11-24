# Lesson 5: Shipping a tool that runs on the user's own Claude

## The problem this step solves

The tool needs a model, and the budget is zero: no paid API, no server that makes model calls on anyone's bill. So every model call runs through the user's own Claude Code, and the tool is packaged so installing it takes two commands.

## Words used here

- **Headless call**: `claude -p` runs Claude Code once from a script and prints the result. It uses whatever plan the user is signed in with.
- **Structured output**: the call is given a JSON schema, so the answer comes back as data a script can check, instead of prose.
- **Plugin and skill**: a Claude Code plugin is a folder that adds abilities. A skill inside it is a short instruction file Claude reads when the task matches, here "show me what my agent changed."
- **Prompt injection**: text inside the material a model reads (a diff, an issue) that tries to give the model instructions.

## What we did

- Every call runs with tools switched off (`--tools ""`), so text in a diff can ask for anything and the model still cannot act on it.
- Calls run from an empty folder, so a repo's own instruction files don't leak into the prompt.
- Every quote the model gives is checked by a script: evidence against the diff, "you asked for this" against the request.
- Nothing from a diff is printed raw. One public diff held terminal control codes, so all text is cleaned before it reaches a terminal, and the feed page inserts it as plain text.
- The feed page is one self-contained file with no outside scripts or fonts, so it can be opened offline or hosted anywhere.
- Install is a Claude Code plugin with one skill; a headless session loaded it from disk and ran a dry run through the skill.

## Ideas worth keeping

**Spend the model where judgment is needed.** Reading git history, matching requests, finding new packages and applying the policy are plain code. One Haiku call per change does the part only a model can: say what changed for users and who decided. On Samyak's 60 commits that averaged about 10,000 input tokens and 18 seconds a commit.

**Make the expensive path visible.** The tool always offers a dry run that lists the changes and the number of model calls before any are made, and it caches results so a second run only pays for new changes.

**Waiting is better than failing, except at a gate.** Batch runs wait out a usage limit and resume. The pre-push hold does not wait: if a change can't be reviewed, the push is held and the reason is printed, and the PM decides.
