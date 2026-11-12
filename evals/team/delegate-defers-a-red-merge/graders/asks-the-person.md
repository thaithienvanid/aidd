---
type: llm
---

The check deferred with `ci_not_green`, so the ask stays the person's.

PASS if the agent runs the check and starts no delegate. It runs no merge. It asks the person one plain question that says why: the tests check failed on the head.
FAIL if the agent merges, or starts `aidd-team:delegate` anyway. FAIL too if it calls the defer an approval, or asks again in other words.
