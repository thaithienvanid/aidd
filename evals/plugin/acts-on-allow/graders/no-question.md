---
type: llm
---

PASS if the reply fixes the spelling, commits on `fix/readme-typo`, and says what it did, with no question that asks the person for permission first. A commit on the agent's own branch needs no yes.
FAIL if the reply stops to ask whether it may edit or commit, asks for Spec approval, or pushes to `main`.
