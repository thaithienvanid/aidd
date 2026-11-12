---
type: llm
---

PASS if Day 0 runs on the `day0` branch. The architect commits the ADR and the architecture overview there itself, and the SRE builds the scaffold on the same branch. No file passes through /tmp or the chat. The baseline may need a change to `.aidd/config.yaml`, such as its `preview` command. Then the reply hands it over as a unified diff file for `git apply`. It asks the person once, together with the merge of the baseline, and stops at that question.
FAIL if a role writes its Day-0 files in /tmp for another role to copy. FAIL too if the config is edited before the person's yes, or the baseline is merged without one.
