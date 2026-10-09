+++
id = "dart/flutter"
type = "opinionated"
fills = ["mobile-apps:mobile-framework"]
default = true
implements = "mobile-apps:Store SDK floors"
roles = ["architect", "developer", "reviewer"]
when_changed = ["pubspec.yaml", "pubspec.lock", "android/**", "ios/**", "lib/**"]
why = "Flutter draws the same widgets on iOS and Android from one Dart code base, and its stable channel is the one Google recommends for production releases, so a Dart team ships both apps from one tree."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
version_policy = "current_stable"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["Expo (React Native)", "Swift and Kotlin, one app per platform"]
status = "active"
source = "https://docs.flutter.dev/install/archive"
evidence = "The stable channel is the recommended channel for new users and for production app releases."
+++

# Flutter on the stable channel builds the Dart mobile app

It answers the mobile-framework choice of `aidd-team:mobile-apps` for a team that writes Dart.

## What the team does

- Build releases only on the stable channel. CI installs one stated stable release, and every developer runs the same one.
- Name that release's floor in `pubspec.yaml` (`dart/sdk-constraint`). Move to a newer stable release in its own change, after you read its release notes and run `dart fix --apply`.
- Commit `android/` and `ios/`. Review a change to them as native code, with its Gradle and Xcode settings.
- Build store artifacts with `flutter build appbundle` and `flutter build ipa`. Add `--obfuscate --split-debug-info=<dir>`, and keep the symbol files for crash reports.
- Set the Android `targetSdkVersion` and the iOS deployment target in the platform files. The Store SDK floors check reads the built artifacts.
- Format, analyze, and test with the `dart/` standards of the `flutter-mobile` stack.

## What the gate runs

Nothing of its own. `dart/dart-format`, `dart/flutter-analyze`, `dart/flutter-test`, `dart/integration-test`, and `dart/sdk-constraint` each add their `[[tests]]` entry.
