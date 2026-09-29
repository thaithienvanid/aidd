---
description: "Threat-model a Spec or security-review a PR/MR with the security engineer"
argument-hint: "<SPEC id or path, or PR/MR number>"
---

Loop steps: **Specify** (before Spec approval) for a Spec, **Review** (before Merge approval) for a PR/MR.

Lanes: spec, emergency.

Run the `aidd-team:security-engineer` subagent on $ARGUMENTS: a threat model (STRIDE), the ASVS level, and the security tests the tester must write, in the security return template (the aidd skill's Spec reference), for the architect to fold into a Spec; a vulnerability review for a PR/MR. The security engineer writes no test itself: the tester does, in Specify. Show the author the result and stop. The human reviewer from the security pool decides.
