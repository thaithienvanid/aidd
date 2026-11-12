---
name: cli-design
description: "Practice skill: design a command-line interface. Use in an aidd repository when a Task adds or changes a command, flag, CLI prompt, help text, exit code, JSON output, or terminal color."
metadata:
  checked: "2026-11-10"
---

# CLI design

**Use it when** a Task adds or changes what a person or a script sees of a command-line tool. That is a command, flag, prompt, help text, error message, exit code, machine output, color, or a setting the command reads. Load it in Specify too: scripts depend on all of it, so it freezes at Spec approval.

**Do not use when** the change is internal and no command's input, output, or exit code changes. A config file's keys and a schema's fields are `aidd-team:data-model-design`.

## Standards

<!-- aidd:gen practice:cli-design -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| Command Line Interface Guidelines | — | 2026-11-10 | <https://clig.dev/> |
| POSIX.1-2024 Utility Conventions | POSIX.1-2024 (IEEE Std 1003.1-2024) | 2026-11-10 | <https://pubs.opengroup.org/onlinepubs/9799919799/basedefs/V1_chap12.html> |
| GNU Coding Standards: command-line interfaces | — | 2026-11-10 | <https://www.gnu.org/prep/standards/html_node/Command_002dLine-Interfaces.html> |
| NO_COLOR: disabling ANSI color output by default | — | 2026-11-10 | <https://no-color.org/> |
| XDG Base Directory Specification | 0.8 | 2026-11-10 | <https://specifications.freedesktop.org/basedir-spec/latest/> |
<!-- aidd:end -->

## Specify

- List the sibling commands and flags, and write the one sentence each new flag holds. Match their pattern.
- The rules, each with its standard: [references/cli-design.md](references/cli-design.md), for flags, prompts, help, errors, `--json`, exit codes, color, and config precedence.
- The project's own patterns win over a guide. When they differ, say so in the Spec.

## Review

- Run the command as a person would: `--help` once, a bad value once, a pipe once, and the exit code of each failure. The review checks and the blocking comment are in `aidd-team:naming`.

## Test commands

| Command | Proves | How |
| --- | --- | --- |
| CLI contract test | help, errors, exit codes, color, and `--json` hold | runs the command: `--help`, a bad value, a pipe with `NO_COLOR=1` (no color, no prompt, clean stdout), each exit code, and the `--json` shape against its schema |

## Stop if

- A shipped flag, exit code, or JSON field would change meaning or disappear in one step: warn for one release first (`aidd-team:naming`, expand and contract).
- A new flag clashes with a sibling and the glossary does not decide it: a person decides.

## Hand off

- Done: the command's contract and its CLI contract test. Next role: the reviewer. Needs: a person, for a clash the glossary does not decide. Stopped at: none, or the stop rule's code.
