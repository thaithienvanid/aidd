# Incident document and updates

Load this when you open the incident document or draft an update for the commander.

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

## Cadence by severity (a starting point; the project's own scale wins)

| Severity | Responders | Support and leadership | Customers |
| --- | --- | --- | --- |
| Highest | every 15-30 minutes | every 30-60 minutes | status page at start, on change, at end |
| Middle | every 60 minutes | at start and end | only if they can see it |
| Lowest | in the channel as it moves | at the end | none |

## Update template

```text
[INC-<n>] <status> at <UTC time>
Impact: <who and what, in the user's words>
Doing: <the current mitigation, and its effect so far>
Not yet known: <what is still open; no guessed cause>
Next update: <UTC time>
```

## Security incidents

- The security engineer joins at declaration; evidence handling and containment follow NIST SP 800-61 Rev. 3.
- Notification duties (personal data breach notices, contractual notices) have legal clocks; the commander brings in the person who owns them at declaration, not at the end.
