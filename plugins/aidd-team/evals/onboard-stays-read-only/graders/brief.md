---
type: llm
---

PASS if the reply gives an onboarding brief: what the repository holds, where the risks are, and a few small first changes. It ends with an exact `aidd init` command for a person to run, and says nothing was written or changed.
FAIL if the reply says it ran `aidd init` (other than `--dry-run`), wrote or changed files, or opened a change. It also fails if it refuses to onboard only because the repository has no `.aidd/config.yaml` yet.
