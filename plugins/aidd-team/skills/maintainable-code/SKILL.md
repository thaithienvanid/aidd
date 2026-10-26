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
<!-- aidd:end -->

## Implement

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

### Comments and docstrings

A comment costs a reader time on every read, so each one must pay for it.

1. **Say why, or what the code cannot.** A decision and its reason, a trap, a link to the rule or the incident. Never what the next line already says.
2. **A docstring for each public name**, one line when one line will do: what it is, what it returns, what it raises or refuses. A private helper with an honest name needs none.
3. **A changed line's comment changes with it.** Read every comment beside a line you change. Update it, or delete it when it no longer holds. A stale comment is a bug.
4. **Never** commented-out code, a change log in a comment, a comment that restates the name, or a "TODO" with no owner or link. Git keeps the history.
5. **Match the file.** Follow the density and the style of the code around it. A new file follows its package.
6. **Name it instead.** A constant whose value carries a rule, such as a limit or a timeout, gets a name, not a comment.

## Review

- Checks: each new function and file reads on one screen, or splits along an idea; each split has one reason to change and a deep interface; no third copy of the same code.
- Smells: a pass-through layer, a helper named for its caller, and commented-out code. So is a comment that says what the next line says, a docstring longer than its code, or a stale comment beside a changed line. Each is a finding (Low), or Medium when it misleads.
- A diff whose comments and docstrings grow faster than its code is a finding, unless the Spec asks for documentation.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| Complexity check | no changed function is past the project's complexity and size limits | the project's linter on the changed files, with its own config and thresholds, such as `ruff check`, `eslint`, or `golangci-lint run --new-from-rev <base>` |

## Stop if

- The split would change behavior, or the Task's scope does not hold the files it moves: hand it off as a `refactor` change.
- A comment would record a decision only a person can make: write it in the Spec or an ADR, and link it.

## Hand off

- Done: the code as split, and the comments that changed. Next: the reviewer. Needs: none, or a person's call on a split that crosses an owner's module. Stopped at: none, or the stop rule that fired.
