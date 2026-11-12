---
name: maintainable-code
description: "Practice skill: keep code readable as it grows. Use in an aidd repository when a Task grows a function, file, module, or package, writes a comment or docstring, or a diff's shape is reviewed."
metadata:
  checked: "2026-10-22"
---

# Maintainable code

**Use it when** a Task adds code, grows a function or file past a screen, adds a module or package, or writes a comment or a docstring. The reviewer uses it to judge a diff's shape.

**Do not use when** the change is a one-line fix in code that already reads well. Never reshape code the Task does not touch: a refactor is its own change.

## Standards

<!-- aidd:gen practice:maintainable-code -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Comments explain why some code exists, not what it does | — | 2026-10-19 | <https://google.github.io/eng-practices/review/reviewer/looking-for.html> |
| Refactoring: Extract Function, Split Phase, Move Function, and Inline Function, each a small behavior-preserving step | 2nd edition, 2018 | 2026-10-19 | <https://refactoring.com/catalog/> |
| Deep modules: a small interface over much behavior; a shallow pass-through layer adds complexity | 2nd edition, July 2021 | 2026-10-20 | <https://web.stanford.edu/~ouster/cgi-bin/aposd.php> |
| The linter's complexity rules set the numbers: ruff C901 (McCabe), ESLint complexity | — | 2026-10-19 | <https://eslint.org/docs/latest/rules/complexity> |
| A ratchet on an old pattern: a recorded count that may fall and never rise | — | 2026-11-12 | <https://eslint.org/blog/2025/04/introducing-bulk-suppressions/> |
<!-- aidd:end -->

## Implement

Before you write a helper, search for one: the module's door, the shared kernel, the owning module, and the library choices ([references/reuse.md](references/reuse.md)).

Before you use an API new to the repository, read its version from the lockfile. Check that version's official documentation, because a model can invent an API or recall one from another version. Name the page on the handoff note.

Keep a list of constants, cases, or options in one order, grouped by kind. Add an item where that order places it, never at the end by habit. When the order is behavior, such as the first match winning, say so in a comment beside it.

### When to split

Split for the reader, never for a count. The signals:

1. **Two reasons to change.** A function, file, or module that changes for two unrelated reasons is two things. Name each part; if an honest name needs "and", split it (`aidd-team:naming`).
2. **One screen.** A reader holds about one screen at a time. A function past it, or a file whose parts a reader must scroll between to follow one idea, splits along the idea (Extract Function, Split Phase).
3. **Deep, not shallow.** Prefer a module with a small interface over much behavior. A split that adds an interface which hides nothing, or a pass-through layer, makes the code harder to read: undo it (Inline Function).
4. **Its own owner.** A part with its own data, team, or release becomes its own module, behind its public interface (`aidd-team:modular-monolith`). A package splits only with an owner and a reason in an ADR.

The counter-rules:

- **Rule of three.** Two copies may stay. On the third, extract what they share, named for what it is.
- **Return early** on a failed check, so the main path is not nested.
- **Never split to please a metric** or a test. A split for a test's sake moves the seam to the wrong place: test through the public interface.
- **A split is a refactor.** It is its own change, of type `refactor`, with the tests green before and after, never folded into a feature.

The numbers belong to the linter, never the agent's taste: the ecosystem's own complexity and size rules (ruff `C901` and the `PLR09` rules, ESLint `complexity`, golangci `gocyclo` and `funlen`), at the values the project set. A rule the project turns off stays off.

### Old patterns you leave

An old pattern is a way the project no longer wants, such as a deprecated call, a hand-made copy of a shared helper, or a suppressed lint rule. Retiring it across the code is a change of its own. A Task that meets it outside its scope leaves it and reports it.

1. **Report it.** Write one line in the handoff note's `done`: `debt: <what, where>`. Give the number of sites and the search that finds them in the `what`.
2. **Hold it with a ratchet** when the pattern has many sites and the project wants it gone: a count for one pattern that may fall and never rise ([references/ratchet.md](references/ratchet.md)). It is a change of its own, of type `chore`, unless the Task is the migration itself.
3. **Keep it in view.** The retrospective's upkeep mode (`/aidd-team:retro upkeep`) lists each `debt:` line, and a person decides whether it becomes a Spec labeled `debt`. How a ratchet reaches the improvement log is in the reference.

### Comments and docstrings

A comment costs a reader time on every read, so each one must pay for it.

1. **Say why, or what the code cannot.** A decision and its reason, a trap, a link to the rule or the incident. Never what the next line already says.
2. **A docstring for each public name**, one line when one line will do: what it is, what it returns, what it raises or refuses. A private helper with an honest name needs none.
3. **A changed line's comment changes with it.** Read every comment beside a line you change. Update it, or delete it when it no longer holds. A stale comment is a bug.
4. **Never** commented-out code, a comment that restates the name, or a "TODO" with no owner or link. Never history either: who or what made the change, the date a number changed, "raised from", "before the … change", or "temporary until". The same goes for a ticket, task, or plan id that its readers cannot open or that stands in place of the reason (rule 7). It holds in a docstring, a test name, and a message too. Say what holds and why, for a reader who never saw the change. Version control keeps the history ([references/history.md](references/history.md)).
5. **Match the file.** Follow the density and the style of the code around it. A new file follows its package.
6. **Name it instead.** A constant whose value carries a rule, such as a limit or a timeout, gets a name, not a comment.
7. **An id points; it never explains.** A ticket, work item, or review id goes in the branch, the commit, and the PR/MR, where the platform links it. In code, cite only an id the code's readers can open, such as an ADR, a Spec in the repository, or an issue in the team's tracker, and state the reason in words beside it. An id they can't open, such as a personal backlog's, or a dated note of who decided, tells a later reader nothing. Check it with one lint rule or test that searches the comments, docstrings, test names, and messages for the project's ticket and task ids. An id in a test's own data, such as a fixture about ids, is not this.

## Review

- Checks: each new function and file against When to split, and no third copy of the same code.
- Smells: a pass-through layer, a helper named for its caller, a docstring that restates its code, and a break of any comment rule above. Each is a finding (Low), or Medium when it misleads.
- A raised baseline of a ratchet, or a new use of a pattern a ratchet holds, is a finding (Medium) unless a person's recorded decision covers it.
- A diff whose comments and docstrings grow faster than its code is a finding, unless the Spec asks for documentation.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Complexity check | no changed function is past the project's complexity and size limits | the project's linter on the changed files, with its own config and thresholds, such as `ruff check`, `eslint`, or `golangci-lint run --new-from-rev <base>` |
| Ratchet check | each held pattern's count is at or below its baseline, and a lower count lowers the baseline | the pattern's search over its stated paths, compared with the baseline file. Run it on a copy where a file that holds the pattern moves: it passes |
| History check | no comment, docstring, test name, or message holds a ticket, task, or plan id its readers cannot open, or one that stands in place of the reason | a lint rule or a short test that searches them for the project's own id prefixes, as [references/history.md](references/history.md) says |

## Stop if

- The split would change behavior, or the Task's scope does not hold the files it moves: hand it off as a `refactor` change.
- A comment would record a decision only a person can make: write it in the Spec or an ADR, and link it.

## Hand off

- Done: the code as split, and the comments that changed. Next role: the reviewer. Needs: none, or a person's call on a split that crosses an owner's module. Stopped at: none, or the stop rule's code.
