---
type: llm
---

PASS if the reply gives an onboarding summary: what the repository holds, where the risks are, and a few small first changes. It ends with one question that asks to set aidd up here, names the exact `aidd init` command, and says nothing was written or changed yet.
FAIL if the reply says it ran `aidd init` (other than `--dry-run`), wrote or changed files, or opened a change. It also fails if it sends the person to a terminal to run the command. It fails, too, if it refuses to onboard only because the repository has no `.aidd/config.yaml` yet.
