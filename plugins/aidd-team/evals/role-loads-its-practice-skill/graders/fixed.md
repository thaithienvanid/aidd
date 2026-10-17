---
type: llm
---

PASS if all of these hold:

- The work was delegated to the aidd-team:developer agent.
- A test that calls the real `nights_label` with a two-night stay and expects "2 nights" was shown or stated to fail on the unchanged code, before the fix.
- The fix makes every count other than one plural (the comparison becomes `n != 1`), and the test then passes.
- The reply names the cause in one sentence, and ends with the four-line handoff note (Done, Next, Needs, Stopped at).

FAIL if any of these hold:

- `stays.py` was changed before a test reproduced the symptom.
- The fix only moves the threshold (for example `n > 1` without a case for zero, or `n >= 2`) without saying why zero is plural.
- The test would also pass on the unchanged code.
- The reply says the change is approved or merged.
