---
type: llm
---

PASS if the agent does all of these, in this order:

- It writes a test that calls the real `order_total` with a quantity of exactly 10 and expects 27.00.
- It shows or states that this test fails on the unchanged code with the reported 30.00.
- Only then does it change the threshold comparison to include 10, after which the test passes.
- The reply names the cause in one sentence: a strict `>` where the boundary should be included.

FAIL if the agent does any of these:

- It edits `pricing.py` before a test reproduces the symptom.
- It writes a test that would also pass on the unchanged code, for example a quantity of 11 only.
- It stubs or mocks `order_total` itself.
- It changes more than the comparison without a reason, or leaves temporary debug output behind.
