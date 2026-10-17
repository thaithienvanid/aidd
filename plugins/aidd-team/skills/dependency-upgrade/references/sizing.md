# Sizing an upgrade

Load this when you decide which route and how much ceremony an upgrade needs.

| The change | Route | What it needs |
| --- | --- | --- |
| A bot's patch or minor bump, lockfile and manifest only, of a package with good test coverage | `standard`, when a `standard_changes` class matches exactly | Green tests; no human approval |
| A patch or minor bump by a person or agent | `minor` (fast lane) | Changelog read, advisory check, full suite |
| A minor bump that changes a default or deprecates an API you use | `normal` | A Spec naming the deprecations and a test for the changed default |
| A major version | `normal` or `major` | Its own change; a deprecation plan; codemod output committed separately |
| A runtime, a language version, a base image, or a build toolchain | `normal` or `major` | The whole matrix built and tested; the platform engineer |
| An upgrade forced by an advisory on a production path | `emergency` only if it is being exploited; otherwise `normal`, first in the queue | The advisory id and the fixed version in the Spec |
| A 0.x package, any bump | Treat as a major | SemVer promises nothing before 1.0.0 |

## Fix windows

How long a known vulnerability may stay in production, from the day the team learns of it. These are aidd's defaults. A team changes them to fit its risk and its contracts, writes its own in a `standards` entry, and tracks each fix against them.

| Severity (CVSS v4.0 score) | Fixed in production within |
| --- | --- |
| Critical (9.0 to 10.0), or in the KEV catalog | 48 hours |
| High (7.0 to 8.9) | 7 days |
| Medium (4.0 to 6.9) | 30 days |
| Low (0.1 to 3.9) | the next planned upgrade |

- An entry in CISA's Known Exploited Vulnerabilities (KEV) catalog is exploited now. It counts as Critical, whatever its score.
- For a KEV entry, the 48-hour default is stricter than CISA BOD 26-04, which binds US federal agencies to 3 or 14 days. For other entries it can be looser: BOD 26-04 sets each timeline from exposure, automatability, impact, and KEV status, and gives some non-KEV entries 3 days. A team bound by BOD 26-04 uses its table.
- A CVSS Base score rates severity, not your risk. Change a window for one advisory only with a written reason, such as "the vulnerable function is never called".

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

Upgrade together only what cannot run apart:

- packages released in lockstep under one version number;
- a framework and the plugins pinned to it;
- a type package and its runtime package.

Everything else is its own change, so a failure points at one package and a revert removes one.
