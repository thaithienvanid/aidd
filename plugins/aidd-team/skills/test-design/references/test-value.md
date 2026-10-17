# Test value and retirement cards

Load this when you add a test whose purpose is not plain from its name, or when a change deletes or weakens a passing test.

A test has a value and a cost. The value card says why the test exists. The retirement card says what evidence a person needs before a passing test goes. Write each card in the test's docstring or comment, or in the handoff note. Keep each one to a few lines.

## Test value card

| Field | What it says |
| --- | --- |
| Test | The test's name, as the runner reports it. |
| Protects | The failure it prevents: the Acceptance line, the bug, or the invariant. Name the user or caller who would see the failure. |
| Fails today when | How it fails today: the change to the code that turns it red. Show it once, by a revert, a mutant, or the red run on base. |
| Cost | Its run time, its flaky rate (`aidd metrics --flaky`), and how often it changed while the behavior did not. |

- A test with no failure it prevents is a candidate for retirement, not a safe test.
- A test that never failed is not a test without value. It can guard a path that nobody broke yet.
- Fix a flaky test, or quarantine it with an owner and a date. A retry that hides the flake is not a fix.

## Retirement card

Delete or weaken a passing test only with one of these evidence items in the change:

1. **The behavior is gone.** The same change deletes the code it tests, or an approved Spec removed the Acceptance line it proves.
2. **Another test covers it.** Name the other test. A mutation run or a revert shows that the other test fails on each mutant this test kills.
3. **The cost is over the value.** Its cost is measured: a run time, or a flaky rate over the limit after a fix was tried. A test at a lower level that proves the same failure replaces it in the same change.

"It is slow", "it never fails", and "it is in the way" are not evidence.

**Who decides.** A person decides, never an agent:

- A test that an approved Spec froze changes only through a new Spec approval.
- Any other passing test goes at Merge approval. The Approver reads the retirement card in the PR/MR.
- The tester or the developer writes the card. The reviewer checks the evidence and reports a deletion without a card as a finding.
