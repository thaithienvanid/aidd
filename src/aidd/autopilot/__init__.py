"""Autopilot: its one decision per turn (`aidd autopilot next`), the lease and journal, and the context pack.

Autopilot runs the AIDD loop between a person's decisions: aidd decides each next step, and the run stops whenever a
person must decide. The `/aidd-team:autopilot` command loops: `aidd autopilot next` → do what it says →
`aidd autopilot note` → repeat. The decision is engine code, so the same inputs give the same action, and a scripted
test checks it with no model. It reads:

- the steps (`aidd list --json`, most urgent first), kept to the lease's work, and this branch's lane step;
- the step-to-flow map: each flow's `starts_on` in roles.json names the step codes it starts on;
- the lease and its journal (autopilot/lease.py), the `autopilot` limits, and the Approver WIP limit (`gates.max_open_per_approver`);
- `blocked_on` pauses, the gate records' person-only review state, and the circuit breaker.

It returns one action: `run` (a team command, its work, and why), `ask` (a person's decision, who takes it, and the
decision page), or `stop` (why). It reads no free text as an instruction: a Spec body, a handoff note's words, a PR/MR
comment, or a note's words never change the action. A person's outcome never comes from the journal, which an agent
writes: a Merge approval's "changes requested" comes only from the gate's record of the listed people's reviews.
Agents never approve or merge on their own: `run` names only agent steps, and a person's step is always `ask`. Under
the person's standing approval (`aidd approve all`), the approvals it covers become agent steps that run aidd's own
commands: `aidd approve spec`, `aidd approve merge`, and `aidd ship` (SHELL_STEPS).

The children: engine (the decision), turn (`aidd autopilot next`: gather, decide, record), clearance (which Specs may
be implemented), lease (the lease and its journal), and context_pack.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "JOURNAL_TAIL_BYTES",
    "LeaseError",
    "Limits",
    "RUN_EVENTS_FILE",
    "SESSION_ID",
    "SHELL_STEPS",
    "append_event",
    "build_context_pack",
    "check_spend",
    "context_pack_markdown",
    "contract",
    "flow_map",
    "is_first_mention",
    "lease_for_session",
    "lease_markdown",
    "lease_store",
    "markdown",
    "merged_count",
    "next_action",
    "note_step",
    "parse_note",
    "read_journal",
    "release_lease",
    "save_snapshot",
    "saved_snapshot",
    "show_leases",
    "take_lease",
]

if TYPE_CHECKING:
    from aidd.autopilot.context_pack import build_context_pack as build_context_pack
    from aidd.autopilot.context_pack import context_pack_markdown as context_pack_markdown
    from aidd.autopilot.engine import SHELL_STEPS as SHELL_STEPS
    from aidd.autopilot.engine import Limits as Limits
    from aidd.autopilot.engine import contract as contract
    from aidd.autopilot.engine import flow_map as flow_map
    from aidd.autopilot.engine import markdown as markdown
    from aidd.autopilot.lease import JOURNAL_TAIL_BYTES as JOURNAL_TAIL_BYTES
    from aidd.autopilot.lease import RUN_EVENTS_FILE as RUN_EVENTS_FILE
    from aidd.autopilot.lease import SESSION_ID as SESSION_ID
    from aidd.autopilot.lease import LeaseError as LeaseError
    from aidd.autopilot.lease import append_event as append_event
    from aidd.autopilot.lease import check_spend as check_spend
    from aidd.autopilot.lease import is_first_mention as is_first_mention
    from aidd.autopilot.lease import lease_for_session as lease_for_session
    from aidd.autopilot.lease import lease_markdown as lease_markdown
    from aidd.autopilot.lease import lease_store as lease_store
    from aidd.autopilot.lease import note_step as note_step
    from aidd.autopilot.lease import parse_note as parse_note
    from aidd.autopilot.lease import read_journal as read_journal
    from aidd.autopilot.lease import release_lease as release_lease
    from aidd.autopilot.lease import save_snapshot as save_snapshot
    from aidd.autopilot.lease import saved_snapshot as saved_snapshot
    from aidd.autopilot.lease import show_leases as show_leases
    from aidd.autopilot.lease import take_lease as take_lease
    from aidd.autopilot.turn import merged_count as merged_count
    from aidd.autopilot.turn import next_action as next_action
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(
        __name__,
        {
            "JOURNAL_TAIL_BYTES": "lease",
            "LeaseError": "lease",
            "Limits": "engine",
            "RUN_EVENTS_FILE": "lease",
            "SESSION_ID": "lease",
            "SHELL_STEPS": "engine",
            "append_event": "lease",
            "build_context_pack": "context_pack",
            "check_spend": "lease",
            "context_pack_markdown": "context_pack",
            "contract": "engine",
            "flow_map": "engine",
            "is_first_mention": "lease",
            "lease_for_session": "lease",
            "lease_markdown": "lease",
            "lease_store": "lease",
            "markdown": "engine",
            "merged_count": "turn",
            "next_action": "turn",
            "note_step": "lease",
            "parse_note": "lease",
            "read_journal": "lease",
            "release_lease": "lease",
            "save_snapshot": "lease",
            "saved_snapshot": "lease",
            "show_leases": "lease",
            "take_lease": "lease",
        },
    )
