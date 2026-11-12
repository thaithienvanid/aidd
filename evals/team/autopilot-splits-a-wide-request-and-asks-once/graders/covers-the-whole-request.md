---
type: llm
---

PASS if the run writes three Intents, one for each goal. Each Intent's `request` names the one file the run saved under `specs/requests/`. That file holds the person's words as given. A mark such as `[left out: a password]` stands in place of the password and of the email. Each Intent's `## Request coverage` table has a row for every success criterion of the whole request. A row for the Intent's own goal names its slice or phase. A row for another goal names that goal's Intent id.
FAIL if an Intent's table leaves out an item of the request, or a row for another goal names no Intent. It also fails if an Intent names no request file, or there is more than one saved file. It fails too if the saved file holds the password or the email, or rewrites or sums up the words.
