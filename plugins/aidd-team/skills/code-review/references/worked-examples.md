# Worked examples: review findings

Load this when a finding feels vague, or its severity is hard to set. Each pair shows a weak finding, a strong one, and the line that tells them apart. The names in angle brackets stand for whatever your code holds; the examples teach the shape, never a domain.

## A finding someone can act on

- **Weak:** "`<handler>` may be vulnerable to injection."
- **Strong:** "Critical, confidence 8. `<file>:<line>` passes `<request field>` to `<query builder>` as raw text: `<the line>`. An anonymous caller sends `<payload>` and reads every row of `<table>`. Fix: bind it as a parameter. Test: the payload returns 400 and reads nothing."
- **The difference:** the strong one quotes the line, names who gets what, and gives the fix and the test that proves it.

## A severity the proof supports

- **Weak:** "High: `<operation>` has no rate limit."
- **Strong:** "Hardening note: `<operation>` has no rate limit. It needs a signed-in caller, and the gateway limits each caller already (`<config file>:<line>`), so no actor gains anything shown here."
- **The difference:** severity follows the impact the proof shows. A missing practice with no path to harm is a note, not a High.

## A test that would catch the regression

- **Weak:** "Tests pass, so Acceptance `<id>` holds."
- **Strong:** "High: reverting `<file>:<line>` keeps every test green. Acceptance `<id>` has no test that fails without the change. Add one that `<calls the operation>` and asserts `<the observable result>`."
- **The difference:** a green run proves little until a test would fail without the change. Revert the change, or run the mutation command, and see.

## Scope, read from the Spec

- **Weak:** no comment on a renamed helper and a reformatted file the Spec never asked for.
- **Strong:** "Medium, non-blocking: `<file>` renames `<helper>` and reformats `<n>` lines. Nothing in Spec `<id>` asks for it, and it hides the real change. Move it to its own change."
- **The difference:** every changed line traces to the Spec. A line that traces to nothing is a finding, even when it is harmless.

## A question, not a guess

- **Weak:** "This is probably wrong: `<function>` should handle `<case>`."
- **Strong:** "Question, confidence 4: can `<input>` be `<case>` here? If it can, `<file>:<line>` returns `<wrong result>`. If it can't, a comment saying why would stop the next reader asking."
- **The difference:** when you can't show the failure, ask, and say what each answer would mean. Don't rank a guess as a defect.
