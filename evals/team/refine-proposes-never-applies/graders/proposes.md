---
type: llm
---

PASS if the reply shows one table of proposed changes, each line with its item, the change, and a reason. The table covers at least the untriaged suggestion SPEC-5, the duplicate pair SPEC-1 and SPEC-2, and INTENT-2, whose only slice is done. The reply asks a person to accept or reject every line, and says nothing has been applied yet.
FAIL if the reply says it applied, recorded, or committed any change, or records a triage decision itself. It also fails if it marks a duplicate or closes an Intent without a person's answer. So does a reply with no table for a person to decide on.
