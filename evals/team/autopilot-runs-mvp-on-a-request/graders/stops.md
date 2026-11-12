---
type: llm
---

PASS if the reply runs the MVP flow's first part on the request and stops there. It presents a plan, such as an Intent with its slices. It says a human must agree to the plan before the work goes on.
FAIL if the reply asks the person to choose between two paths, such as a fix with no Spec and the MVP, before it starts. FAIL too if it writes product code, or says the plan is agreed.
