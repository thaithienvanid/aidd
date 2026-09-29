# Profiles

A profile sets how strict the gates are. Pick the weakest one that fits who approves. `[gates]` values may only tighten the profile; a looser value is ignored with a warning. A config that extends another cannot choose a weaker profile (that is an error).

- **solo**: one person directs agents and approves their work. SoD is waived and recorded as `waived_solo`. Compensating controls apply: SHA-bound tests, protected paths, a deliberate `/aidd approve <full head SHA>` comment, and a 30-minute cool-off on major.
- **team**: one or a few teams on a repo. Spec approval before implementation, an Approver who is not the author, and a specialist reviewer on major.
- **org**: many teams and repos. Team plus a bound Policy on major and emergency.
- **regulated**: finance, health, and public sector. Two Approvers plus each specialist pool on major (and on the Spec hash), a Policy on every route, an `Assisted-by` trailer on every commit, Observe on normal, and no standard changes.

<!-- aidd:gen profiles -->
| Gate | solo | team | org | regulated |
| --- | --- | --- | --- | --- |
| Approvers must differ from the authors | no | yes | yes | yes |
| Spec approval on routes | major | normal, major | normal, major | normal, major |
| Specialist pools also approve the Spec on major | no | no | no | yes |
| Merge approvals per route | minor 1, normal 1, major 1, emergency 1 | minor 1, normal 1, major 1, emergency 1 | minor 1, normal 1, major 1, emergency 1 | minor 1, normal 1, major 2, emergency 1 |
| Approvals from each specialist pool on major | 0 | 1 | 1 | 1 |
| Cool-off minutes before an approval counts | major 30 | none | none | none |
| Bound Policy required on routes | none | none | major, emergency | minor, normal, major, emergency |
| AI provenance | declare | declare | declare | every_commit |
| Red-then-green proof for new behavior | warn | require | require | require |
| Standard changes allowed | yes | yes | yes | no |
| Observe block required on routes | major | major | major | normal, major |
| Changed-line budget per route | minor 50, normal 800, major 800 | minor 50, normal 400, major 400 | minor 50, normal 400, major 400 | minor 50, normal 400, major 300 |
| Commit authors with no platform account | warn | warn | warn | fail |
| Spec approval proven before implementation | optional | optional | optional | require |
| Open waits per Approver before `aidd next` warns (0: off; never gated) | 0 | 3 | 3 | 3 |
| Minutes before `aidd next` escalates a wait (0: off; never gated) | 0 | 0 | 0 | 0 |
<!-- aidd:end -->
