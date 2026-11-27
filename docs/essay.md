# What a sign-off rule would have caught in 60 commits my coding agent wrote

> Draft, still under review. The wording may change.

*I built a tool that tells a product manager what a coding agent changed and which decisions it made on its own. Then I replayed my own commit history through it and scored each sign-off rule against what I later went back and changed.*

## The problem

I build my side projects with Claude Code. Between late October and mid-November 2026 it wrote 59 of the 60 commits in two of them: my portfolio site, and a site where Kellogg students share their recruiting interviews. Neither project has a single pull request. The agent commits to the main branch and the site redeploys.

Each commit carries several decisions. In one, I asked the agent to drop comment emails and add an in-app notification bell. The same commit ran a database migration that permanently removed every user's email-preference setting, their unsubscribe links and the table that logged sent emails. Nothing in my request mentioned stored data, and a revert would not have brought it back.

The tools I could find for watching this kind of work are code review tools, written for engineers. As the person who owns these products, I wanted two things from each commit: a plain account of what changed for users, with the decisions I had not asked for marked, and a chance to approve the ones I care about before they ship.

Earlier this month I wrote about approval fatigue. By Anthropic's count, Claude Code users accept 93% of its permission prompts, and a question that is almost always answered yes stops being read. So a sign-off step for product decisions also has to ask rarely.

## What I built

I built signoff with Claude Code, which also did most of the analysis below.

signoff reads a repository without changing it. For each commit it finds what I asked for. In my case that is my messages in the Claude Code session that produced the commit, read from the session logs on my laptop. It runs a few exact checks for things like new packages, database migrations, deleted pages and email sending. Then one call to Claude Haiku, made through my own Claude Code with its tools switched off, writes a two-sentence summary of what changed for users and lists the product decisions in the commit.

Each decision gets a type (user-facing behavior, scope, data and privacy, a new dependency or cost, or a removed feature), who made it (I asked, my request implied it, or the agent's own call), whether a revert can undo it, and the lines of code it rests on. A script then checks that every quoted line exists in the code change and every quote from my request exists in my request.

Rules I set decide what happens to each decision: hold it for my sign-off, put it on a reading list, or keep it in the history. The default holds anything a revert can't undo, plus the agent's own calls about data and removed features. A git hook enforces the hold when code is pushed. Approvals only count when a person types them in a terminal, and a coding agent runs its commands without one.

## How I scored it

I wanted three numbers: whether I would catch the changes that matter, how many approvals the tool asks for, and how often a summary misleads.

The first needs a list of the changes that matter, and asking a model for that list would only measure the model's taste. In the approval-fatigue essay I argued that the measure that matters most is actions later reversed or regretted, and my own later requests to the agent record exactly those. For each of 44 requests, Claude Sonnet compared what I asked with every decision from earlier commits and listed the ones I reversed or changed, quoting my words. A script checked every quote. Claude then read all 35 matches by hand and threw one out.

The reference labels for all 149 decisions in the 60 commits came from Sonnet reading the full request and code change. The tool runs on the smaller Haiku, so it is never graded by a copy of itself. No person has checked those labels line by line, and that is the largest gap in this study.

I wrote the measures and the pass marks down before running anything, and logged every mistake along the way. Both are in the repository.

## What I found

### I went back on my own requests more than on the agent's choices

I later reversed or changed 13 of the 63 decisions I had asked for (21%), 4 of the 36 my requests implied (11%), and 1 of the 50 the agent made on its own (2%). Another 12 corrections matched no labeled decision at all, and almost all of those were about wording, such as a page intro or an essay title.

The 2% could mean the agent's own calls were fine, or that I never noticed them, and my history can't separate the two. That is the strongest case I have found for the canary approvals I proposed in the earlier essay: now and then, plant a change the reviewer should refuse, and record whether they do.

### Every rule mostly stops changes I kept

I fixed six rules in advance and replayed all 60 commits through each. The 5 decisions in the fourth column are the ones I later reversed that the agent had made on its own or that my request had only implied.

| Rule | Commits held | Per active week | Of those 5, held before shipping | Holds touching anything I later changed |
|---|---|---|---|---|
| Every commit | 60 | 15 | 5 | 13 of 60 (22%) |
| File paths, like a CODEOWNERS file | 40 | 10 | 4 | 12 of 40 (30%) |
| Exact code checks, no model | 21 | 5.2 | 3 | 9 of 21 (43%) |
| Tool: any decision | 56 | 14 | 5 | 13 of 56 (23%) |
| Tool: any decision the agent made | 48 | 12 | 4 | 11 of 48 (23%) |
| Tool: the default rules | 20 | 5 | 2, and all 5 shown in the feed | 7 of 20 (35%) |

Even under the default, 13 of the 20 holds were for commits I never went back on, so about two holds in three would most likely have ended with me approving something I was going to keep.

Five cases are too few to rank the rules on catches. Catching 2 of 5 is consistent with a true rate anywhere from 12% to 77%.

### Plain code checks held about as well as the model

The exact checks need no model and hold 21 commits, 9 of which contained something I later changed. The model-based default holds 20, with 7. At these sample sizes that difference means little. Where the model helped was the explanation that came with each hold: what changed in plain words and who decided, with the code lines behind every flag.

### All four irreversible commits were held

The reference labels found 5 decisions the agent made on its own that a revert can't undo, spread over 4 commits: the email-preference deletion, the data the interview site stores about each student, a pair of tables that record site visits, and a comments feature with its own table and access rules. The default rules hold all 4. This is the cleanest result in the study, and it matches the tiers from the approval-fatigue essay: hold what can't be undone, and tell me afterwards about the rest.

### Summaries rarely misled

To grade summaries I needed a judge, a model that compares a description with the code, and the judge needed grading first. I tested it on pull requests that two annotators had already labeled for whether the description matches the code, from a 2026 study of agent-written pull requests. Agreement was measured with Cohen's kappa, which discounts matches that would happen by chance: 1 is perfect agreement and 0 is chance. The first version scored 0.29 against a pass mark of 0.6, because it marked descriptions as incomplete for leaving out details the annotators did not count. I changed how it counts omissions and tested the new version on 71 pull requests it had never seen. It passed at 0.69, and it still leans harsh.

With that judge, none of the 60 tool summaries misled; the 95% interval runs from 0 to 6%. One of the agent's 60 commit messages did, by describing a change the code does not make. The judge called 12 tool summaries and 18 commit messages incomplete. Two sentences leave things out, and the decision list under each summary is where those things appear.

### Who decided is the weak spot

Haiku called 158 of its 274 decisions the agent's own, while the reference labels call 50 of 149 the agent's. It also splits what the reference counts as one decision into several. The more serious error runs the other way: in 16 cases where the reference says the agent decided on its own, the tool said I had asked, which hides the decision behind my own words. The quote check can't catch this, because the quoted phrase really is in my request; it just doesn't support the decision.

The hold decision itself is stable. Run twice on 20 commits, the tool made the same hold-or-release call on 19, though the decision lists differed by about one item per commit.

## Where I would put the control

I would hold changes at the push. My agents commit straight to the main branch, so the push is the last moment the code exists only on my laptop. In a team that reviews pull requests, the pull request is the natural place.

What the hold stops should be what can't be undone: deleted or reshaped data, messages already sent to users, broken public links and money committed. The rest can wait for the feed.

Exact checks should run first. They cost nothing and explain themselves, and here they did about as well as the model at choosing what to hold. I would keep the model for writing the explanation.

Any decision the tool credits to my request deserves a second look, because that is the error that hides decisions. The feed shows the exact request text beside each one, and those are the lines I read first.

The reviewer needs measuring too. My history can't say whether the agent's unflagged calls were fine or unseen. A planted canary is the cheapest way I know to get that number.

## What this can't tell you

The evidence is one PM's 60 commits in two small projects over four active weeks. There are five cases of a change that mattered, so every catch rate here has a wide interval. The reference labels come from a model, and no person has checked them line by line yet. The judge was calibrated on descriptions written for engineers and then used on summaries written for a PM. In the demo project most pull requests link no issue, so the tool had no spec there and every decision counts as the agent's own call.

## Try it

signoff is free and open source. In Claude Code:

```
/plugin marketplace add samyakjain510/signoff
/plugin install signoff@signoff
```

The [demo](https://samyakjain510.github.io/signoff/demo/) shows the feed for 25 merged agent pull requests in Morphic, an open-source AI search app. The code, the measures written before any run, every result and the log of mistakes are in the [repository](https://github.com/samyakjain510/signoff).

## Sources

- Anthropic, [Claude Code auto mode: a safer way to skip permissions](https://www.anthropic.com/engineering/claude-code-auto-mode), 2026.
- Jingzhi Gong, Giovanni Pinna, Yixin Bian and Jie M. Zhang, [Analyzing Message-Code Inconsistency in AI Coding Agent-Authored Pull Requests](https://arxiv.org/abs/2601.04886), 2026. Labeled data at [github.com/gjz78910/PR-MCI](https://github.com/gjz78910/PR-MCI).
- Samyak Jain, How to keep "human in the loop" meaningful when people approve 93% of AI agent requests, 2026.
- Morphic, [github.com/miurla/morphic](https://github.com/miurla/morphic), Apache-2.0.
