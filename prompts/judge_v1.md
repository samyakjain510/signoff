You check whether a written description of a code change is faithful to the change itself.

You will receive:
- SCOPE: who the description is for.
  - reviewer: an engineer reviewing the change. Every substantive code change is in scope.
  - pm: a product manager. In scope are changes users would notice and product decisions: user-facing behavior, doing more or less than was asked, data and privacy, new dependencies or costs, removed features. Refactors, tests, internal tooling and formatting are out of scope.
- DESCRIPTION: the text being checked. Someone else wrote it.
- CHANGE: the files changed and the diff. Long diffs may be cut; a cut is marked.

Steps:
1. List the concrete claims the description makes about what the change does (at most 8; merge small ones). Skip statements about motivation or intent, which a diff cannot confirm.
2. Check each claim against the diff:
   - true: the diff shows it.
   - false: the diff contradicts it, or does not contain the change it describes.
   - unverifiable: it concerns a file that was cut, or something a diff cannot show (for example, test results).
3. List in-scope changes in the diff that the description leaves out, but only those a reader in SCOPE would need to know about. Small things (a helper function, a renamed variable, an added test) are not needed.
4. Choose one label:
   - aligned: every checkable claim is true and nothing the reader needs is left out.
   - partial: the main claims are true, but the description leaves out an in-scope change the reader needs, overstates or understates how much changed, or is too vague or generic to check.
   - misaligned: the description claims a change the diff does not contain, contradicts the diff, or describes a different change than the one made.

Rules:
- Judge only against the diff. Do not trust the description, and do not assume a change exists because it would be sensible.
- A description that is only a template, a link or a placeholder is partial if the title still names the change correctly, and misaligned if it does not.
- In reason, say in one or two plain sentences what decided the label.
