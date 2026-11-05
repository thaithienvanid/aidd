"""Rule suggestions from the decision records, for `aidd risk --suggest`: each `ask` rule that a person answered yes
every time, at least MIN_ASKS times, for an action a person can undo. So a person may lower it toward the least asking
the risk allows. It only suggests: a person changes a rule, and that config edit asks too.

Three kinds of rule are never suggested, however many yeses they got:
- one that governs an action a person cannot undo (`irreversible: true` in its definition, such as a force-push, a
  deploy, or a message sent), including through a wildcard such as `db.*`;
- one at a person's own decision points (DECISION_POINTS): Spec approval, a Spec's revision, Merge approval, a push
  to the default branch, and an edit to the risk rules themselves, since lowering one would hand that decision away;
- a locked rule, which the project cannot change.
It counts only the records this clone wrote, never pulled ones, which are another's text. Even its own are the agent's
account, which nothing verifies, so a suggestion is a prompt for the person, never evidence.
"""

from __future__ import annotations

from aidd import records
from aidd.risk import commands
from aidd.risk.rules import Rule, RuleSet, _action_score, edit_level, winning_rule

MIN_ASKS = 10
# The rules at a person's own decision points, by (action, area, branch): never suggested, since lowering one hands
# that decision to the agent.
DECISION_POINTS = (
    ("spec.approve", None, None),
    ("spec.revise", None, None),
    ("pr.merge", None, None),
    ("git.push", None, "default"),
    ("code.edit", "risk_rules", None),
)


def _deciding_rule(rs: RuleSet, data: dict, default_branch: str | None) -> Rule | None:
    """The rule in force now that would ask the question this decision answered."""
    action = data["action"]
    covers: dict = data["covers"] if isinstance(data.get("covers"), dict) else {}
    paths = covers.get("paths")
    if action == "code.edit" and isinstance(paths, list) and paths and all(isinstance(p, str) for p in paths):
        return edit_level(rs, paths)[1]
    branch = covers.get("branch")
    # An ask about a branch is about the default branch or a shared one: a push to the agent's own branch never asks.
    branch_type = None if not isinstance(branch, str) else "default" if branch == default_branch else "shared"
    return winning_rule(rs, action, branch=branch_type if action.startswith("git.push") else None)


def rule_suggestions(rs: RuleSet, cwd: str = ".") -> dict:
    """`{suggestions, min_asks}`: each ask rule to consider lowering to `report`, with how many asks it got, every one
    accepted, and how many asks a suggestion needs."""
    found, _ = records.read_records(cwd, record_type="decision")
    pulled = records.pulled_ids(cwd)
    default_branch = commands._default_branch(cwd)
    tally: dict[tuple, dict] = {}
    for record in found:
        if record["id"] in pulled:
            continue
        data = record["data"]
        question = data.get("question") if isinstance(data.get("question"), dict) else {}
        answer = data.get("answer") if isinstance(data.get("answer"), dict) else {}
        if question.get("type") != "approval" or not isinstance(data.get("action"), str):
            continue
        rule = _deciding_rule(rs, data, default_branch)
        if rule is None or rule.level != "ask":
            continue
        entry = tally.setdefault(rule.selector, {"rule": rule, "asks": 0, "accepted": 0, "actions": set()})
        entry["asks"] += 1
        entry["accepted"] += answer.get("outcome") == "accept"
        entry["actions"].add(data["action"])
    out = []
    for entry in tally.values():
        rule = entry["rule"]
        governed = {a for a in rs.actions if _action_score(rule.action, a) is not None} | entry["actions"] | {rule.action}
        undoable = not any((rs.actions.get(a) or {}).get("irreversible") for a in governed)
        # A rule broader than a decision point decides it too: `git.push` with no branch covers the default branch.
        decision_point = any(
            _action_score(rule.action, a) is not None and rule.area in (None, area) and rule.branch in (None, branch) for a, area, branch in DECISION_POINTS
        )
        if entry["asks"] >= MIN_ASKS and entry["accepted"] == entry["asks"] and undoable and not decision_point and not rule.locked:
            out.append(
                {
                    "action": rule.action,
                    "area": rule.area,
                    "branch": rule.branch,
                    "role": rule.role,
                    "source": rule.source,
                    "asks": entry["asks"],
                    "level": "ask",
                    "consider": "report",
                }
            )
    return {"suggestions": sorted(out, key=lambda s: (-s["asks"], s["action"])), "min_asks": MIN_ASKS}
