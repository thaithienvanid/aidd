# 30. `aidd approve` and `aidd cancel` require a terminal in every coding agent

Accepted on 2026-11-14. In force for `aidd approve`; decided for 1.0.0, not built yet, for `aidd cancel`.
The project owner decided it, and the architect was consulted. Every contributor is informed through this record.

## Context and problem statement

`aidd approve` and `aidd cancel` write a person's decision commit. Should either command run without a terminal inside a coding agent session when the harness asks first?

## Considered options

- **Allow no-terminal runs inside a checked coding agent session.** It costs safety, because any child process started by an allowed command shares the session environment.
- **Require a terminal in every coding agent.** It costs one extra step in agents without commit ask rules, where a person runs the command in their own terminal.

## Decision outcome

The chosen option is "require a terminal in every coding agent", because a session check cannot separate an asked command from its child processes.

> `aidd approve` and `aidd cancel` run only at a terminal in every coding agent, and `aidd decline` follows that rule for a person's name. A yes in chat still works through the commit the agent asks to make.

### The case that decided it

A script, test, or git hook started by an allowed command inherits the same session variables as the coding agent. Requiring a terminal blocks plain shell calls everywhere, while harnesses that ask on `git commit *Approves*` or `*Cancels*` still let a person say yes in chat.

### Consequences

- Good, because no child process in an allowed run can record a person's decision silently.
- Bad, because in coding agents without those commit patterns, a person must run the command in their own terminal.

### Reopen when

A harness isolates the asked command's process so a child process cannot inherit its session check.

## More information

[0020](0020-an-approval-names-its-content.md) defines the commit hold, and [SECURITY.md](../../SECURITY.md) states the terminal rule.
