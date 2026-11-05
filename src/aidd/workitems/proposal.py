"""Proposals: the case put to someone who decides, before any code, and the bridge to delivery once it is accepted.

A proposal goes to a client (a bid, a pitch, a response to a request for proposal) or to the company's own decision
makers (a change put to leadership). Its front matter holds what a decision maker compares: the needs and how each
is answered, the options, a range estimate and its parts, the claims and their evidence, the RAID log (risks,
assumptions, issues, dependencies), the milestones, the exclusions, and open questions. `matrix` renders them as tables
for the document that is sent, and `convert` turns an accepted proposal into an Initiative and Epics whose ids trace
back to it. One home per phase: the proposal keeps what was promised, frozen at sign-off, and the Initiative takes the
milestones, the RAID log, and the scope decisions log as the delivery record, so every change delivered later answers
to what was promised and nothing is tracked twice.
"""

from __future__ import annotations

DECISIONS = ("go_no_go", "sign_off")  # the two a person records; an agent never does
