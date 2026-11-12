# What a review gives

Load this when you write what a review found, as the reviewer or the security engineer. It says what each finding shows and the order of the output, so a review cut off in transit still holds the verdict and every finding.

## Both questions

Answer both, and rank a `blocks` finding as you rank a `lets through` one. Honest work is work that should pass and now fails or slows: an unrelated change a new check refuses, a valid input it rejects, a step added for every user. For a new control, name the honest work it could block, and the test where that work still passes. With no such test, that is a `blocks` finding.

## The fields

<!-- aidd:gen roles:review-report -->
| Field | Value | It says |
| --- | --- | --- |
| `question` | `lets through` | what this lets through that it should stop |
| `question` | `blocks` | what honest work this now blocks or slows |
| `origin` | `regression` | behaves worse than base on the same input |
| `origin` | `new gap` | sits in code or a path this change adds |
| `origin` | `older gap` | behaves the same on base |
| `shown` | `ran` | you ran it, and give the command and its output |
| `shown` | `read` | you read it, and give the lines |
<!-- aidd:end -->

Tell a `regression` from an `older gap` by running old and new on one repository, with only the code changed: the same folder, base then head. Two folders can differ in more than the code. If you write no file, read the base with `git show <base>:<path>`, mark the finding `read`, and name the command that would compare them. A `read` finding is never Critical or High without `input:`, the input that would show it, and `test:`, the test that should catch it.

## The order

1. The harness and model you ran on. The security engineer adds one `Model:` line: who controls what input, and the boundary. Rank only what is inside it, and list the rest, one line each, after the findings.
2. `Verdict:` with the blocking count (Critical and High), then each origin and each question, each as a word and its count. A zero says you looked.
3. One line per finding: severity, question, origin, shown, `file:line`, and the finding with its evidence in a clause.
4. All of that in under 300 words. The detail follows, finding by finding, in your final message: you write no file.

| Before | After |
| --- | --- |
| Do not merge: this has serious problems. | `Verdict: blocking 1. regression 1, new gap 0, older gap 0; lets through 0, blocks 1.` |
| The new check may be too strict. | `1. High \| blocks \| regression \| ran \| src/parse.py:88 \| A waiting change now fails an unrelated one: the same command exits 0 on base and 2 on head.` |

## One rule before cases

Count the rounds of findings on one component from the last report you were given.

| Round | Say |
| --- | --- |
| First or second | One rule with its invariant, a sentence true of every input, then the cases it covers |
| Third or later | "Round N on this component": propose to shrink it, or to state its boundary once. Add no case. |

## A reader, a parser, or a decider

When the change alters code that reads input and answers allow or deny, a route, or a level, ask which test compares the new answer with the old one over a generated set of inputs. A test that holds only the new answer to itself cannot show a regression. With no such test, report it as a finding: `read`, ranked by what a wrong answer lets through or blocks.

## Worked examples

Use these when a finding feels vague, or its severity is hard to set. Each pair shows a weak finding, a strong one, and the line that tells them apart. The names in angle brackets stand for whatever your code holds; the examples teach the shape, never a domain.

### A finding someone can act on

- **Weak:** "`<handler>` may be vulnerable to injection."
- **Strong:** "Critical, confidence 8. `<file>:<line>` passes `<request field>` to `<query builder>` as raw text: `<the line>`. An anonymous caller sends `<payload>` and reads every row of `<table>`. Fix: bind it as a parameter. Test: the payload returns 400 and reads nothing."
- **The difference:** the strong one quotes the line, names who gets what, and gives the fix and the test that proves it.

### A severity the proof supports

- **Weak:** "High: `<operation>` has no rate limit."
- **Strong:** "Hardening note: `<operation>` has no rate limit. It needs a signed-in caller, and the gateway limits each caller already (`<config file>:<line>`), so no actor gains anything shown here."
- **The difference:** severity follows the impact the proof shows. A missing practice with no path to harm is a note, not a High.

### A test that would catch the regression

- **Weak:** "Tests pass, so Acceptance `<id>` holds."
- **Strong:** "High: no new-behavior command covers Acceptance `<id>`, so the red run on base has no result for it. Acceptance `<id>` has no test that fails without the change. Add one that `<calls the operation>` and asserts `<the observable result>`."
- **The difference:** a green run proves little until a test fails without the change. Read the red run on base, or the mutation run's surviving mutants.

### Scope, read from the Spec

- **Weak:** no comment on a renamed helper and a reformatted file the Spec never asked for.
- **Strong:** "Medium, non-blocking: `<file>` renames `<helper>` and reformats `<n>` lines. Nothing in Spec `<id>` asks for it, and it hides the real change. Move it to its own change."
- **The difference:** every changed line traces to the Spec. A line that traces to nothing is a finding, even when it is harmless.

### A question, not a guess

- **Weak:** "This is probably wrong: `<function>` should handle `<case>`."
- **Strong:** "Question, confidence 4: can `<input>` be `<case>` here? If it can, `<file>:<line>` returns `<wrong result>`. If it can't, a comment saying why would stop the next reader asking."
- **The difference:** when you can't show the failure, ask, and say what each answer would mean. Don't rank a guess as a defect.
