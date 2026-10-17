"""The gate rules, one function each, run in order over a shared `GateRun` (gate_run.py).

Each gate reads the context and what earlier gates derived, records facts,
and adds findings. A gate that makes the rest meaningless (no config, no
valid block, no Spec) calls `run.stop()`. To add a rule, write a function
that takes a Run and put it in GATES; org rules that should not live here
go through the Policy interface instead (see gate/policy.py).
"""

from __future__ import annotations

from collections.abc import Callable

from aidd.gate.rules import approval_facts, approvals, declared, evidence, gate_run, route, safety

# Order matters only where a step derives facts later ones read: gate_config, gate_change_request, gate_facts,
# gate_standard_change and gate_route set up the declaration, the diff, and the route; derive_approvals builds
# the approval facts every approval gate reads. The remaining gates only read.
GATES: list[Callable[[gate_run.GateRun], None]] = [
    declared.gate_config,
    route.gate_explore,  # before anything that stops: a change from an explore branch always fails
    safety.gate_secrets,
    declared.gate_change_request,
    declared.gate_facts,
    declared.gate_standard_change,
    route.gate_route,
    route.gate_scope,
    route.gate_budget,
    route.gate_merge_queue,
    evidence.gate_tests_declared,
    route.gate_harness,
    evidence.gate_status_checks,
    evidence.gate_evidence,
    approval_facts.derive_approvals,
    approvals.gate_spec_approval,
    evidence.gate_red_green,
    evidence.gate_spec_phase,
    approvals.gate_merge_approval,
    approvals.gate_specialist_approval,
    safety.gate_policy,
    safety.gate_emergency,
    safety.gate_observe,
    safety.gate_provenance,
    route.gate_draft,
]
