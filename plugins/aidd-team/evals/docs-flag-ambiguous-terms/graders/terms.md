---
type: llm
---

PASS if the rewrite says Spec approval instead of "signs off on the Spec" and "the design gate" (the design files are approved as part of Spec approval, by a person); says a person gives the Merge approval rather than the reviewer approving; calls the PR a PR/MR or keeps it unchanged with a note; says evidence is what the test runner recorded on the head commit, not the CI logs; says a person agrees to the plan rather than approves it; and lists each replaced term with the preferred one.
FAIL if the rewrite keeps "sign off" or "gate" for a person's decision, lets the reviewer approve the change, still calls the CI logs the evidence, or changes the terms silently without saying what it changed.
