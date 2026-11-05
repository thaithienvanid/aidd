# Errors a person reads

Load this when a Task writes an error message, a refusal, or a warning that a person reads: in a screen, an API response, or a command line. An error is the text a person reads when they're already stuck, so it gets the same review as a page.

## What every error says

1. **What happened**, in the reader's words, about their task: "The file `report.csv` has no header row", never "Parse error".
2. **Why**, when the reader can act on it: the value, the limit, or the rule that failed. Say which input was wrong, and never blame the reader.
3. **What to do now**: one next step that works where the reader is, such as a command, a link, or the field to fix. When the fix needs a tool the reader may not have, name a way that always works too.
4. **A code and a link for support**: a stable code, such as `payment_declined`, and a link to its page, with the cause and the fix. Add the trace ID when there is one, so support finds the log line without asking.

Keep it short, plain, and neutral, at the level `aidd-team:plain-language` sets. Show it next to the thing that failed, with more than color to mark it. Keep what the reader already typed. A message the reader can't act on goes to the log, not the screen.

## On a command line

- Errors and warnings go to stderr, and output goes to stdout, so a pipe carries only the output.
- Exit 0 on success and non-zero on failure. Give each failure mode a script must tell apart its own code, and document the codes with the commands.
- A debug flag (`--debug`) or a variable (`DEBUG=1`, or the tool's own) shows the traceback and the detail. Without it, show the human message only.
- Add color only on a terminal: check that the stream is a TTY, and add no color when `NO_COLOR` is set to any non-empty value. A flag such as `--json` gives scripts a stable, machine-readable form on stdout.
- An unexpected crash names a way to report a bug. Give a URL that fills in the version and the environment, and say what to attach, never a secret.

## Sources

- [Command Line Interface Guidelines](https://clig.dev/) (clig.dev): errors rewritten for humans, stderr, exit codes, a debug flag, and an easy bug report.
- [NO_COLOR](https://no-color.org/): software that adds color by default checks for a non-empty `NO_COLOR` and adds none.
- [Error-Message Guidelines](https://www.nngroup.com/articles/error-message-guidelines/), Nielsen Norman Group, 2023: visible, plain, specific, constructive, and blameless.
- [Microsoft Writing Style Guide](https://learn.microsoft.com/en-us/style-guide/top-10-tips-style-voice), "Top 10 tips": write like you speak, get to the point fast, and replace "Invalid ID" with what a valid one looks like.
