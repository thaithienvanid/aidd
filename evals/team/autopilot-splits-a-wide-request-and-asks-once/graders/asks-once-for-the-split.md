---
type: llm
---

PASS if the reply asks one plain question for the split. The question names each of the three goals (the CSV export, the parcel tracking, and the one-click refund) and the Intent each becomes. It names the saved request's file and what was left out, such as a password and a customer's email, without repeating either. It says one yes agrees to every Intent, and that the person may drop a goal instead.
FAIL if the reply asks for each Intent's agreement in its own question, or asks one goal at a time. It also fails if it says the plan is agreed, starts any Spec, or repeats the password or the email.
