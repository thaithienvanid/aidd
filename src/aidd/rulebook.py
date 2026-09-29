"""What each gate rule checks, as data: the single source for the rule tables in docs/METHOD.md and the
skill's references/gate.md (`aidd gen-docs`), for the finding-code table in examples/README.md, and for
`aidd gate --explain <rule>`.

A test keeps this list and the rules gates.py can emit in step, and each row's `codes` equal to the finding codes
the verifier declares for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    name: str
    levels: str
    holds: str
    fix: str
    # Every finding code the rule can emit (`rule.reason`), each with a one-line meaning.
    codes: dict[str, str] = field(default_factory=dict, hash=False)


RULES: tuple[Rule, ...] = (
    Rule(
        "context",
        "fail",
        "the adapter's context validates against its schema",
        "report it with the context JSON; the gate fails closed",
        codes={"context.invalid": "the context does not validate against context.schema.json (one finding per schema error, up to ten)"},
    ),
    Rule(
        "internal",
        "fail",
        "the verifier ran without error; any crash fails closed and the gate posts `error`",
        "report it with the context JSON",
        codes={"internal.crash": "the verifier raised an exception; it fails closed"},
    ),
    Rule(
        "config",
        "fail, pending, or warn",
        "the base branch has a valid `.aidd/config.toml` (pending when only the change itself adds one, fail when there is none); "
        "outside solo, `owners.approvers` is not empty",
        "an administrator merges the first config; set `owners.approvers`",
        codes={
            "config.missing": "no `.aidd/config.toml` on the base branch or in the change",
            "config.bootstrap": "only the change itself adds the config; an administrator merges the first one",
            "config.invalid": "the base branch's config (or a parent it extends) does not parse or validate",
            "config.warning": "a config setting was ignored, such as a gate looser than the profile allows",
            "config.newer_version": "the config declares an `aidd_version` newer than this verifier",
            "config.no_approvers": "the profile needs `owners.approvers`, and it is empty",
        },
    ),
    Rule(
        "change_request",
        "fail or warn",
        "exactly one valid `toml aidd` block; with `spec`, only `spec` and `trace_id`; an inline emergency names its `backfill`; "
        "a bot PR without a block matches its standard change class",
        "copy `assets/change-request.md`, or run `aidd change`",
        codes={
            "change_request.no_block": "the PR/MR description has no `toml aidd` block",
            "change_request.invalid": "the block does not parse, is not the only one, or does not validate against change-request.schema.json",
            "change_request.extra_keys": "a block that names a Spec holds keys other than `spec` and `trace_id`",
            "change_request.trace_id_mismatch": "the block's `trace_id` differs from the Spec's",
            "change_request.standard_by_default": "a bot PR with no block is treated as the standard change class that lists its author",
        },
    ),
    Rule(
        "spec",
        "fail",
        "normal and major name a Spec that exists at head, validates, and lints",
        "`aidd validate specs/<ID>.md` until 0 errors",
        codes={
            "spec.missing": "normal or major without a `spec` in the block",
            "spec.not_at_head": "the named Spec file is not in the head commit",
            "spec.unparsable": "the Spec's front matter does not parse",
            "spec.invalid": "the Spec does not validate or lint (one finding per error)",
        },
    ),
    Rule(
        "confidence",
        "fail",
        "not `low`",
        "answer the open questions, then run `aidd next` again",
        codes={"confidence.low": "the change declares confidence `low`"},
    ),
    Rule(
        "route",
        "fail or warn",
        "the declared route is at least the computed minimum, except that a Spec-backed normal change is raised to major (warn); "
        "an inline block declares every implied dimension (a Spec gets a warning)",
        "`aidd next`; write a Spec when the diff needs one",
        codes={
            "route.too_low": "the declared route is below the minimum the paths, dimensions, and type compute",
            "route.raised_to_major": "a Spec-backed normal change computes major, so it is raised and the major route's rules apply",
            "route.undeclared_dimensions": "`risk.dimensions` lacks a dimension the changed paths imply (fail on an inline block, warn on a Spec)",
        },
    ),
    Rule(
        "scope",
        "fail or warn",
        "every changed path (rename sources too) is inside a Task's scope, the Spec, its backfill, a test or design file, or "
        "`scope_exempt_paths`; no scope pattern matches every path; a declared inline scope and the test files do not overlap "
        "(a minor change that declares no scope takes its changed paths); every Task of a Spec changes something in its "
        "scope (warn: the plan and the diff disagree)",
        "keep to the scope; widen the Spec and get Spec approval again; finish or remove a Task that changed nothing",
        codes={
            "scope.outside": "a changed path (or rename source) is outside every Task's scope and the exempt paths",
            "scope.catch_all": "a scope pattern matches every path, so it declares no scope",
            "scope.test_catch_all": "a test-file pattern matches every path, so it names no test file",
            "scope.overlaps_test": "an inline block's scope overlaps a test file",
            "scope.untouched_task": "a Task changed nothing in its scope: the plan and the diff disagree",
        },
    ),
    Rule(
        "budget",
        "fail",
        "changed lines are within `max_changed_lines` for the route, excluding `budget_exclude_paths` and, for a Spec, the Spec and its "
        "test and design files Spec approval froze (standard uses its class limit; emergency has none)",
        "split the change, or exclude generated files",
        codes={"budget.exceeded": "the changed lines exceed the route's `max_changed_lines`"},
    ),
    Rule(
        "merge_queue",
        "fail",
        "for a merge-queue entry (`merge_group` in the context): its commit's tree is exactly the approved head merged into the commit "
        "the entry was built on; an entry built on another entry passes only when the queue merges a group once every entry passed",
        'queue the pull request again from its approved head; turn on the queue\'s "Only merge non-failing pull requests"',
        codes={
            "merge_queue.conflict": "the approved head does not merge cleanly into the commit the queue entry was built on",
            "merge_queue.diff_mismatch": "the merge-group commit's tree is not the approved head merged into the commit it was built on",
            "merge_queue.stacked_unverified": "the entry is built on another entry, and the queue is not confirmed to merge only all-green groups",
        },
    ),
    Rule(
        "authors",
        "fail or warn",
        "the platform returned the whole commit list (fail); every commit author maps to a platform account, unless the platform itself "
        "blocks committers from approving (`unlinked_authors`: warn, fail under regulated)",
        "split or squash the change; link the email, or list agent emails in `identities.bots`",
        codes={
            "authors.truncated": "the platform returned only part of the commit list",
            "authors.unlinked": "a commit author maps to no platform account (warn, or fail under `unlinked_authors = fail`)",
        },
    ),
    Rule(
        "tests",
        "pending, fail, or warn",
        "the repository has tests (a suite, `evidence.status_checks`, or the Spec's); a minor change has the suite or `status_checks`; "
        "every applicable command (`when_changed` included) has a green result on this exact head and base, from a test run of the "
        "change's own branch, with the declared command; names are unique; every `status_checks` name succeeded on head, from an allowed "
        "app and the change's own branch; with `evidence.signer_workflow`, the evidence carries that workflow's attestation; the "
        "evidence is not partial (`aidd test --changed`); in a merge queue, the head and base are the merge-group commit and the "
        "commit it was built on",
        "`aidd test`; in CI, wait for `aidd-tests`",
        codes={
            "tests.evidence_partial": "the evidence comes from `aidd test --changed`, which runs only some commands",
            "tests.none": "the repository and the change declare no tests at all",
            "tests.minor_without_suite": "a minor change has neither the repository suite nor `evidence.status_checks`",
            "tests.none_applies": "no declared test command's `when_changed` matches the diff",
            "tests.duplicate_name": "a test name is declared twice, in the config and the Spec",
            "tests.no_op": "a test command proves nothing, such as `true`, `echo`, or `sh -c true`",
            "tests.no_evidence": "no evidence for the head commit yet",
            "tests.evidence_invalid": "the evidence artifact could not be read (the adapter's `invalid` record)",
            "tests.evidence_schema": "the evidence does not validate against evidence.schema.json",
            "tests.evidence_other_head": "the evidence is for another head commit",
            "tests.evidence_other_base": "the evidence ran against another base commit",
            "tests.duplicate_result": "the evidence holds two results for one test name in one phase",
            "tests.no_result": "an applicable command has no result on head",
            "tests.command_mismatch": "the runner ran another command than the one declared",
            "tests.failed": "an applicable command did not pass on head",
            "tests.check_failed": "a required status check ended in failure, cancelled, timed_out, or action_required",
            "tests.check_waiting": "a required status check is still queued, running, or missing",
            "tests.check_skipped": "a required status check was skipped on head",
        },
    ),
    Rule(
        "red_green",
        "fail (warn in solo)",
        "on Spec-backed normal and major: every `new_behavior` command failed on base (a non-zero exit other than 126 or 127; "
        "a compile or import error counts) with the declared command, and a feat or fix change has one",
        "write the test first and see it fail on base",
        codes={
            "red_green.no_new_behavior": "a feat or fix Spec declares no `new_behavior` test command",
            "red_green.no_red_run": "a `new_behavior` command has no run against the base commit",
            "red_green.passes_on_base": "a `new_behavior` command passes on base, so it proves nothing new",
            "red_green.red_not_assertion": "the red run did not fail with a real exit code: a timeout, an error, or exit 126 or 127",
            "red_green.red_command_mismatch": "the red run used another command than the one declared",
        },
    ),
    Rule(
        "spec_approval",
        "pending or warn",
        "on the profile's routes, an eligible Approver (not an author, except under solo) approved the current Spec hash; each owner "
        "area the Spec touches has an approval from its owners; under `spec_approval_proof = require`, the approval names a commit that "
        'held only the Spec and its frozen files; on a local context under `gates.local_approvals = "signed"`, only approvals the '
        "adapter marked `verified` count (warn when one was dropped); with a `tenant`, an approval by another tenant's identity never counts (warn)",
        "`aidd hash specs/<ID>.md --comment` prints the line; a human posts it",
        codes={
            "spec_approval.missing": "no eligible Approver approved the current Spec hash",
            "spec_approval.owner_area": "an owner area the Spec touches has no Spec approval from its owners",
            "spec_approval.commit_required": "`spec_approval_proof = require`, and no approval names a commit holding only the Spec and its frozen files",
            "spec_approval.names_base": "an approval names the base commit, which proves no Spec commit",
            "spec_approval.after_implementation": "the approved commit already held implementation, so approval came after it began",
            "spec_approval.unsigned": 'locally under `local_approvals = "signed"`, a Spec approval without `verified: true` was dropped',
            "spec_approval.other_tenant": "the config names a `tenant`, and a Spec approval came from an identity qualified with another tenant; it never counts",
        },
    ),
    Rule(
        "merge_approval",
        "pending or warn",
        "as many eligible Approvers as the route requires (`gates.approvals`) approved the head commit; each owner area the diff touches "
        "has an approval from its owners; "
        "no Approver, specialist reviewer, or path owner's latest review requests changes; on a local context under "
        '`gates.local_approvals = "signed"`, only approvals the adapter marked `verified` count (warn when one was dropped); an agent '
        "account never approves, and its platform approval warns; with a `tenant`, an approval by another tenant's identity never counts (warn)",
        "a human approves the PR/MR on head",
        codes={
            "merge_approval.missing": "fewer eligible, cooled-off approvals on head than `gates.approvals` asks for the route",
            "merge_approval.owner_area": "an owner area the diff touches has no approval from its owners",
            "merge_approval.changes_requested": "an Approver, specialist reviewer, or path owner's latest review requests changes",
            "merge_approval.unsigned": 'locally under `local_approvals = "signed"`, an approval without `verified: true` was dropped',
            "merge_approval.other_tenant": "the config names a `tenant`, and an approval came from an identity qualified with another tenant; it never counts",
            "merge_approval.agent_approval": "an agent account (`identities.bots`, a baseline `agent_accounts` login such as Copilot's reviewer, a `[bot]` "
            "named for an agent) or a bot no pool names approved on the platform; it never counts, and the platform's own review count may",
        },
    ),
    Rule(
        "edited_comments",
        "warn",
        "no edited comment was ignored",
        "post a new comment instead of editing one",
        codes={"edited_comments.ignored": "an edited comment was ignored; approval commands in it do not count"},
    ),
    Rule(
        "specialist_review",
        "pending or fail",
        "major, and emergency when a protected path changes: `specialist_approvals` approvals on head from each pool the reasons name "
        "(`owners.reviewers`; an unbound pool falls back to `security`); under `specialist_spec_approval`, each pool also approved the Spec hash",
        "a member of each named pool approves",
        codes={
            "specialist_review.unbound": "a required specialist pool (and the `security` fallback) is not bound in `owners.reviewers`",
            "specialist_review.missing": "a required specialist pool has too few approvals on head",
            "specialist_review.spec_missing": "under `specialist_spec_approval`, a required pool has not approved the Spec hash",
        },
    ),
    Rule(
        "policy",
        "fail or warn",
        "Policy allows; a freeze passes only emergency; a required Policy is bound; unreachable is deny",
        "wait for the freeze to end, or bind `policy.command`",
        codes={
            "policy.required": "the profile requires a bound Policy command on this route, and none is bound",
            "policy.deny": "the Policy command returned deny",
            "policy.freeze": "a freeze is on and the route is not emergency",
            "policy.break_glass": "an emergency ships under a freeze",
            "policy.unreachable": "the Policy command did not answer, which is deny",
        },
    ),
    Rule(
        "policy:<rule>",
        "as reported",
        "each finding the Policy command reports",
        "what the finding says",
        codes={"policy:<rule>": "a finding the Policy command reported; its code is its rule, at the level it chose"},
    ),
    Rule(
        "emergency",
        "fail, pending, or warn",
        "the emergency block is complete; `review_due` falls within `emergency.review_sla_days` (default 2) of the day the change opened "
        "or its head was last pushed, whichever is later; the backfill Spec is committed with the same `review_due`; the commander is a "
        "human eligible Approver, not an author or agent, and approved the head",
        "fill the block, commit the backfill stub, and ask the commander",
        codes={
            "emergency.no_block": "route emergency without an emergency block",
            "emergency.review_due_invalid": "`review_due` is not a calendar date",
            "emergency.review_due_early": "`review_due` is before the day the change opened",
            "emergency.review_due_late": "`review_due` is further than `emergency.review_sla_days` from the day the change opened or was last pushed",
            "emergency.backfill_missing": "the backfill Spec is not in the head commit",
            "emergency.backfill_unparsable": "the backfill Spec does not parse",
            "emergency.backfill_mismatch": "the backfill is not an emergency Spec with the same `review_due`",
            "emergency.commander_is_agent": "the incident commander is an agent or bot account",
            "emergency.commander_is_author": "the incident commander is an author of the change",
            "emergency.commander_not_approver": "the incident commander is not an eligible Approver",
            "emergency.commander_pending": "the incident commander has not approved head",
            "emergency.would_be_major": "outside an emergency the repair would be major, so the specialist review still applies",
        },
    ),
    Rule(
        "observe",
        "fail",
        "the profile's routes carry an `observe` block",
        "add window, rollback_trigger, and a command or signals",
        codes={"observe.missing": "the profile's routes need an `observe` block, and the Spec or block has none"},
    ),
    Rule(
        "provenance",
        "fail or warn",
        "`assisted_by` is set whenever a commit names an agent: an `Assisted-by:` trailer, a `Co-authored-by:` agent (the baseline's "
        "`agent_coauthors`), or an author in `identities.bots`; under regulated, every non-merge commit carries a trailer "
        "(`Assisted-by: none` when no agent wrote it)",
        "amend the commits or the declaration",
        codes={
            "provenance.undeclared_agent": "a commit names an agent, but `assisted_by` is empty",
            "provenance.undeclared_trailer": "a commit trailer names an agent `assisted_by` does not list",
            "provenance.missing_trailer": "under regulated, a non-merge commit has no `Assisted-by` trailer",
            "provenance.no_agent_commit": "`assisted_by` is set, but no commit names an agent",
        },
    ),
    Rule(
        "standard_change",
        "fail",
        "the class exists and the profile allows it; paths, authors, and the line limit fit; every commit has a platform-verified signature",
        "use another route when it does not fit",
        codes={
            "standard_change.not_allowed": "the profile does not allow standard changes",
            "standard_change.unknown_class": "the block names a standard change class the config lacks",
            "standard_change.mismatch": "the change does not fit its class: paths, authors, line limit, or unsigned commits",
        },
    ),
    Rule("draft", "pending", "the PR/MR is not a draft", "mark it ready for review", codes={"draft.draft": "the PR/MR is a draft"}),
)

BY_NAME = {r.name: r for r in RULES}


def explain(name: str) -> str:
    r = BY_NAME.get(name)
    if r is None and name.startswith("policy:"):
        from .policy import RULE_NAME

        sub = name[len("policy:") :]
        if RULE_NAME.match(sub):
            r = Rule(name, "fail or warn", f"the custom policy rule {sub!r} holds", "fix the issue reported by the policy command")
    if r is None:
        raise LookupError(f"no rule {name!r}; one of {', '.join(BY_NAME)}")
    codes = "".join(f"\n    {code}: {meaning}" for code, meaning in r.codes.items())
    return f"{r.name} ({r.levels})\n  holds when: {r.holds}\n  to satisfy: {r.fix}" + (f"\n  codes:{codes}" if codes else "")
