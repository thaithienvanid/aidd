"""The checks `aidd validate` runs on the product scope: what one file of it owes, and what the files and the Intents owe each other.

One file owes its placeholders filled, its approver a person, and its approval current. The product scope owes each `serves`
an item of the right type that is not retired, each id kept for good, one shape, and an intent order that names Intents. An
Intent owes a `serves` once a product scope exists, and a warning says when it looks like several goals. Every finding names
its file and the next step. A finding with no prefix is an error, and `warning: ` and `note: ` start the others.
"""

from __future__ import annotations

import datetime as dt
import functools
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, resources, timestamps
from aidd.workitems import intent_checks, intent_paths, intents, product_approval, product_map, product_scope, repo_reads, status
from aidd.workitems.product_scope import MET, RETIRED, Item, ProductScope

WARNING, NOTE = "warning: ", "note: "
# The approval a file of the product scope carries, and the person its type names to decide it.
STAMPS = (product_approval.BY, product_approval.AT)
DECIDERS = {"brd": "sponsor", "intent-order": "owner"}
# The most fields or ids one finding names.
MAX_NAMED = 5


def shown(value: object) -> str:
    """A value a file holds, as a finding names it: on one line and short, because a file is another person's text."""
    return documents.one_line(str(value), 80)


def placeholders(data: object, where: str = "") -> list[str]:
    """The fields of front matter whose text holds a placeholder, as `objectives[0].metric.target`, in file order."""
    if isinstance(data, str):
        return [where] if status.PLACEHOLDER in data else []
    if isinstance(data, dict):
        return [p for k, v in data.items() for p in placeholders(v, f"{where}.{k}" if where else str(k))]
    if isinstance(data, list):
        return [p for n, v in enumerate(data) for p in placeholders(v, f"{where}[{n}]")]
    return []


def without_placeholder_errors(path: object, data: dict, found: list[str]) -> list[str]:
    """`found` without the schema errors of a field that still holds a placeholder: the finding for the placeholder names the
    field and the way out, so the date or the id the placeholder is not says nothing more."""
    held = [f"{path}: $.{h}: " for h in placeholders(data)]
    return [f for f in found if not f.startswith(tuple(held))]


def _only_a_reminder(data: dict, root: Path | None) -> bool:
    """Whether a placeholder is only a reminder: it is in the intent order, no BRD, PRD, or standing outcomes exist yet, and nobody
    approved the file. An upgrade seeds the order with the product owner still to name, and nothing there is approved."""
    if data.get("type") != product_scope.ORDER or data.get("approved_at") or root is None:
        return False
    product_dir = (repo_reads.config_at(root) or config.EMPTY).product_dir
    return not any(product_scope.read_file(root, intent_paths.product_file(t, product_dir), t) is not None for t in product_scope.HOLDING)


def _placeholder_error(path: object, data: dict, root: Path | None) -> list[str]:
    held = placeholders(data)
    if not held:
        return []
    shown = ", ".join(held[:MAX_NAMED]) + (f", and {len(held) - MAX_NAMED} more" if len(held) > MAX_NAMED else "")
    many = len(held) != 1
    said = f"{len(held)} field{'s' if many else ''} still hold{'' if many else 's'} TODO ({shown}): decide each with the person, then write the value. "
    if _only_a_reminder(data, root):
        return [f"{WARNING}{path}: {said}For `owner`, a person names who orders the Intents. It stays a warning until a BRD, a PRD, or standing outcomes exist"]
    return [f"{path}: {said}An agent never fills a number, a date, a target, or a name, so no gap is approved"]


def _people_findings(path: object, item_type: str, data: dict) -> list[str]:
    """Who approved and who decides: an agent is an error, another form a warning, and an approver who is not the person the
    file names as its decider (`sponsor`, `owner`) is a warning, because one person may hold both roles."""
    decider = DECIDERS.get(item_type)
    people = {f: data[f] for f in ("approved_by", decider) if f and isinstance(data.get(f), str) and status.PLACEHOLDER not in data[f]}
    out, problems = [], {f: config.approved_by_problem(who, f) for f, who in people.items()}
    for f, problem in problems.items():
        if problem:
            out.append(f"{path}: {problem}" if config.approver_is_agent(people[f]) else f"{WARNING}{path}: {problem}")
    if decider in people and "approved_by" in people and not any(problems.values()):
        if config.normalize_identity(people["approved_by"]) != config.normalize_identity(people[decider]):
            out.append(
                f"{WARNING}{path}: approved_by {shown(people['approved_by'])} is not the {decider}, {shown(people[decider])}. "
                f"If one person holds both roles, write that person in `{decider}`; otherwise ask the {decider} to approve it"
            )
    return out


def entries(data: dict) -> dict[str, dict]:
    """Each item of one file's front matter as its entry, by id."""
    return {e["id"]: e for key, _ in product_scope.LISTS for e in data.get(key) or [] if isinstance(e, dict) and isinstance(e.get("id"), str)}


def changes_since(then: dict, then_body: str, now: dict, now_body: str) -> list[str]:
    """What changed in one file since the version a person approved (`then`): the items added, removed, or changed, as
    phrases, a new order, and other text, which is any other front matter and the body. The approval's own fields never
    count. Empty when nothing did."""
    old, new = entries(then), entries(now)
    out = []
    # An item that left the file is the error of a gone id, or the other file's added item: said there, and not twice.
    for names, said in (
        ([i for i in new if i not in old], "added"),
        ([i for i in new if i in old and new[i] != old[i]], "changed"),
    ):
        if names:
            out.append(f"{', '.join(names)} {said}")
    if then.get("order") != now.get("order"):
        out.append("the order of the Intents changed")
    kept = {key for key, _ in product_scope.LISTS} | {"order", *STAMPS}
    if {k: v for k, v in then.items() if k not in kept} != {k: v for k, v in now.items() if k not in kept} or then_body.strip() != now_body.strip():
        out.append("its other text changed")
    return out


def _approval_findings(path: Path, data: dict, body: str, root: Path | None) -> list[str]:
    """A warning for a file whose approval no commit records, or that changed since the person approved it. A file never
    approved has nothing to compare, and `aidd status product` names the approval as the next step."""
    at = str(data.get("approved_at") or "")
    if not at:
        return []
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix() if root is not None else ""
    except ValueError:
        rel = ""
    then = product_approval.approved_text(root, rel, data) if root is not None and rel else None
    if then is None:
        return [
            f"{WARNING}{path}: no commit that changes only `approved_by` and `approved_at` carries an `Approved-by:` line of {shown(data.get('approved_by'))} "
            f"and `Approves: {command_names.quoted(rel) or '<this file>'}`, so aidd reads its approval of {shown(at)} as not approved. Ask the person to approve it "
            "(`product_scope.approve`), then commit `approved_by` and `approved_at` alone with those two lines"
        ]
    if not (changed := changes_since(then[0], then[1], data, body)):
        return []
    return [
        f"{WARNING}{path}: {'; '.join(changed)} since {shown(data.get('approved_by'))} approved it on {shown(at)}; ask the person to approve it again "
        "(`product_scope.approve`), then record the new `approved_by` and `approved_at`"
    ]


def file_findings(path: Path, text: str, data: dict, root: Path | None) -> list[str]:
    """The checks on one file of the product scope that need no other file: its placeholders, its people, and its approval."""
    if str(data.get("type")) not in (*product_scope.HOLDING, product_scope.ORDER):
        return []
    body = documents.split_front_matter(text, str(path))[1]
    return _placeholder_error(path, data, root) + _people_findings(path, str(data["type"]), data) + _approval_findings(path, data, body, root)


@dataclass(frozen=True)
class Repository:
    """What the product scope is checked against: the root, each Intent as (path, front matter), each Intent's derived
    status, the day, and the most slices one Intent lists (`limits.max_intent_specs`)."""

    root: Path
    intents: list[tuple[str, dict]]
    states: Mapping[str, str]
    today: dt.date
    max_specs: int


NAMES = {"objective": "an objective", "requirement": "a requirement", "outcome": "an outcome"}


def _target_finding(where: str, serves: str, target: Item | None, allowed: tuple[str, ...], live: bool = True) -> list[str]:
    """What is wrong with the item `serves` that the work at `where` (`path: id`) serves: no file holds it, it is of a type the
    work may not serve (`allowed`), or, while the work is `live`, it is retired (an error) or met (a note)."""
    serves = shown(serves)
    if target is None:
        return [f"{where} serves {serves}, which no file of the product scope holds: name an item that exists, or add {serves} where it belongs"]
    if target.type not in allowed:
        return [f"{where} serves {serves}, {NAMES[target.type]}, but it serves {' or '.join(NAMES[k] for k in allowed)}"]
    if live and target.status == RETIRED:
        return [f"{where} serves {serves}, which is retired: serve an item that is active, or ask a person to approve a change that keeps {serves}"]
    if live and target.status == MET:
        return [f"{NOTE}{where} serves {serves}, which is met: the work still counts, and a person may retire it or raise its target"]
    return []


def _item_findings(scope: ProductScope) -> list[str]:
    """Where items live comes first, because the step it names settles the rest: requirements live in one file, and the
    requirements of any other file are checked for nothing else, as they are to move; objectives live in the BRD when there is
    one. Then each requirement and product outcome serves an item of the right type that is not retired, and a requirement
    serves an objective wherever the product scope holds objectives."""
    out: list[str] = []
    has_brd = "brd" in scope.files
    holding = [f.path for f in scope.files.values() if f.type in product_scope.HOLDING and f.data.get("requirements")]
    if len(holding) > 1:
        out.append(
            f"{holding[-1]}: requirements are in {' and '.join(holding)}, and a product keeps them in one file: "
            f"move them into {holding[0]} (the BRD when there is one, else the PRD), then remove them from the other"
        )
    prd = scope.files.get("prd")
    if has_brd and prd is not None and prd.data.get("objectives"):
        brd = scope.files["brd"]
        beside = f"objectives are in both {brd.path} and {prd.path}" if brd.data.get("objectives") else "objectives are in the PRD, and the BRD holds none"
        out.append(f"{prd.path}: {beside}: with a BRD they live there, so move them into {brd.path}")
    has_objectives = any(i.type == "objective" for i in scope.items.values())
    for item in scope.items.values():
        path = product_scope.path_of(scope, item.id)
        if item.type == "requirement" and path in holding[1:]:
            continue
        if item.type == "requirement" and item.serves:
            out += _target_finding(f"{path}: {item.id}", item.serves, scope.items.get(item.serves), ("objective",))
        elif item.type == "requirement" and has_objectives:
            out.append(f"{path}: {item.id} serves nothing, and this product scope has objectives: add `serves: Objective-n` for the objective it serves")
        elif item.type == "outcome" and item.file_type == "prd" and item.serves:
            out += _target_finding(f"{path}: {item.id}", item.serves, scope.items.get(item.serves), ("requirement",) if has_brd else ("objective",))
        elif item.type == "outcome" and item.file_type == "prd" and has_brd:
            out.append(f"{path}: {item.id} serves nothing, and a BRD exists: add `serves: Requirement-n` for the requirement it brings about")
    return out


def _shape_findings(scope: ProductScope) -> list[str]:
    """One shape: the standing outcomes stand for a product with neither a BRD nor a PRD, and an id is held once."""
    out = []
    here = scope.files.get("standing-outcomes")
    if here is not None and (beside := [scope.files[t].path for t in ("brd", "prd") if t in scope.files]):
        out.append(
            f"{here.path}: standing outcomes stand for a product with neither a BRD nor a PRD, and {' and '.join(beside)} exists: "
            "move each outcome into the PRD, then remove this file"
        )
    out += [
        f"{second}: {i} is also in {first}; an id is held once in one product scope, so give one of them the next free number"
        for i, first, second in scope.repeated
    ]
    return out


def _gone_findings(scope: ProductScope, root: Path) -> list[str]:
    """An id that the last approved version of a file held is gone from every file: ids are never reused, so a person retires
    an item with a result, and never removes it. The last approved version comes from the file's history, never from the stamps
    it holds today, so removing them with the item hides nothing."""
    out = []
    for f in scope.files.values():
        then = product_approval.last_approved_text(root, f.path) if f.type in product_scope.HOLDING and f.readable else None
        if then is None:
            continue
        data = then[0]
        out += [
            f"{f.path}: {i} was in it when {shown(data.get('approved_by'))} approved it on {shown(data.get('approved_at'))}, and is gone: never remove an item. "
            f"Put {i} back, or retire it with a `results` entry whose decision is `retire`"
            for i in entries(data)
            if i not in scope.items
        ]
    return out


def _order_findings(scope: ProductScope, repo: Repository) -> list[str]:
    """The intent order names Intents only. It warns about an approved Intent it leaves out, and notes a closed one it still lists."""
    order = scope.files.get(product_scope.ORDER)
    if order is None or not order.readable:
        return []
    out, known = [], {str(d.get("id")) for _, d in repo.intents}
    for i in scope.order:
        if status.PLACEHOLDER in i:  # the placeholder finding leads
            continue
        if i not in known:
            out.append(f"{order.path}: {i} is no Intent in this worktree: merge the branch that holds it, or remove the line")
        elif repo.states.get(i) in status.INTENT_ENDED:
            out.append(f"{NOTE}{order.path}: {i} is {repo.states[i]} and still listed: a person may remove the line")
    left = [i for _, d in repo.intents if (i := str(d.get("id"))) not in scope.order and repo.states.get(i) == "approved"]
    if left:
        verb, them = ("is", "it") if len(left) == 1 else ("are", "them")
        out.append(f"{WARNING}{order.path}: {', '.join(left)} {verb} approved and not in the order, so shown last: ask the product owner where to place {them}")
    return out


@functools.cache
def default_review_days() -> int:
    """The days between results reviews when no intent order says: the schema's default."""
    return int(resources.load_json("product-scope.schema.json")["$defs"]["intent_order"]["properties"]["review_every_days"]["default"])


def size_warnings(path: str, data: dict, repo: Repository, cycle: int) -> list[str]:
    """The three facts that say an Intent may be several goals, from counts and dates only, each a warning that names its
    question: the slices it lists, its phases beside a `serves`, and the days it has stayed open since the approval,
    against the review cycle (`cycle`)."""
    iid, out = shown(data.get("id")), []
    if (n := len(intents.planned_spec_ids(data))) > repo.max_specs:
        out.append(
            f"{WARNING}{path}: {iid} lists {n} slices, more than {repo.max_specs}: is it one problem, or several goals? "
            "If several, split it so that each Intent serves one item and a person can agree to each alone"
        )
    if len(phases := intents.phases_of(data)) > 1 and data.get("serves"):
        out.append(
            f"{WARNING}{path}: {iid} has {len(phases)} phases and serves {shown(data['serves'])}: could a phase ship alone, so that a user would notice it? "
            "If so, make that phase its own Intent"
        )
    approved = timestamps.parse_date(intent_checks.approval_of(data)[1] or None)
    if approved is not None and (days := (repo.today - approved).days) >= cycle:
        out.append(
            f"{WARNING}{path}: {iid} was approved {days} days ago and is still open, as long as the {cycle}-day review cycle or longer: should it be live within one cycle? "
            "If not, it is probably several goals, so split it"
        )
    return out


def _intent_findings(scope: ProductScope, repo: Repository) -> list[str]:
    """Each Intent that is not closed serves an item once a product scope exists, and the item holds; a closed Intent keeps
    only the check of an id no file holds or of the wrong type. The size warnings follow, only with a BRD, a PRD, or standing outcomes."""
    order = scope.files.get(product_scope.ORDER)
    cycle = int(order.data.get("review_every_days") or default_review_days()) if order is not None and order.readable else default_review_days()
    allowed = product_map.carried_types(scope)
    name = " or ".join(f"{NAMES[t]} (`{t.capitalize()}-n`)" for t in allowed)
    out: list[str] = []
    for path, data in repo.intents:
        iid, serves = shown(data.get("id")), data.get("serves")
        ended = repo.states.get(str(data.get("id")), "draft") in status.INTENT_ENDED
        if serves is None and scope.exists and not ended:
            active = [i.id for i in scope.items.values() if i.status == product_scope.ACTIVE and i.type in allowed][:MAX_NAMED]
            out.append(
                f"{path}: {iid} serves nothing, and this repository has a product scope: add `serves` with {name}, and `success_criteria`."
                + (f" The active ones: {', '.join(active)}." if active else "")
            )
        elif isinstance(serves, str) and not scope.exists:
            out.append(f"{path}: {iid} serves {shown(serves)}, but this repository has no product scope: write one (`aidd new prd`), or remove `serves`")
        elif isinstance(serves, str) and scope.whole:
            out += _target_finding(f"{path}: {iid}", serves, scope.items.get(serves), allowed, live=not ended)
        if not ended and scope.exists:
            out += size_warnings(path, data, repo, cycle)
    return out


def scope_findings(scope: ProductScope, repo: Repository) -> list[str]:
    """What the product scope and the Intents owe each other, for `aidd validate` of the repository."""
    return [
        *(f.problems[0] for f in scope.files.values() if f.misfiled),
        *_shape_findings(scope),
        *(_item_findings(scope) if scope.whole else []),
        *_gone_findings(scope, repo.root),
        *_order_findings(scope, repo),
        *_intent_findings(scope, repo),
    ]
