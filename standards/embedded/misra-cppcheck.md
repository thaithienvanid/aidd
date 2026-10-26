---
id: embedded/misra-cppcheck
type: opinionated
fills: [embedded-automotive-industrial:misra-checker]
default: true
implements: embedded-automotive-industrial:MISRA and static analysis
roles: [developer, security-engineer, reviewer]
when_changed: [misra.cppcheck, misra.json, "**/*.c", "**/*.h"]
why: "Cppcheck's open-source MISRA addon checks most MISRA C:2012 rules at no cost on every change, and a deviation record next to each suppression keeps what it skips visible to the assessor."
reviewed: "2026-10-22"
maturity: established
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
source: https://cppcheck.sourceforge.io/misra.php
evidence: Cppcheck covers almost all the MISRA C 2012 rules.
alternatives: [Cppcheck Premium, a qualified commercial checker]
status: active
enforced_by:
  - name: misra
    command: [cppcheck, --project=misra.cppcheck, --error-exitcode=1, --inline-suppr]
---

# Cppcheck's MISRA addon checks the C rules

It answers the misra-checker choice of `aidd-team:embedded-automotive-industrial`. Cppcheck is under the GNU GPL version 3, which covers the tool and not the code it checks.

## What the open-source addon covers

On 2026-10-22, Cppcheck's own pages said the open-source addon covers the original MISRA C:2012 rules and amendments 1 and 2, each in part. Amendments 3 and 4, MISRA C:2023, and both MISRA C++ editions are in Cppcheck Premium only. Rules 1.1, 1.2, and 17.3 are not checked, and the compiler covers the first two. The addon prints rule numbers, not rule texts, because the team supplies the licensed texts. So it is not evidence for the MISRA C:2025 edition the pack names. A product whose safety case claims that edition needs a qualified checker.

## What the team does

- Commit `misra.cppcheck`, a Cppcheck project that names the sources, include paths, defines, the target's C version, and the `misra` addon with its `misra.json` settings.
- Run the Cppcheck version the pack's MISRA test names, so the findings match.
- Point `misra.json` at the team's own copy of the rule texts, outside git when its licence says so.
- Suppress one finding in the line with `cppcheck-suppress misra-c2012-<rule>`, and record the deviation where the safety case keeps them.

## What the gate runs

One `tests` entry runs the project file. A finding without a suppression fails the change.
