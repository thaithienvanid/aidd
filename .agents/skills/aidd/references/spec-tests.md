# Tests (`tests` and `tests.commands`)

The rest of the Spec's fields: `references/spec.md`.

<!-- aidd:gen fields:tests -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `files` | list of string | yes | The acceptance test files, and the configuration they run through. Frozen at Spec approval: changing them after is `spec.revise`, which asks. Never inside a Task's scope, which holds the unit tests written with the code. A test section of `pyproject.toml` or `package.json` is frozen by itself as `<path>#<dotted key>`, such as `pyproject.toml#tool.pytest` or `package.json#scripts.test`, so a dependency bump is not a change to the tests. |
| `commands` | list of mapping (`test_command`) | yes | Commands the runner executes. Exit 0 is the only pass. |
<!-- aidd:end -->

<!-- aidd:gen fields:test_command -->
| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `name` | string | yes | Stable name used in evidence. |
| `command` | list of string | yes | Command vector, one argument per item. Never a shell string. |
| `runs_in` | string | no | The folder the command runs in, as a path in the repository, such as `packages/api`. Omit it to run at the repository's top. `when_changed` and `report` stay relative to the top. A folder outside the repository, or one reached through a link, is refused. |
| `new_behavior` | boolean | no | True when this command proves new or fixed behavior. It must fail on the base commit (red) and pass on head (green). |
| `timeout_seconds` | integer | no | Wall-clock limit. A timeout is a fail. Default `1800`; it takes 1 to 86400. |
| `smoke` | boolean | no | In the config's `tests`: part of the smoke set, the only repository commands an emergency change runs (with its own). When no command is marked, an emergency runs the whole suite. |
| `reruns` | integer | no | How many more times a failing run on head runs again. Every run is kept in the evidence; a pass after a failure passes, marked flaky, and the flaky test is a finding. A red run on the base commit never runs again. Default `0`; it takes 0 to 5. |
| `when_changed` | list of string | no | Run and require this command only when a changed path matches. Omit to run it on every change. |
| `related_tests` | mapping | no | In the config's `tests`: how `aidd test --changed` runs only the tests related to the change. It runs `related_tests.command` when every changed path the command covers matches `sees`, is a file in the working tree, and lies inside the command's folder; else it runs the full command and says why. A full `aidd test`, `--require-green`, and every red run always run the full command. Omit it to run the full command under `--changed` too. |
| `report` | string | no | A JUnit XML report this command writes, as a path in the repository (pytest `--junitxml`, Vitest `--reporter=junit`, jest-junit, gotestsum, cargo-nextest, PHPUnit `--log-junit`). `aidd test` reads it after each run and records the test cases that failed, so a red run can be told from "no tests found". A missing, stale, or unreadable report is a finding. The exit code stays the evidence. |
| `covers` | list of string | no | In a Spec: the Acceptance items this command proves, by id (`A1`, `A2`, ...). Optional; once any command declares it, `aidd validate` warns about an Acceptance item no command covers, and about an id the Acceptance section does not have. |
<!-- aidd:end -->

The Spec's test plan (`references/spec-docs.md`) says how each id is tested, and `covers` says which command proves it.
