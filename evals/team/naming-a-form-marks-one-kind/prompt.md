---
description: Of three proposed names, the two that borrow another kind's form are changed (a status written like a path, and a yes-or-no field that ends like the dates), and the one that fits its family is kept.
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
  - claim:duty:architect.keeps-one-form-for-each-kind-of-name
  - tier:full
  - shape:library/brownfield/team/unregulated
  - world:ruby-education
---

This repository uses aidd. `lib/enrolment.rb` holds a student's enrolment on a course. I want to add three names to it:

1. a third status, written `enrolment.completed`, for a student who finished the course;
2. `reminders_on`, which is true when the student wants email reminders for this course;
3. `completed_on`, the day the student finished.

Review the three names before I add them. Change no file.

End your reply with three lines, one for each name, in this form:

```text
1: keep or change, then the name to use
2: keep or change, then the name to use
3: keep or change, then the name to use
```
