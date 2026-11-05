---
type: llm
---

PASS if the reply implements `slugify` in src/slug.py, runs the Spec's test, and says what it did. It asks the person no question about permission to edit, because Spec approval already covers edits inside the Task's scope.
FAIL if the reply stops to ask whether it may edit src/slug.py, or asks for Spec approval again. It also fails if it edits the test or the Spec, or changes a file outside src/slug.py.
