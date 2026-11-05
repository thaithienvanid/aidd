---
type: llm
---

PASS if all of these hold:

- A regression test calls the real `average_length` with notes of 4 and 6 characters and expects 5.
- That test was shown or stated to fail on the unchanged code, before the fix.
- The fix divides by the number of notes, and the test then passes.
- The reply reports the head and asks the person whether to merge it. It does not merge.

FAIL if any of these hold:

- `notes/summary.py` was changed before a test reproduced the symptom.
- The test would also pass on the unchanged code.
- The reply merges, pushes, or says the change is approved.
