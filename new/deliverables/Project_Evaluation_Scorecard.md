# Project evaluation scorecard

This measures end-to-end evidence and submission readiness. It is separate from C3 file quality and optional C7 provider price comparisons. Unknown measures are never treated as zero or as passing.

| Measure | Formula | Current result | Decision use |
| --- | --- | ---: | --- |
| Target plan evidence maturity | Confirmed target PPO plan-file edges ÷ confirmed + provisional target PPO edges | 6.64% (30/452) | Prioritize plan review; not a network accuracy estimate |
| File attribution | Selected target files known PPO-only ÷ selected target files | 0% (0/1) | Blocks PPO-specific rate claim for shared files |
| Candidate address reach | Unique C4 NPIs with physical candidate ÷ unique C4 NPIs | 96.13% | Shows matching reach, not verification |
| Fully verified provider link | Unique C4 NPIs with corroborated site, direct TIN/site proof, and exact PPO/site proof ÷ unique C4 NPIs | 0.0% | Core C5 outcome |
| Verified rate yield | C6 verified PPO-specific rows ÷ C4 selected rate contexts | 0.0% | Final rate-file evidence gate; zero while attribution is unresolved |
| Rate sample correctness | Sampled exported rows matching source rate and selection decision ÷ sampled exported rows | Unknown | Requires a recorded source-row audit or answer key |
| Clean rerun | Successful fresh-environment runs ÷ attempted fresh-environment runs | Unknown | Requires a recorded clean run with input hashes |

**Release gate:** publish a populated PPO rate file only when a PPO-only rate attribution is documented, its NPI/TIN/site links are verified, sampled rows reconcile to the source, and the README rerun succeeds. The current release gate is **not met**.

The C3 score is reported separately: 83.33/100, grade B, REVIEW_REQUIRED. It grades the published file's fitness for direct-dollar benchmarking, not the completed project.
