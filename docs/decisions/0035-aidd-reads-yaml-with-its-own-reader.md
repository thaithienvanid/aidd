# 35. aidd reads YAML with its own reader, for a strict subset

Accepted on 2026-11-16, for a decision made while aidd was built. In force.
The maintainers decided it while aidd was built, and this record keeps the reasons that the architecture page gave. Every contributor is informed through this record.

## Context and problem statement

Every document aidd reads has its fields as YAML between `---` lines, and the config is a YAML file. YAML readers differ: YAML 1.1 reads `yes` and `on` as booleans, and YAML 1.2 does not. A value such as `1.0.0` or a date may become text, a number, or a date. A person's editor and aidd must read one file the same way. Which reader does aidd use?

## Considered options

- **A YAML library, such as PyYAML.** It costs a runtime dependency, which the standard-library-only rule forbids, and it gives no promise that another reader reads the file the same.
- **No YAML: JSON for the config and the front matter.** It costs the comments and the plain look of a file that a person edits by hand.
- **aidd's own reader, for a strict subset of YAML.** It costs a reader to keep, and a bug in it could misread a document.

## Decision outcome

The chosen option is "aidd's own reader, for a strict subset", because the subset can be one that every YAML reader reads the same.

> aidd reads YAML with `kernel/strict_yaml.py`, which accepts only what every YAML reader reads the same. Anything outside the subset is an error that names the line and the fix.

### The case that decided it

A version `1.0.0`, a date, `yes`, or `on` must be quoted, and so must a key such as `on`. An anchor, a tag, null, a duplicate key, or a tab is refused. A person who leaves a date unquoted gets an error and the line to fix, and never a value that one tool takes as a date and another as text. The cost of a reader aidd owns is a control: `tests/test_strict_yaml.py` checks it against PyYAML on every document it accepts, and CI requires PyYAML for that. `kernel/yaml_edit.py` changes one key of a person's file on its own line, so the rest of the file stays as it was.

### Consequences

- Good, because the config and every front matter read the same in aidd and in the person's editor.
- Good, because a mistake is an error with a line, not a silent guess.
- Bad, because a person must quote a value that YAML would have read as a number, a date, or a boolean.
- Bad, because a reader bug could misread a document. The differential tests are the control.

### Reopen when

The differential tests find a document that aidd and PyYAML read differently, and no fix to the reader closes it.

## More information

[The architecture page](../architecture/README.md#file-formats) lists the file formats. [0003](0003-state-in-files-a-person-can-read.md) says why state lives in files.
