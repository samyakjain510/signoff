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
| 2026-11-23 | Samyak asked Claude to finish the project end to end without waiting for him; his 10-label review stays optional | Samyak | |
| 2026-11-23 | Measures, thresholds and policies written down before any run (`docs/measures.md`) | Claude | |
| 2026-11-23 | Judge v1 calibrated on 72 PR-MCI PRs: failed (kappa 0.29). Judge v2 scored on 71 unseen PRs: passed (0.69 / 0.68) | Claude (script), PR-MCI annotators' labels | Claude read all 15 aligned-to-partial disagreements |
| 2026-11-23 | Tool built (feed, flags, policy, gate) and run with Haiku on all 60 commits | Claude | Claude read the outputs for 4 commits in full |
| 2026-11-23 | Correction finder (Sonnet) over 44 requests: 35 matches, 12 other corrections | Claude (script) | Claude read every match; rejected 1 (`corrections_review.json`) |
| 2026-11-23 | Judge v2 on 60 tool summaries and 60 commit messages | Claude (script) | Claude read the reasons for every misaligned and every partial tool summary |
| 2026-11-23 | Six policies replayed over the 60 commits (`results/own_repos.json`) | Claude (script) | Counts cross-checked against the per-commit lists |
| 2026-11-23 | Demo on 25 merged agent PRs in miurla/morphic; first set was wrong (review-bot badge read as author), rebuilt | Claude | Claude checked the page in a browser at desktop and phone width, light and dark |
| 2026-11-23 | Pre-push hold tested on a scratch copy of ktech: push held, agent approval refused, terminal approval recorded, push passed | Claude | Claude ran each step and read the output |
| 2026-11-23 | Stability: tool rerun on 20 commits; same hold decision on 19 | Claude (script) | |
| 2026-11-23 | Plugin loaded from disk in a headless Claude Code session; skill ran a dry run | Claude | |

