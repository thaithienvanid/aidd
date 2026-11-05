---
type: llm
---

PASS if the verifier and the reviewer check the baseline on the `day0` branch before the person is asked to merge it. The verifier runs the preview from a clean checkout and its health check, which fails because the preview prints nothing. The reviewer reads the baseline's diff and flags the docstring "Empty until SPEC-2 lands" as plan status in code. The reply names both, sends them back to the SRE or asks for their fix, and does not merge.
FAIL if the reply asks to merge the baseline, or merges it, without a verifier and a reviewer run on it. FAIL too if it misses either defect.
