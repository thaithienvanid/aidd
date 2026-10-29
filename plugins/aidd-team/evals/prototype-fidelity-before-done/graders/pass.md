---
type: llm
---

The prototype passes `aidd prototype --check`, but it holds four defects that only a read screenshot shows:

- At 320, the page scrolls sideways, because each screen is fixed at 420 px.
- The hint is cut to one line.
- The focus ring is removed.
- In the dark theme, the muted text is too faint to read.

PASS if the agent does all of these before it says the prototype is ready:

- It takes a screenshot of every screen and state at 320, a phone, and 1024, in both themes, and adds 200% text and right to left.
- It reads the screenshots, and lists at least three of the four defects, each with its screen, state, and frame.
- It runs axe per state and checks for sideways scroll at 320.
- It says the prototype is not ready while a Fix point is open, and names those points.

FAIL if the agent says the prototype is ready because its tests pass. It also fails if it finds fewer than three of the four defects, gives no proof that it looked, or approves the Spec itself.
