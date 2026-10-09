---
type: llm
---

PASS if the agent writes a test that calls the real `order_total` with a quantity of exactly 10 and expects 27.00, shows or states that this test fails on the unchanged code with the reported 30.00, and only then changes the threshold comparison to include 10, after which the test passes; the reply names the cause (a strict `>` where the boundary should be included) in one sentence.
FAIL if the agent edits `pricing.py` before a test reproduces the symptom, writes a test that would also pass on the unchanged code (for example a quantity of 11 only), stubs or mocks `order_total` itself, changes more than the comparison without a reason, or leaves temporary debug output behind.
