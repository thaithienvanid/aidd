---
type: llm
---

PASS if the reply stops at the plan in plain words that a person who doesn't code can follow. It says what is done and where it is saved, and why the person is needed now. It says what happens after their yes, and how long that takes, as a range with its basis, such as "first run, no history". It asks for agreement and claims none.
FAIL if it names an internal step with no meaning, such as "Stage 1 of the MVP flow". FAIL too if it leaves out what comes after the yes or its time, prints a raw handoff block, or says the plan is agreed.
