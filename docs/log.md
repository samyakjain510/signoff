# Signoff build log

What was done, by whom (Claude or Samyak), and what was checked by hand.

| Date | Step | Done by | Checked by hand |
|---|---|---|---|
| 2026-11-22 | Research on existing tools and oversight studies; plan approved | Claude | Samyak approved plan |
| 2026-11-22 | Commit records for portfolio (30) and ktech-interviews (30), from fresh GitHub clones | Claude (script) | Claude spot-checked counts against GitHub |
| 2026-11-22 | Linked commits to the session messages that produced them (59/60) | Claude (script) | Claude read 3 links by hand; all correct |
| 2026-11-22 | Exact code checks; first version too noisy (187 portfolio findings), tightened to 28 | Claude | Claude inspected trigger text for every check type |
| 2026-11-22 | AIDev sample: 360 merged agent PRs with linked issues, 60 per agent, seed 7 | Claude (script) | Not yet |
| 2026-11-22 | PR-MCI human labels downloaded (600 validation PRs, 432 with failure types) | Researchers (Gong et al.) | Their two annotators, kappa 0.892 |
| 2026-11-22 | Reference labels for 60 commits drafted by Claude Sonnet via `claude -p` | Claude | Script checked every evidence quote exists in the diff; Samyak to review a sample of 10 |
| 2026-11-23 | Found and fixed two gaps in request linking (Claude's compaction summaries counted as the user; mid-task messages missed); 21 commits relabeled | Claude | Claude traced one wrong label (Internships split) back to the missed mid-task message by reading the transcript |

