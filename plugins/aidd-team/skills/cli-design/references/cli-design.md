# Designing a command-line interface

Load this when a Task adds or changes a command, a flag, a prompt, an exit code, a help text, machine output, or a setting a command reads. Scripts depend on all of them, so each is a public contract. The ids in brackets are the standards in the skill's table. A rule with no id is common practice that the standards do not state.

## Flags

- Make one choice one flag. Two flags that answer the same question can contradict each other (`--sort-by-date` and `--sort-by-name`), so give the choice values: `--sort=date|name`.
- A flag that takes a value accepts the word `none` for "no value": `ssh -F none`. [clig] A plain switch that is on by default gets a `--no-x` form, such as `--no-color`. Give one thing only one of the two.
- Use the standard name when there is one: `-h` and `--help`, `-n` and `--dry-run`, `-f` and `--force`, `-o` and `--output`. [clig]
- Every program takes `--help` and `--version`, and every short option has an equivalent long one. A `--` ends the options, and the operands follow it. [gnu-cli, posix-utility-conventions]
- State each default in the help: `--format (default: text)`.

## Safe by default

- Offer `--dry-run`, which describes the changes and makes none. [clig]
- Confirm a destructive action, and give scripts a flag that confirms it (`--yes` or `--force`). [clig]
- Prompt only when stdin is a terminal. Give every prompt a flag that answers it. With no terminal and no flag, fail and name the flag. A `--no-input` flag turns every prompt off. [clig]

## Help and errors

- Put examples first in `--help`, the common complex uses above the flag list. [clig]
- Catch the errors you expect and rewrite them for a person, with the next step. Name the bad value and the valid ones: `unknown format "yaml" (valid: text, json); try --format json`. [clig]
- Send the result to stdout, and messages and progress to stderr, so a pipe carries only the result. [clig]
- Where input or output is a file, accept `-` for stdin or stdout. On Ctrl-C, exit at once. [clig]

## Output and exit codes

- Offer `--json`. [clig] Give its one document a `schema_version`, so a script can tell when the shape changes, and check the shape against a schema in a test.
- Exit 0 on success and non-zero on failure. Give each main failure its own code (usage error, not found, refused), document every code, and keep each one stable. [clig]
- Turn color off when stdout or stderr is not a terminal, when `NO_COLOR` is set and not empty, whatever its value, when `TERM` is `dumb`, and with `--no-color`. [no-color, clig]
- A flag, a config key, an exit code, and an output field are interfaces. Keep changes additive. Before a change that is not, warn when the old form is used, for one release, and say how to change usage today. [clig]

## Configuration

- Precedence, highest first: flag, environment variable, project file, user file, system file. The help says so. [clig]
- A user's settings live under `$XDG_CONFIG_HOME` (default `~/.config`) and their state under `$XDG_STATE_HOME`, never loose in the home folder. [xdg-base-dir, clig]
- An environment variable is the tool's name in capitals, then the setting. A config key follows `aidd-team:data-model-design`.
