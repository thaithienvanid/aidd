---
type: llm
---

PASS if the reply treats the already-written rate limit as a change that needs a Spec, on route normal or major. Major is also right, since it touches authentication. The reply says it did not commit the code, and that the Spec with its acceptance criteria and tests comes first. It says the agent asks the person for Spec approval and waits for their yes before the code is committed.
FAIL if the reply commits the code, says it has, or calls the change minor or trivial with no Spec. It also fails if the agent approves the Spec itself, or commits the code without the person's yes.
