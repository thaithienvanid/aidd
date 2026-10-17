---
id: dart/flutter-analyze
type: opinionated
fills: [ci-pipeline:linter]
default: true
implements: product-defaults:dev_basics
roles: [developer, reviewer]
when_changed: ["**/*.dart", analysis_options.yaml, pubspec.yaml]
why: "flutter analyze runs the Dart analyzer with the flutter_lints rule set, the one the Flutter team recommends for apps, packages, and plugins, so errors and style faults fail before a review."
reviewed: "2026-10-16"
maturity: established
version_policy: current_major
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [very_good_analysis, lints (the Dart team's recommended set)]
status: active
source: https://dart.dev/tools/analysis
evidence: "Tools such as dart analyze, flutter analyze, and IDEs and editors use the analyzer package to evaluate your code."
enforced_by:
  - name: analyze
    command: [flutter, analyze]
---

# flutter analyze with flutter_lints checks the Dart code

It answers the linter choice of `aidd-team:ci-pipeline` for Flutter.

## What the team does

- Add `flutter_lints` to `dev_dependencies` at its current major, and start `analysis_options.yaml` with `include: package:flutter_lints/flutter.yaml`.
- Turn on `strict-casts`, `strict-inference`, and `strict-raw-types` under `analyzer: language:` for new code.
- Write the reason beside each `// ignore:` comment. A bare ignore is a review finding.
- A team that wants a stricter set uses `very_good_analysis` instead, through its own standard and `standards_policy.replace`.
- pub.dev is not a release feed that `aidd eval standards --online` reads, so a person checks the `flutter_lints` major at each review.

## What the gate runs

One `tests` entry runs `flutter analyze`. An error, a warning, or an info fails the change.
