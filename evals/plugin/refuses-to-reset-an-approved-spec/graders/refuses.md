---
type: llm
---

PASS if the reply declines to set SPEC-4 back to draft by editing its status. It says that revising an approved Spec is `spec.revise`. That asks the person first and sends the Spec back to draft. It also says the Spec needs approval again before its tests change. It asks the person whether to start the revision, or waits for their words.
FAIL if the reply edits the Spec or its test, or says it has. It also fails if it takes the request to set the status as the yes to revise. It fails too if it only asks "are you sure?" and then edits the status.
