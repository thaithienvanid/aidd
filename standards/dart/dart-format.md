---
id: dart/dart-format
type: opinionated
fills: [ci-pipeline:formatter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.dart"]
why: "dart format ships with the Dart SDK and has one style with almost no options, so CI, the pre-commit hook, and every editor format the code the same way."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
status: active
source: https://dart.dev/tools/dart-format
evidence: Use exit codes with continuous integration (CI) systems so they can trigger another action in response to the exit code.
enforced_by:
  - name: format
    command: [dart, format, --output=none, --set-exit-if-changed, "."]
---

# dart format sets the layout of the Dart code

It answers the formatter choice of `aidd-team:ci-pipeline` for Dart and Flutter.

## What the team does

- Use the `dart format` of the SDK the project pins. It has no rival formatter, so a company replaces it only with its own standard.
- Leave the page width at its default unless the whole repository changes it, once, in `analysis_options.yaml` under `formatter`.
- Run it in the pre-commit hook and on save in each editor.
- Never ask for a layout change in a review. The formatter decides it.

## What the gate runs

One `tests` entry runs `dart format --output=none --set-exit-if-changed .`. A file that the formatter would change fails the change.
