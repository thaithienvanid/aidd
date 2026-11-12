---
type: llm
---

PASS if the review does all of these:

- It sorts its points into Keep, Fix, and Quick win.
- The missing focus ring, the raw color, and the unnamed button are Fix points.
- The steady loading state is a Keep, and the bare empty state is a Quick win or a Fix with a reason.
- Every point carries proof a reader can open or rerun. That is a screenshot path, the token, the file and line, or the axe rule. It may also be a WCAG 2.2 success criterion such as 2.4.7 or 4.1.2, or a named Nielsen heuristic.
- It declines the score out of 10, saying the list of Fix points is the verdict.

FAIL if the review gives a numeric score, grade, or percentage, or leaves a point without proof. It also fails if it mixes the kinds into one undifferentiated list, or says the change is approved.
