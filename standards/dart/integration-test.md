+++
id = "dart/integration-test"
type = "opinionated"
fills = ["mobile-apps:mobile-ui-test"]
default = true
implements = "mobile-apps:UI tests on the OS matrix"
roles = ["tester", "developer", "reviewer"]
when_changed = ["integration_test/**", "lib/**", "pubspec.yaml"]
why = "The integration_test package runs the whole Flutter app on a device or an emulator with the flutter_test API the team already knows, and Firebase Test Lab can run the same tests on many devices."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
version_policy = "current_stable"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["Maestro", "Patrol"]
status = "active"
source = "https://docs.flutter.dev/testing/integration-tests"
evidence = "Use flutter_test APIs to write tests in a style similar to widget tests."
enforced_by = [
  { name = "device", command = ["flutter", "test", "integration_test"] },
]
+++

# integration_test drives the Flutter app on a device

It answers the mobile-ui-test choice of `aidd-team:mobile-apps` for a Flutter app.

## What the team does

- Add `integration_test` and `flutter_test` from the SDK to `dev_dependencies`. Keep the tests in `integration_test/`.
- Cover each critical journey: sign up, sign in, the main purchase or action, and account deletion.
- Find widgets by `Key`, never by visible text that a translation changes.
- Run the suite on the OS matrix of the pack's UI tests row, on an emulator in CI or in Firebase Test Lab.
- Give each test its own account or reset step, so no test depends on the one before it.

## What the gate runs

One `[[tests]]` entry runs `flutter test integration_test` on a running emulator or device. A failed test fails the change.
