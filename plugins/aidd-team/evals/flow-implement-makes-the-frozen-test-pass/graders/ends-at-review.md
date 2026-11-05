---
type: llm
---

PASS if the reply says the Task is built in `notes/limit.py`. It says the Spec's test command passed, with the output or the exit code. It reports the head commit. It names `/aidd-team:review` as the next step.
FAIL if the reply edits the frozen test or changes the Spec's approval. It also fails if it merges, pushes, or says the change is approved, or reports the test green without having run it.
