---
description: A finished shipment gains no status, flag, or code that means work is owed. The signature is a stored fact, and each chase has its owner and outcome, as a new item or on a shipment that stays open until it is signed.
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
max_turns: 25
timeout_seconds: 900
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - practice
  - claim:duty:architect.keeps-a-finished-object-finished
  - tier:full
  - shape:api-service/brownfield/team/unregulated
  - world:go-logistics
  - grading:judge-needed
---

This repository uses aidd. `shipment/shipment.go` holds a shipment and its four statuses. Ten days after a delivery, the depot's claims clerk must chase each customer who has not signed the delivery note. The clerk notes how each chase ended. My plan is to add a fifth status, `pod_check_due`, that a delivered shipment moves to after ten days, so it comes back onto the depot's list. Design the change to the model before I build it. Change no file.

End your reply with these two lines, filled in:

```text
Status values after the change: <every status a shipment can have>
New object or field: <its name, or none>
```
