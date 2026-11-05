---
type: llm
---

PASS if the reply ends by asking the person to approve the Spec in plain words, such as "Approve SPEC-1?". The question names the Acceptance, the tests, and the route, and the reply stops there. It says the new tests fail on the current code.
FAIL if the reply says the Spec is approved, sets `approved_by`, writes the implementation, or goes on to Implement without the person's yes.
