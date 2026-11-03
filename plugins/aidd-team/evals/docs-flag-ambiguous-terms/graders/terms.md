---
type: llm
---

PASS if the rewrite does all of these:

- It says Spec approval instead of "signs off on the Spec" and "the design gate". The design files are approved as part of Spec approval, by a person.
- It says a person gives the Merge approval, rather than the reviewer approving.
- It calls the PR a PR/MR, or keeps it unchanged with a note.
- It says evidence is what the test runner recorded on the head commit, not the CI logs.
- It says a person agrees to the plan, rather than approves it.
- It lists each replaced term with the preferred one.

FAIL if the rewrite keeps "sign off" or "gate" for a person's decision, or lets the reviewer approve the change. It also fails if it still calls the CI logs the evidence, or changes the terms silently without saying what it changed.
