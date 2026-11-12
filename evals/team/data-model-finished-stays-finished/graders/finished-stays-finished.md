---
type: llm
---

PASS if the reply meets both halves of the request, and leaves nothing on a finished shipment that means work is owed.

- It stores the signature as a fact of its own on the shipment, with its instant. A signed parcel then drops off the clerk's list.
- It records each chase with its owner and how it ended, in one of two sound shapes.
- The first shape is a new item for the chase. It holds a link to its shipment, the day it starts, its own state, and how the chase ended. `delivered` stays a final status.
- The second shape keeps the shipment open after `delivered`. The shipment ends in a final status of its own, such as `signed`, and while it is open it holds the chase's owner and outcome.
- In both shapes, "due" is computed. It is never stored on the shipment.

FAIL if the reply adds `pod_check_due` to the shipment, or another status that means the check is owed. It also fails if it marks a finished shipment with a flag or a date that means the check is owed. It fails if its only design is a job that changes the delivered shipment after ten days. It fails too if it meets only one half: a list read as a view with no record of each chase, or a chase written for every delivery with no stored signature.
