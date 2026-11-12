---
type: llm
---

The page holds five defects that a look at the screen finds:

- At 320, the page scrolls sideways, because the toolbar is fixed at 640 px.
- The icon button has no name.
- The focus ring is removed.
- The "Size" label is too faint to read.
- The Checks badge sits off its label's baseline.

PASS if the agent does all of these:

- It reviews the changed screen even though there is no Spec. The nine sizes becoming one list is a change to a component's look and states, so the designer's pass applies, sized to that change.
- It takes the screen as a person sees it first, then each changed control's states in both themes, a 320 width, and 200% text, and reads each screenshot. A full matrix of every state at three widths is more than the change needs, and it does not fail.
- It finds at least three of the five defects.
- It runs axe, or says how to, and checks for sideways scroll.
- It reports Keep, Fix, and Quick win points, each with its proof: a screenshot path, a rule, or a file and line.
- It gives no numeric score and approves nothing.

FAIL if the agent declines because there is no Spec, or reviews the code alone without looking at the screen. It also fails if it finds fewer than three defects, or gives an opinion without proof, a numeric score, or an approval.
