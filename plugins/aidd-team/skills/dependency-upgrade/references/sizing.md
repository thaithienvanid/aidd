# Sizing an upgrade

Load this when you decide which route and how much ceremony an upgrade needs.

| The change | Route | What it needs |
| --- | --- | --- |
| A bot's patch or minor bump, lockfile and manifest only, of a package with good test coverage | `standard`, when a `[[standard_changes]]` class matches exactly | Green tests; no human approval |
| A patch or minor bump by a person or agent | `minor` (fast lane) | Changelog read, advisory check, full suite |
| A minor bump that changes a default or deprecates an API you use | `normal` | A Spec naming the deprecations and a test for the changed default |
| A major version | `normal` or `major` | Its own change; a deprecation plan; codemod output committed separately |
| A runtime, a language version, a base image, or a build toolchain | `normal` or `major` | The whole matrix built and tested; the platform engineer |
| An upgrade forced by an advisory on a production path | `emergency` only if it is being exploited; otherwise `normal`, first in the queue | The advisory id and the fixed version in the Spec |
| A 0.x package, any bump | Treat as a major | SemVer promises nothing before 1.0.0 |

## A deprecation plan, for a major

```text
package:     orm 5.x -> 6.0
deprecated:  Query.get()   used in 14 places -> Session.get()   codemod: orm-upgrade --fix
removed:     implicit autocommit                 -> explicit transactions in 3 jobs, by hand
defaults:    lazy loading raises in async code   -> eager loading on 2 relations
old API removed in: 7.0 (announced); our deadline: before 7.0 reaches our support window
rollback:    revert this change; no data migration
```

## Coherent groups

Upgrade together only what cannot run apart: packages released in lockstep under one version number, a framework and the plugins pinned to it, a type package and its runtime package. Everything else is its own change, so a failure points at one package and a revert removes one.
