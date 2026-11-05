# Breach and incident notification clocks

The one table of notification clocks; the packs and the privacy pack point here. Each clock counts from awareness, or from the regime's own trigger (a classification, a materiality decision), never from the end of the investigation. Read on 2026-09-30 from each regime's official text. The incident runbook names the ones that apply to the product, and contracts add their own notice periods.

| Regime | Who reports, to whom | Clock |
| --- | --- | --- |
| GDPR Art. 33, 34 | the controller, to the supervisory authority; to the people, when the risk to them is high | without undue delay, within 72 hours where feasible; people without undue delay |
| EU CRA Art. 14 (from 2026-09-11) | a manufacturer, through the single reporting platform | exploited vulnerability: early warning 24 h, notification 72 h, final report 14 days after a fix is available; severe incident: 24 h, 72 h, final report one month after the notification |
| NIS2 Art. 23 | an essential or important entity, to its CSIRT or authority | early warning 24 h, notification 72 h, final report one month after the notification |
| DORA, Delegated Regulation (EU) 2025/301 | a financial entity, for a major ICT incident | initial 4 h after classifying it major and within 24 h of awareness; intermediate 72 h after the initial; final one month after the latest intermediate |
| HIPAA 45 CFR 164.404, 164.406, 164.408 | a covered entity, to the individuals, the media, and HHS | individuals without unreasonable delay and within 60 calendar days of discovery; the media in a State, for 500 or more of its residents, in the same time; HHS with that notice for 500 or more, within 60 days after the calendar year's end for fewer |
| DFARS 252.204-7012(c) (read 2026-10-22) | a defense contractor holding covered defense information, to DoD through DIBNet | rapidly report: within 72 hours of discovery; keep images of affected systems and packet captures at least 90 days from the report |
| SEC Form 8-K Item 1.05 | a registrant, in a public filing | four business days after it determines the incident is material |

Notes:

- GDPR: a processor tells its controller without undue delay (Art. 33(3)), and within the contract's own deadline. Every breach is documented, notified or not (Art. 33(5)). A late notice says why.
- CRA: the clocks run from the manufacturer becoming aware. The final report for a vulnerability waits for a corrective or mitigating measure.
- DORA: the time limits are those of Commission Delegated Regulation (EU) 2025/301, Article 5.
- US state breach laws add their own clocks, some as short as 30 days. The runbook lists the states where the users live.
- An agent drafts each notice from the facts: what data or service, whose, how many, since when, and what was done. A person with the authority decides and sends it.
