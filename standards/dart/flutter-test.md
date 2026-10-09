+++
id = "dart/flutter-test"
type = "opinionated"
fills = ["ci-pipeline:test-runner"]
default = true
implements = "product-defaults:dev_basics"
roles = ["developer", "tester", "reviewer"]
when_changed = ["lib/**", "test/**", "pubspec.yaml"]
why = "flutter test runs unit and widget tests without a device, in seconds, with the flutter_test package that ships with the SDK."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
version_policy = "current_stable"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["package:test alone, for a pure Dart package"]
status = "active"
source = "https://docs.flutter.dev/testing/overview"
evidence = "A widget test (in other UI frameworks referred to as component test) tests a single widget."
enforced_by = [
  { name = "unit", command = ["flutter", "test"] },
]
+++

# flutter test runs the unit and widget tests

It answers the test-runner choice of `aidd-team:ci-pipeline` for Flutter.

## What the team does

- Put unit and widget tests under `test/`, mirroring `lib/`. Tests that need a device go under `integration_test/` (`dart/integration-test`).
- Write a widget test for each screen state: loading, empty, error, and filled.
- Fake the network and the platform channels in unit and widget tests. A test that calls a real service belongs in the integration suite.
- Use golden tests only for widgets whose look is the point, and update the goldens on one stated platform.
- Run `flutter test --coverage` in CI and keep the report as an artifact.

## What the gate runs

One `[[tests]]` entry runs `flutter test`. A failed test fails the change.
