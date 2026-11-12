---
type: llm
---

PASS if the agent writes deterministic checks as Spec test commands, each with a name and a command vector (not one shell string). One command may cover several rules, such as `aidd prototype --check` on the file. Together they catch all of these in the screen shown:

- the raw colors `#1a1a1a` and `rgb(200, 30, 30)` outside the tokens block. For example, a grep over `prototype.html` with the `<style id="tokens">` block removed first, or stylelint `color-no-hex` and `function-disallowed-list` over the file's other styles.
- the hotlinked font and image
- the placeholder text (lorem ipsum, "Your Name", the TODO)
- the emoji used as an icon
- the clickable `div` with no accessible name and no keyboard access, checked with axe-core (such as `button-name`) and a keyboard walk or `eslint-plugin-jsx-a11y`

It points to `aidd-team:accessible-ui` for the fuller accessibility practice. It says the script the commands run belongs in `tests.files`, so Spec approval freezes it.
FAIL if any of the five kinds of violation would pass the checks, or a check depends on a model's judgment or the network rather than a deterministic command. It also fails if a check would also flag the generated `<style id="tokens">` block, or the agent fixes the prototype instead of writing the tests.
