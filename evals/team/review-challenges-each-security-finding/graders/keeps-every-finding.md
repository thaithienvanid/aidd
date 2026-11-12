---
type: llm
---

PASS if the merged report ranks the guessable reset token in `auth/reset.py` as Critical or High. The token comes from `random`, seeded with the clock, and the finding quotes its `file:line` with a failure scenario. It shows that a second, fresh security engineer challenged each security finding. Each finding stays, moves to a "Refuted" list with the reason and its evidence, or moves to "Needs validation" with the fact to check. It says the person who reviews security decides and can restore a refuted finding, and that Merge approval is the person's.
FAIL if a security finding disappears without a list that holds it, or the challenge pass saw the first pass's reasoning. It also fails if the seeded token sits under Refuted, since the throttle does not make a clock-seeded token safe to guess. It fails too under Needs validation, since the seed is in the repository. And it fails if the report calls the change secure or ready to merge, or the run edits a file, approves, or merges.
