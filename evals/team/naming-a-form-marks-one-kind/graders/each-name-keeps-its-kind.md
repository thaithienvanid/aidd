---
type: llm
---

PASS if the reply does all of these:

- It changes the first name to a bare word, as the other statuses are written.
- It says why. A name with a dot reads as a field of an enrolment, or as an event, and never as a status.
- It changes the second name, and it says why. The record's dates end in `_on`, so a yes-or-no field that ends in `_on` reads as a date.
- It gives the second field a name that reads as a yes-or-no fact.
- It keeps the third name, because it is a date and ends as the record's other dates do.

FAIL if the reply keeps the first or the second name, or changes the third. It also fails if its only reason is letter case or style. A reason must say what kind of thing each name marks.
