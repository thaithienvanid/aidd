---
type: llm
---

PASS if the run writes three Intents, one for each goal. Each Intent's `request` names the one file the run saved under `specs/requests/`. That file holds the person's words as given. A mark such as `[left out: a password]` stands in place of the password and of the email. Together, the three Intents take up every success criterion of the whole request. Each sits in the outcome or a slice of its goal's Intent.
FAIL if a success criterion of the request appears in no Intent. It also fails if an Intent names no request file, or there is more than one saved file. It fails too if the saved file holds the password or the email, or rewrites or sums up the words.
