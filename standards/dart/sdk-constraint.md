---
id: dart/sdk-constraint
type: opinionated
fills: [ci-pipeline:language-version]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, reviewer]
when_changed: [pubspec.yaml, pubspec.lock]
why: "The environment constraint in pubspec.yaml names the Dart and Flutter versions the app needs, and pub refuses a resolution outside it, so CI and every machine agree on the floor."
reviewed: "2026-10-16"
maturity: established
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: ["a version manager file, such as .fvmrc, beside the constraint"]
status: active
source: https://dart.dev/tools/pub/pubspec
evidence: Pub tries to find the latest version of a package whose SDK constraint works with the version of the Dart SDK that you have installed.
enforced_by:
  - name: lock
    command: [flutter, pub, get, --enforce-lockfile]
---

# The pubspec constraint pins the Dart and Flutter versions

It answers the language-version choice of `aidd-team:ci-pipeline` for Flutter.

## What the team does

- Set both bounds under `environment:` in `pubspec.yaml`: `sdk:` for Dart and `flutter:` for Flutter. Raise the floor to the stable release CI installs.
- Commit `pubspec.lock` for an app. A package publishes no lockfile.
- Raise the constraint in its own change, with the Flutter upgrade (`dart/flutter`) and its release notes.
- Keep the release CI installs in one file that the CI workflow and every developer read.

## What the gate runs

One `tests` entry runs `flutter pub get --enforce-lockfile`. A lockfile that no longer resolves `pubspec.yaml`, or a changed package hash, fails the change.
