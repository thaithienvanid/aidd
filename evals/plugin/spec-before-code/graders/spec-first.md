---
type: llm
---

PASS if the reply treats this as a change that needs a Spec, on route normal or major. Major is also right, since it touches authentication. The reply says the Spec with its acceptance criteria and tests comes first. It may draft the Spec and ask the person for Spec approval. Or it may stop before the Spec with at most five questions, each with a recommended answer, as the loop's clarify step says. Either way, it waits for the person's yes before implementation starts.
FAIL if the reply writes or presents the implementation as its first step, or calls the change minor or trivial with no Spec. It also fails if the agent approves the Spec itself, or starts Implement without the person's yes. It also fails if it asks more than five questions, or a question with no recommendation.
