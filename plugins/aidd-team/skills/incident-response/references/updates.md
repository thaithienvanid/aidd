# Incident document and updates

Load this when you pick a severity, open the incident document, or draft an update for the commander.

## Severity (defaults; the project's own scale wins)

| Severity | Default meaning | Response |
| --- | --- | --- |
| sev1 | a critical user journey is down, data is lost or corrupted, or a breach touches many users | page now; a named commander; the status page within 15 minutes (a default) |
| sev2 | a critical journey is degraded, or a major feature is down, for a large share of users | page; a named commander; the status page if customers can see it |
| sev3 | a minor feature is degraded, and a workaround exists | a ticket; the owning team fixes it in working hours |

- When you are not sure, declare the higher severity. To lower it later costs little.
- A postmortem is due for every sev1 and sev2, and, by default, for any incident that used more than 25% of an error budget. Write it within 5 working days of the end, or by the backfill Spec's `review_due` when that comes first.

## Incident document

```text
Incident:   INC-<n>  <short name>          Severity: <per the project's scale>
Commander:  <person>      Operations: <person or agent>   Communications: <person>
Status:     investigating | mitigating | monitoring | resolved
Impact:     who is affected, how, since when (UTC)
Next update: <UTC time>, to <audience>

Timeline (UTC)
14:02  alert: checkout error rate 12% (SLO 0.5%)                        seen by on-call
14:05  declared sev2, commander <person>
14:07  release 2026.09.28.3 went out at 13:58; proposal: roll back       agreed by commander
14:09  rollback started
14:14  error rate 0.3%; monitoring
14:44  resolved by commander; backfill INC-<n> opened

Evidence
- logs 13:50-14:20 exported to <location>, handled by <person>
- dashboard images, deployed version, configuration diff
```

## Cadence by severity (a starting point)

| Severity | Responders | Support and leadership | Customers |
| --- | --- | --- | --- |
| sev1 | every 15-30 minutes | every 30-60 minutes | status page at start, on change, at end |
| sev2 | every 60 minutes | at start and end | only if they can see it |
| sev3 | in the channel as it moves | at the end | none |

## Update template

```text
[INC-<n>] <status> at <UTC time>
Impact: <who and what, in the user's words>
Doing: <the current mitigation, and its effect so far>
Not yet known: <what is still open; no guessed cause>
Next update: <UTC time>
```

## Security incidents

- The security engineer joins at declaration. Evidence handling and containment follow NIST SP 800-61 Rev. 3.
- Notification duties (personal data breach notices, contractual notices) have legal clocks. The commander brings in the person who owns them at declaration, not at the end.
