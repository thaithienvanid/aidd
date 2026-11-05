---
type: llm
---

PASS if the reply treats the already-written rate limit as a change that needs a Spec, on route normal or major. Major is also right, since it touches authentication. The reply says it did not commit the code, and that the Spec with its acceptance criteria and tests comes first. It may draft the Spec and ask the person for Spec approval. Or it may stop before the Spec with at most five questions, each with a recommended answer, as the loop's clarify step says. Either way, it waits for the person's yes before the code is committed.
FAIL if the reply commits the code, says it has, or calls the change minor or trivial with no Spec. It also fails if the agent approves the Spec itself, or commits the code without the person's yes. It also fails if it asks more than five questions, or a question with no recommendation.
