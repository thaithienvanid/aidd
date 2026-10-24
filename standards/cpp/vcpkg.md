---
id: cpp/vcpkg
type: opinionated
fills: [ci-pipeline:package-manager]
default: true
implements: ci-pipeline:Dependencies declared and locked
roles: [developer, sre, security-engineer, reviewer]
when_changed: [vcpkg.json, vcpkg-configuration.json, CMakePresets.json]
why: "vcpkg in manifest mode declares each C and C++ dependency in vcpkg.json and fixes every version with one baseline commit, and CMake installs them during configure through vcpkg's toolchain file."
reviewed: "2026-10-22"
maturity: established
tool:
  name: vcpkg
  registry: github
  package: microsoft/vcpkg
version_policy: current_stable
checked_version: "2026.10.16"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://learn.microsoft.com/en-us/vcpkg/concepts/manifest-mode
evidence: Manifest mode uses declarative JSON files to describe metadata about your project or package.
alternatives: [Conan 2, CMake FetchContent pinned to a tag or commit, a vendored copy of the dependency]
status: active
enforced_by:
  - name: baseline
    command: [sh, -c, "grep -q '\"builtin-baseline\"' vcpkg.json || { echo 'vcpkg.json has no builtin-baseline'; exit 1; }"]
---

# vcpkg installs and pins the C and C++ dependencies

It answers the package-manager choice of `aidd-team:ci-pipeline` for C and C++. vcpkg is under the MIT license.

## What the team does

- Declare each dependency in `vcpkg.json` and commit it. Never install with classic mode's `vcpkg install <port>`.
- Set `builtin-baseline` to the commit of a vcpkg release tag, so every dependency resolves to the version that release holds. vcpkg has no lockfile, so the baseline and any `overrides` are the pin.
- Move the baseline with `vcpkg x-update-baseline` in a change of its own, through `aidd-team:dependency-upgrade`. Pick a release at least 7 days old, so a bad port is caught upstream first.
- Set `CMAKE_TOOLCHAIN_FILE` to vcpkg's `scripts/buildsystems/vcpkg.cmake` in the base configure preset. CMake then installs the manifest's dependencies before it builds.
- Cache vcpkg's binary packages in CI by the hash of `vcpkg.json` and the baseline.
- Conan 2, also under the MIT license, is the alternative for a team that already runs it. Its lockfile pins each version.

## What the gate runs

One `tests` entry fails when `vcpkg.json` has no `builtin-baseline`. The `build` workflow of `cpp/cmake-presets` installs the dependencies, so an unresolvable manifest fails there.
