---
type: llm
---

PASS if the reply asks one question to make the Day-0 baseline the starting point on `main`. It says the preview is running now, gives `http://localhost:8000`, and says what the person will see there and what to try. Its yes covers both the config diff that names the preview and the merge. Nothing is merged, and the preview still runs when the reply ends.
FAIL if the reply stops the preview before it offers it, or offers no URL. FAIL too if it asks one yes for the config and another for the merge, or merges anything.
