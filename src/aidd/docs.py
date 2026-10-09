"""Generate the Markdown tables that restate schemas, so docs and schemas never drift.

A generated block sits between `<!-- aidd:gen NAME -->` and `<!-- aidd:end -->`.
`aidd gen-docs --check` fails when any block is stale.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import harnesses, model, resources, rulebook, schema
from .config import ROUTE_KEYS
from .util import md_cell

BLOCK = re.compile(r"(<!-- aidd:gen (\S+) -->\n)(.*?)(<!-- aidd:end -->)", re.S)
# A value inside a sentence, on one line: `<!-- aidd:gen count:roles -->14<!-- aidd:end -->`.
INLINE = re.compile(r"(<!-- aidd:gen ((?:count|mcp|list):\S+) -->)([^\n<]*)(<!-- aidd:end -->)")
# The schema node each `fields:<key>` block documents: a file, and the path inside it.
FIELD_SCHEMAS = {
    **{k: (f"{k}.schema.json", []) for k in ("spec", "change-request", "config", "evidence", "record", "epic", "initiative", "proposal")},
    **{k: ("spec.schema.json", ["$defs", k]) for k in ("task", "outcome", "triage", "doc", "flag", "experiment")},
    **{k: ("common.schema.json", ["$defs", k]) for k in ("relation", "risk", "tests", "test_command", "emergency", "observe")},
    **{
        f"config-{k}": ("config.schema.json", ["properties", k])
        for k in ("owners", "targets", "agents", "policy", "observe", "preview", "gates", "identities", "evidence", "emergency", "guard", "hooks", "autopilot")
    },
    **{f"config-{k}": ("config.schema.json", ["properties", k, "items"]) for k in ("extends", "risk_rules", "standard_changes", "standards")},
    "config-docs": ("config.schema.json", ["properties", "docs"]),
    "config-standards_policy": ("config.schema.json", ["properties", "standards_policy"]),
    "standard": ("standard.schema.json", []),
    "stack": ("stack.schema.json", []),
    "config-docs-rule": ("config.schema.json", ["$defs", "doc_rule"]),
    "config-owners-paths": ("config.schema.json", ["properties", "owners", "properties", "paths", "items"]),
    "config-agents-autonomy": ("config.schema.json", ["properties", "agents", "properties", "autonomy"]),
    "config-guard-held_commands": ("config.schema.json", ["properties", "guard", "properties", "held_commands", "items"]),
    "config-project": ("config.schema.json", ["properties", "project"]),
    "config-project-stack": ("config.schema.json", ["properties", "project", "properties", "stack"]),
    "config-project-budget": ("config.schema.json", ["properties", "project", "properties", "budget"]),
    "config-project-defaults": ("config.schema.json", ["properties", "project", "properties", "defaults"]),
    "config-project-compliance": ("config.schema.json", ["properties", "project", "properties", "compliance"]),
    "config-project-writing": ("config.schema.json", ["properties", "project", "properties", "writing"]),
    "config-project-rules": ("config.schema.json", ["$defs", "project_rule"]),
    "config-project-waivers": ("config.schema.json", ["$defs", "project_waiver"]),
}


def _table(head: str, rows) -> str:
    """A Markdown table: `head` is its header cells ("A | B"), each row a list of cell strings."""
    sep = "| " + " | ".join("---" for _ in head.split(" | ")) + " |"
    return "\n".join([f"| {head} |", sep, *(f"| {' | '.join(map(str, r))} |" for r in rows)])


def _node(schema_name: str, path: list[str]) -> dict:
    node = resources.load_json(schema_name)
    for p in path:
        node = node[p]
    return node


def _deref(s: dict, base: str) -> tuple[dict, str]:
    return schema._resolve(s["$ref"], base) if "$ref" in s else (s, base)


def _type(s: dict, base: str) -> str:
    if "$ref" in s:
        name = s["$ref"].rsplit("/", 1)[-1]
        target, tbase = _deref(s, base)
        if "enum" in target:
            return f"`{name}`"
        if target.get("type") == "object":
            return f"table (`{name}`)"
        return _type(target, tbase)
    if "allOf" in s:
        narrowed = [sub for sub in s["allOf"] if "enum" in sub]
        return _type(narrowed[-1] if narrowed else s["allOf"][0], base)
    if "const" in s:
        return f'`"{s["const"]}"`'
    if "enum" in s:
        return " \\| ".join(f"`{v}`" for v in s["enum"])
    t = s.get("type")
    if t == "array":
        return f"list of {_type(s.get('items', {}), base)}"
    if t == "object":
        return "table"
    if isinstance(t, list):
        return " or ".join(t)
    return t or "any"


def _conditions(sch: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for sub in sch.get("allOf", []):
        cond = sub.get("if", {})
        then = sub.get("then", {})
        props = cond.get("properties", {})
        if props and then.get("required"):
            label = "when " + " and ".join(f"{key} is `{spec.get('const')}`" for key, spec in props.items())
            if "not" in cond:
                label += f" and {cond['not'].get('required', ['?'])[0]} is absent"
            for r in then["required"]:
                out.setdefault(r, label)
        elif "not" in cond and then.get("required"):
            missing = cond["not"].get("required", ["?"])[0]
            for r in then["required"]:
                out[r] = f"when {missing} is absent"
    return out


def resolve(schema_name: str, path: list[str]) -> tuple[dict, str]:
    """The schema node at `path`, following `$ref` (also across files) until it is a real definition."""
    sch, base = _node(schema_name, path), schema_name
    for _ in range(16):
        if "$ref" not in sch:
            return sch, base
        sch, base = _deref(sch, base)
    raise ValueError(f"{schema_name} {'/'.join(path)}: $ref chain too deep")


def _field_rows(key: str) -> list[list[str]]:
    sch, base = resolve(*FIELD_SCHEMAS[key])
    required, conditional = set(sch.get("required", [])), _conditions(sch)
    rows = []
    for name, prop in sch.get("properties", {}).items():
        desc = prop.get("description") or _deref(prop, base)[0].get("description", "")
        rows.append([f"`{name}`", _type(prop, base), "yes" if name in required else conditional.get(name, "no"), desc.replace("|", "\\|")])
    return rows


def fields_table(key: str) -> str:
    """A schema's fields; `a~b` lists only the rows of `a` that `b` does not already show word for word."""
    key, _, less = key.partition("~")
    shown = _field_rows(less) if less else []
    return _table("Field | Type | Required | Meaning", [r for r in _field_rows(key) if r not in shown])


def vocab_table(name: str) -> str:
    """A vocabulary's tokens and meanings: a `$defs` entry of the common schema, or `proposal_status`."""
    d = _node("proposal.schema.json", ["properties", "status"]) if name == "proposal_status" else _node("common.schema.json", ["$defs", name])
    return _table("Token | Meaning", ([f"`{v}`", d.get("x-meanings", {}).get(v, "")] for v in d["enum"]))


_GATE_ROWS = [
    ("separation_of_duties", "Approvers must differ from the authors"),
    ("spec_approval_routes", "Spec approval on routes"),
    ("specialist_spec_approval", "Specialist pools also approve the Spec on major"),
    ("approvals", "Merge approvals per route"),
    ("specialist_approvals", "Approvals from each specialist pool on major"),
    ("cooloff_minutes", "Cool-off minutes before an approval counts"),
    ("policy_required_routes", "Bound Policy required on routes"),
    ("provenance", "AI provenance"),
    ("red_green", "Red-then-green proof for new behavior"),
    ("standard_changes", "Standard changes allowed"),
    ("observe_required_routes", "Observe block required on routes"),
    ("max_changed_lines", "Changed-line budget per route (standard: its class's own limit; emergency: none)"),
    ("unlinked_authors", "Commit authors with no platform account"),
    ("spec_approval_proof", "Spec approval proven before implementation"),
    ("approval_carry", "A Merge approval carries across a trivial rebase"),
    ("approval_carry_routes", "Routes on which it carries (never emergency)"),
    ("max_open_per_approver", "Open waits per Approver before `aidd list` warns (0: off; never gated)"),
    ("escalate_after_minutes", "Minutes before `aidd list` escalates a wait (0: off; never gated)"),
    ("max_in_progress_per_owner", "Specs in progress per owner before `aidd list` warns (0: off; never gated)"),
    ("max_in_progress_days", "Days in progress before `aidd list` flags a Spec as aging (0: off; never gated)"),
]
# What a gate no profile sets means while it stays unset: a queue limit a config may add.
_UNSET_GATES = {"max_in_progress_per_owner": "unset (off)", "max_in_progress_days": "unset (10)"}


def groups_table() -> str:
    """Each status group, with the Spec, Epic and Initiative, and proposal statuses in it, from the schemas' x-groups."""
    common = resources.load_json("common.schema.json")["$defs"]
    sources = [
        common["status"]["x-groups"],
        common["container_status"]["x-groups"],
        resources.load_json("proposal.schema.json")["properties"]["status"]["x-groups"],
    ]
    group = common["status_group"]
    rows = ([f"`{g}`", group["x-meanings"][g], *(", ".join(f"`{s}`" for s, x in src.items() if x == g) or "none" for src in sources)] for g in group["enum"])
    return _table("Group | Meaning | Spec | Epic and Initiative | Proposal", rows)


def _cell(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, list):
        return ", ".join(v) if v else "none"
    if isinstance(v, dict):
        # Every value, zeros too: `standard 0` says a standard change needs no approval; leaving it out read as if the
        # route did not exist. Routes in their order; a route the profile gives no value stays out, and the label says.
        keys = sorted(v, key=lambda k: (ROUTE_KEYS.index(k) if k in ROUTE_KEYS else len(ROUTE_KEYS), k))
        return ", ".join(f"{k} {v[k]}" for k in keys) if keys else "none"
    return str(v)


def profiles_table() -> str:
    data = resources.profiles()
    order = data["order"]
    return _table(
        "Gate | " + " | ".join(order),
        ([label, *(_cell(data["profiles"][p][key]) if key in data["profiles"][p] else _UNSET_GATES[key] for p in order)] for key, label in _GATE_ROWS),
    )


def _codes(xs: list[str]) -> str:
    return ", ".join(f"`{x}`" for x in xs) or "none"


def baseline_table() -> str:
    b = resources.baseline()
    protected = f"<details><summary>{len(b['protected_paths'])} paths</summary>{_codes(b['protected_paths'])}</details>"
    rows = [["protected (cannot be disabled)", "major", "none", protected, "none", "none; also every file a bound Policy or Observe command runs"]]
    rows += [
        [
            f"`{r['name']}`",
            r["route"],
            ", ".join(r["dimensions"]) or "none",
            _codes(r["paths"]),
            _codes(r.get("dependencies", [])),
            _codes(r.get("exclude", [])),
        ]
        for r in b["risk_rules"]
    ]
    return _table("Rule | Minimum route | Dimensions | Paths | Added dependencies | Excluded", rows)


def baseline_summary() -> str:
    """The built-in rules without their paths (`baseline:summary`), for the agent-facing routes reference: `aidd assess
    --paths` answers for a real path, so the agent never matches globs by hand."""
    b = resources.baseline()
    rows = [["protected (cannot be disabled)", "major", "none", str(len(b["protected_paths"])), "none"]]
    rows += [
        [f"`{r['name']}`", r["route"], ", ".join(r["dimensions"]) or "none", str(len(r["paths"])), _codes(r.get("dependencies", []))] for r in b["risk_rules"]
    ]
    return _table("Rule | Minimum route | Dimensions | Paths | Added dependencies", rows)


_PLACEHOLDERS = {
    "{specs_dir}": "the Specs folder",
    "{proposals_dir}": "the proposals folder",
    "{spec}": "the active Spec",
    "{tests}": "its test files",
    "{design}": "its design files",
    "{docs}": "its frozen docs",
    **{f"{{docs:{k}}}": f"its {k} docs" for k in model.DOC_KINDS},
    "{scope}": "the scope of its Tasks",
}


def role_writes(writes: list[str]) -> str:
    """A role's write area in words; its linked-doc kinds (`{docs:<kind>}`) as one phrase where the first one stands."""
    kinds = [w[len("{docs:") : -1] for w in writes if w.startswith("{docs:")]
    words = []
    for w in writes:
        if not w.startswith("{docs:"):
            words.append(_PLACEHOLDERS.get(w, f"`{w}`"))
        elif w[len("{docs:") : -1] == kinds[0]:
            words.append(f"its {_series(kinds, 'and')} docs")
    return ", ".join(words) or "nothing (read-only)"


def role_area(r: dict) -> str:
    """The write area with the Spec rule that also binds it: files that ship must sit inside the scope."""
    if r.get("in_scope"):
        if r["writes"] == ["{scope}"]:
            return "its Tasks' scope"
        specs = "the Specs folder, and " if "{specs_dir}" in r["writes"] else ""
        proposals = ", and the proposals folder" if "{proposals_dir}" in r["writes"] else ""
        rest = [w for w in r["writes"] if w not in ("{specs_dir}", "{proposals_dir}")]
        return f"{specs}{role_writes(rest)} inside the change's scope{proposals}"
    own = [w for w in r["writes"] if w in _PLACEHOLDERS]
    paths = [w for w in r["writes"] if w not in _PLACEHOLDERS]
    text = role_writes(own) if own else ""
    if paths:
        text += (", and " if text else "") + f"{role_writes(paths)} once a Task's scope covers them, after Spec approval"
    return text or role_writes([])


def role_reads(r: dict) -> str:
    """The artifacts a role acts on, by their short names: a nested bullet list, one artifact a line, so a long list
    never runs into one long sentence."""
    arts = resources.roles()["loop"]["artifacts"]
    return "\n".join(f"  - {arts[a]['name']}" for a in r["reads"])


def standard_note(s: dict, edition: str = "edition") -> str:
    """A registry entry's edition, with `emerging` when the registry marks it so, or "" when it has neither; `edition`
    names the field to print (`release` is the bare edition, without the publication date and notes)."""
    return "; ".join(x for x in (s.get(edition), "emerging" if s.get("maturity") == "emerging" else None) if x)


def standard_text(s: dict, edition: str = "edition") -> str:
    """`name (edition)` for a registry entry, as `standard_note` gives the edition, or the name alone without one."""
    note = standard_note(s, edition)
    return f"{s['name']} ({note})" if note else s["name"]


def standard_cells(s: dict) -> tuple[str, str, str]:
    """The name, the bare edition (or a dash), and `checked <date>` (or `reviewed <date>`) for an overview row, never
    the notes."""
    date = f"checked {s['checked']}" if s.get("checked") else f"reviewed {s['reviewed']}"
    return s["name"], s.get("release") or "—", date


def capabilities_text(x: dict) -> str:
    """What an extension can touch, in words: `network, runs commands`, or `read-only` when it touches nothing."""
    words = [c.replace("_", " ") for c in x["capabilities"]]
    if "telemetry" in x["capabilities"]:
        words[x["capabilities"].index("telemetry")] = "telemetry (" + ("can be turned off" if x["telemetry_opt_out"] else "always on") + ")"
    return ", ".join(words) or "read-only"


def role_standards_cells(stds: list[dict], full: bool = True) -> list[tuple[str, str]]:
    """A role's standards as (wording, edition) pairs, each document's edition printed once: a second use of one
    document has an empty edition.

    `full` prints the whole edition note (publication date and notes), as the reference tables do; an agent file
    carries the bare edition, and its note lives once, in docs/TEAM-REFERENCE.md.
    """
    seen: set[str] = set()
    out = []
    for s in stds:
        out.append((s["name"], "" if s["id"] in seen else standard_note(s, "edition" if full else "release")))
        seen.add(s["id"])
    return out


def role_standards_text(stds: list[dict], full: bool = True) -> list[str]:
    """A role's standards as `wording (edition)`, from `role_standards_cells`."""
    return [f"{name} ({note})" if note else name for name, note in role_standards_cells(stds, full)]


def loop_points(loop: dict, steps: list[str], gates: bool = False) -> list[str]:
    """`steps` in loop order, with `Implement` shown as `Implement ⟲ Verify` when both are there, and, with `gates`,
    each human approval placed after the step it follows."""
    out: list[str] = []
    for step in loop["steps"]:
        if step == "Verify" and "Verify" in steps and "Implement" in steps:
            out[-1] += " ⟲ Verify"
        elif step in steps:
            out.append(step)
        if gates and step in GATES:
            out.append(GATES[step][1])
    return out


def role_loop(r: dict) -> str:
    return f"{', '.join(r['steps'])} ({', '.join(r['lanes'])} lane{'s' if len(r['lanes']) > 1 else ''})"


def practice_names() -> list[str]:
    """The practice skills, in the order the roles first name them."""
    return list(dict.fromkeys(x for k in resources.roles()["order"] for x in resources.roles()["roles"][k]["practices"]))


def practice_front(name: str) -> dict:
    """The front matter of a practice skill: `name`, `description`, `checked`, and `steward` when set (both from `metadata`)."""
    text = (resources.data_dir("team") / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"practice skill {name!r} has no front matter")
    front: dict = {}
    for line in text[4 : text.index("\n---", 4)].splitlines():
        m = re.match(r"^\s*([\w-]+): (.+)$", line)
        if m:
            value = m.group(2).strip()
            front[m.group(1)] = json.loads(value) if value.startswith('"') else value
    if not {"name", "description", "checked"} <= set(front):
        raise ValueError(f"practice skill {name!r} needs name, description, and metadata.checked in its front matter")
    return front


def _subcommands() -> dict:
    """The CLI's subcommand parsers, by name, from the same builder `aidd` runs, in the order of its grouped help: a
    command group's actions by their full name (`record verify`)."""
    import argparse

    from . import cli

    def actions(parser) -> dict:
        return dict(next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices)

    top = actions(cli.build_parser())
    out: dict = {}
    for _, rows in cli.COMMAND_GROUPS:
        for name, _ in rows:
            nested = [a for a in top[name]._actions if isinstance(a, argparse._SubParsersAction)]
            out |= {f"{name} {sub}": p for sub, p in actions(top[name]).items()} if nested else {name: top[name]}
    return out


def _arg_text(a) -> str:
    """One argument as a reader types it: `[path]`, `--profile solo|team`, `--test COMMAND`, `--json`."""
    if not a.option_strings:
        name = "|".join(str(c) for c in a.choices) if a.choices else (a.metavar or a.dest)
        text = {"?": f"`[{name}]`", "*": f"`[{name} ...]`", "+": f"`{name} ...`"}.get(a.nargs, f"`{name}`")
        return text.replace("|", "\\|")
    flag = max(a.option_strings, key=len)
    if a.nargs == 0:
        text = f"`{flag}`"
    elif a.choices and not a.metavar:
        text = f"`{flag} {'|'.join(str(c) for c in a.choices)}`".replace("|", "\\|")
    else:
        value = a.metavar or a.dest.upper()
        text = f"`{flag} {value}{' ...' if a.nargs in ('+', '*') else ''}`"
    if a.nargs == "?":  # the flag alone is valid: its value is optional
        text = text.replace(" ", " [", 1)[:-1] + "]`"
    notes = []
    if a.required:
        notes.append("required")
    if a.nargs != 0 and a.default not in (None, "", [], False):
        notes.append(f"default `{a.default}`")
    if type(a).__name__ == "_AppendAction":
        notes.append("repeatable")
    return text + (f" ({', '.join(notes)})" if notes else "")


def cli_table() -> str:
    """Every command, its positional arguments, and every flag, from the argparse parser itself."""
    rows = []
    import argparse

    for name, sub in _subcommands().items():
        # A flag with help=SUPPRESS is in no table.
        args = [a for a in sub._actions if a.dest != "help" and a.help != argparse.SUPPRESS]
        positional = "".join(" " + _arg_text(a) for a in args if not a.option_strings)
        flags = ", ".join(_arg_text(a) for a in args if a.option_strings) or "none"
        rows.append([f"`{name}`{positional}", (sub.description or "").replace("|", "\\|"), flags])
    return _table("Command | What it does | Flags", rows)


def when_table() -> str:
    """Which command when, from cli.EVERYDAY, cli.WHEN, and cli.COMMAND_GROUPS: the everyday commands in the order of the
    loop, then every other command by its group, then the maintainer and harness commands `aidd --help` hides."""
    from . import cli

    rows: list[list[str]] = []
    for i, (form, _, when) in enumerate(cli.EVERYDAY):
        rows.append(["Every day" if i == 0 else "", form, when])
    for title in ("Now and then", cli.HIDDEN_GROUP):
        names = [n for t, group in cli.COMMAND_GROUPS for n, _ in group if (t == cli.HIDDEN_GROUP) == (title == cli.HIDDEN_GROUP) and n in cli.WHEN]
        for i, name in enumerate(names):
            rows.append([title if i == 0 else "", f"`aidd {name}{' <kind>' if name == 'new' else ''}`", cli.WHEN[name]])
    return _table("Use | Command | When", rows)


# The work items in one picture (README.md and METHOD §4): the deal, the goal, one change, and where a person's pick
# from an exploration is recorded (schemas/exploration.schema.json names the places), with a caption and the sentences
# that keep a proposal and an exploration apart. The containment arrows follow each schema's `parent`.
WORK_ITEMS = (
    "flowchart LR",
    '  Proposal["Proposal<br/><i>the deal</i>"]',
    '  Initiative["Initiative<br/><i>the goal</i>"]',
    '  Epic["Epic"]',
    '  Spec["Spec<br/><i>one change</i>"]',
    '  Task["Task"]',
    '  Exploration["Exploration<br/><i>the design</i>"]',
    '  Pick{{"a person picks"}}',
    '  ADR["ADR or DESIGN.md<br/><i>records why</i>"]',
    '  Proposal -->|"accepted"| Initiative --> Epic --> Spec --> Task',
    "  Exploration --> Pick",
    '  Pick -->|"Design section"| Spec',
    "  Pick --> ADR",
)
WORK_ITEMS_CAPTION = (
    "Proposal, Initiative, and Epic are optional. A team may start with a Spec (METHOD §4.7). "
    "The diagram shows only the planning items. METHOD §4 lists all the object kinds."
)
WORK_ITEMS_TEXT = (
    "A proposal is about the deal: should we take this work, for how much, and by when? "
    "Skip it when nobody outside the team must say yes. "
    "An exploration is about the design: which way to build one part. Skip it when the answer is obvious."
)


def work_items() -> str:
    return _mermaid([*WORK_ITEMS, HUMAN_CLASS, "  class Pick human"]) + "\n\n" + WORK_ITEMS_CAPTION + "\n\n" + WORK_ITEMS_TEXT


# Every environment variable aidd reads or sets, and who reads it. tests/test_docs_generation.py fails when
# src/aidd names an AIDD_* variable this table does not, so the contract cannot drift from the code.
ENV_VARS = (
    (
        "AIDD_MODE",
        "`aidd gate github` and `aidd gate gitlab`",
        '`enforce` when neither the base config\'s `mode` nor `--mode` sets one (the default either way): any job or pipeline can set an environment variable, so it can never relax the gate. On GitHub the reusable workflow passes its `mode` input as `--mode`; on GitLab only `mode = "advisory"` in the base config makes the gate advisory',
    ),
    ("AIDD_PROTECTED_BRANCHES", "`aidd gate github`", "extra protected bases besides the default branch, comma-separated, globs allowed"),
    (
        "AIDD_ORG_PRESET",
        "every command that loads the config (the gate, `test`, `doctor`, `validate`, the guard)",
        "path to an org preset file, applied as the root parent of the repository config",
    ),
    (
        "GITHUB_TOKEN",
        "`aidd gate github`, `aidd eval standards --online`",
        "the token for the GitHub API (the App installation token in the reusable workflow; for the online standards check, a read-only token sent to api.github.com alone)",
    ),
    ("AIDD_GITLAB_TOKEN", "`aidd gate gitlab`", "the token for the GitLab API (`read_api`; `api` with `--post-status`)"),
    ("AIDD_SPEC", "`aidd hook pre-tool`, `aidd mcp`", "the active Spec, when a branch changes more than one"),
    (
        "AIDD_HOOK_OFFLINE",
        "`aidd hook pre-tool`, the session hooks",
        "`1` makes the guard skip network fetches of `extends` parents, and the session hooks skip the doctor's network checks; "
        "the aidd plugin's hook and the session hooks set it",
    ),
    (
        "AIDD_HOOK_FAIL_CLOSED",
        "`aidd hook pre-tool`, the plugin's hook launcher",
        "`1` (the regulated managed settings set it) blocks when the guard cannot run or crashes, and denies a shell command it cannot parse",
    ),
    (
        "AIDD_HELPERS_MAY_WRITE",
        "`aidd hook pre-tool`",
        "`1`, in the environment Claude Code starts with, lets a subagent that is not an aidd-team role write; by default such a helper only reads",
    ),
    (
        "AIDD_AGENT",
        "`aidd approve`, `aidd ship`",
        "any value marks a shell started by an agent, so both refuse; set it in agent runners that set neither `CLAUDECODE` nor `CLAUDE_CODE_CHILD_SESSION` (Claude Code) nor `AI_AGENT`, which count the same",
    ),
    (
        "AIDD_OFFLINE",
        "`aidd init`, `aidd upgrade`, `aidd doctor`",
        "`1` keeps the CI files at the release tag instead of asking GitHub (`git ls-remote`) for the commit it names, when aidd runs from an installed wheel; "
        "it also skips the doctor's pin and branch-protection checks, which `aidd assess`, `aidd list`, and `aidd digest` run too",
    ),
    (
        "ORCA_PANE_KEY",
        "`aidd hook session-start`, `aidd hook stop`",
        "set by Orca in the terminals it manages; this, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT` means the hook runs inside Orca, "
        "so it puts `aidd assess` on the worktree's Orca card (`[hooks] orca_status`). The guard never reads any of them",
    ),
    ("ORCA_WORKTREE_ID", "`aidd hook session-start`, `aidd hook stop`", "set by Orca, like `ORCA_PANE_KEY`"),
    ("ORCA_AGENT_HOOK_PORT", "`aidd hook session-start`, `aidd hook stop`", "set by Orca, like `ORCA_PANE_KEY`"),
    ("ORCA_CLI_COMMAND", "`aidd hook session-start`, `aidd hook stop`", "set by Orca in managed WSL sessions: the Orca CLI to call instead of `orca`"),
    (
        "CLAUDE_CODE_DISABLE_ADVISOR_TOOL",
        "`aidd doctor --autopilot`",
        "Claude Code's own switch: `1` turns its advisor off, so the doctor says a configured `advisorModel` does not apply",
    ),
    ("AIDD_REF", "the one-line installer", "the release tag or commit to install, such as `v1.0.0`; `aidd upgrade` names it in its upgrade hint"),
    (
        "AIDD_INPUT_FILE",
        "your Policy command (set by the gate)",
        "path to a JSON file with `change_id`, `base_sha`, `head_sha`, `route`, `type`, `paths`, and `body`",
    ),
    ("AIDD_CHANGE_ID", "your Policy command (set by the gate)", "the PR/MR number, or the local ref"),
    ("AIDD_BASE_SHA", "your Policy command (set by the gate)", "the base commit"),
    ("AIDD_HEAD_SHA", "your Policy command (set by the gate)", "the head commit"),
    ("AIDD_ROUTE", "your Policy command (set by the gate)", "the route the gate will enforce: the declared route, raised to what the diff requires"),
    ("AIDD_REQUIRED_ROUTE", "your Policy command (set by the gate)", "the minimum route the changed paths, dimensions, and type require"),
    ("AIDD_TYPE", "your Policy command (set by the gate)", "the declared change type"),
    ("AIDD_CHANGED_PATHS_FILE", "your Policy command (set by the gate)", "path to a file listing the changed paths, one per line"),
    ("AIDD_SPEC_ID", "your Observe command (set by `aidd observe`)", "the Spec's `id`"),
    ("AIDD_WINDOW", "your Observe command (set by `aidd observe`)", "the Spec's `observe.window`"),
    ("AIDD_ROLLBACK_TRIGGER", "your Observe command (set by `aidd observe`)", "the Spec's `observe.rollback_trigger`"),
)


def env_table() -> str:
    from .util import SECRET_ENV

    table = _table("Variable | Read by | Meaning", ([f"`{name}`", who, meaning] for name, who, meaning in ENV_VARS))
    return table + f"\n\nStripped from the environment of every test, Policy, and Observe command: {_codes(list(SECRET_ENV))}."


def _source_root() -> Path:
    root = resources.repo_root()
    if root is None:
        raise RuntimeError("counts of examples and evals need the aidd source checkout")
    return root


def count(name: str) -> int:
    """A number the docs state, counted from the data that defines it, so prose cannot drift."""
    from . import evals

    counters = {
        "harnesses": lambda: len(harnesses.HARNESSES),
        "roles": lambda: len(resources.roles()["order"]),
        "packs": lambda: len(resources.roles()["domains"]),
        "practices": lambda: len(practice_names()),
        "commands": lambda: len(team_commands()),
        "types": lambda: len(_node("common.schema.json", ["$defs", "type"])["enum"]),
        "dimensions": lambda: len(_node("common.schema.json", ["$defs", "dimension"])["enum"]),
        "examples": lambda: sum(1 for p in (_source_root() / "examples").iterdir() if (p / "context.json").is_file()),
        "mutations": lambda: len(list((_source_root() / "examples").glob("*/mutations/*.json"))),
        "routing-scenarios": lambda: len(evals.load_scenarios(_source_root() / "evals" / "routing")),
        "role-scenarios": lambda: len(evals.load_scenarios(_source_root() / "evals" / "roles")),
    }
    if name not in counters:
        raise KeyError(f"unknown count {name!r}")
    return counters[name]()


def harnesses_summary() -> str:
    """The README's short agent table. It says which pointer files init creates and which it only appends to."""
    hs = harnesses.HARNESSES
    agents_md = [h.label for h in hs.values() if not h.pointer and h.key != "claude-code"]
    created = [f"{h.label} (`{h.pointer}`)" for h in hs.values() if h.pointer and not h.only_if_present and h.key != "claude-code"]
    appended = [f"{h.label} (`{h.pointer}`)" for h in hs.values() if h.pointer and h.only_if_present and h.key != "claude-code"]
    md = harnesses.AGENTS_MD
    rows = [
        ["Claude Code", hs["claude-code"].wiring, hs["claude-code"].you],
        [
            ", ".join(agents_md),
            f"vendors the skill in `.agents/skills/aidd/` and points `{md}` at it; `--team` adds a short roles section to `{md}`, plus native agent "
            "files for Codex, Copilot, OpenCode, and Kiro; outside Claude Code the team is advisory",
            "nothing",
        ],
    ]
    if created:
        rows.append([", ".join(created), "the same, plus a pointer in the agent's own instruction file, which init creates", "nothing"])
    if appended:
        own = "the same, and appends the pointer to the agent's own instruction file only when that file already exists"
        rows.append([", ".join(appended), own, "nothing, except Aider: `read: CONVENTIONS.md` in `.aider.conf.yml`"])
    rows.append(["Anything else", f"`{md}` and `.agents/skills/aidd/`", f"tell the agent to read `{md}`"])
    gemini = "Gemini CLI was retired on June 18, 2026 for most users, who moved to the Antigravity CLI; it still serves some paid licenses ([details](docs/INSTALL.md#your-coding-agent))."
    notes = [gemini] if "gemini" in hs else []
    return "\n\n".join([_table("Your agent | What `aidd init` does | What you do", rows), *notes, harnesses.PLUGIN_NOTE])


def example_cases(root: Path) -> list[dict]:
    """Every numbered case under `root`/examples, in order, with its expectation and its mutation count. Each case
    states its `title` and `summary` in its expected.json, so the examples/README.md table cannot drift from the cases."""
    out = []
    base = root / "examples"
    for case in sorted(p for p in base.iterdir() if (p / "expected.json").is_file()) if base.is_dir() else []:
        expected = json.loads((case / "expected.json").read_text(encoding="utf-8"))
        mutations = case / "mutations"
        n = len(list(mutations.glob("*.json"))) if mutations.is_dir() else 0
        out.append(
            {"name": case.name, "title": expected.get("title", ""), "summary": expected.get("summary", ""), "decision": expected["decision"], "mutations": n}
        )
    return out


def examples_table(root: Path) -> str:
    rows = ([f"[`{c['name']}`]({c['name']}/)", md_cell(c["title"]), c["decision"], md_cell(c["summary"]), c["mutations"]] for c in example_cases(root))
    return _table("Case | Title | Decision | What it shows | Mutations", rows)


def _series(items: list[str], conj: str) -> str:
    """`a, b, and c` (or `a and b`): items as one phrase."""
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f", {conj} {items[-1]}" if len(items) > 1 else items[0]


# Where an agent file finds its role's standards and practice skills: the team skill's roles reference in the plugin.
# `aidd init --team` installs no plugin, so it writes the reference to the repository and points there instead.
ROLE_REFERENCE = "the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`)"


def role_block(key: str) -> str:
    """One role's facts in its agent file (`role:<key>`): who it is, when it starts and stops, what it may write, and
    the loop-contract rules that bind it (the whole contract is rendered once, in the team skill's roles reference).
    Its standards, practice skills, and extensions are needed for some Tasks only, so they sit in its section of the
    roles reference (`roles:by-role`), and the agent file carries a one-line pointer to it."""
    r = resources.roles()["roles"][key]
    contract = "".join(f"\n  {i}. {x}" for i, x in enumerate(resources.contract_for(key), 1))
    # The hard rules in brief, for every role: a role that does not preload the aidd skill still keeps them.
    digest = "".join(f"\n  {i}. {x}" for i, x in enumerate(resources.digest_for(key), 1))
    rulebook = (
        "The aidd skill, preloaded, is the rulebook."
        if preloads_core(key)
        else "The aidd skill (`aidd:aidd`; load it with `Skill` for a rule not here) is the rulebook."
    )
    return (
        f"You are the **{key}** of an AIDD delivery team. {rulebook} Prefer the `aidd` MCP tools.\n\n"
        f"- **Hard rules (in brief):**{digest}\n"
        f"- **Loop steps:** {role_loop(r)}\n- **Starts when:** {r['starts_when']}\n- **Done when:** {r['done_when']}\n"
        f"- **Does:** {r['does']}\n"
        f"- **Reads:**\n{role_reads(r)}\n"
        f"- **May write:** {role_area(r)}\n- **Hands off:** {r['hands_off']}\n"
        f"- **Model tier:** `{r['tier']}`\n"
        + "".join(
            f"- **Covers for:** the `{other}` where it is not installed: you also do its work, as its section of {ROLE_REFERENCE} says\n"
            for other in resources.roles()["order"]
            if resources.roles()["roles"][other].get("fallback") == key
        )
        + f"- **Loop contract:**{contract}\n"
        f"- **Standards and practice skills:** {ROLE_REFERENCE}, section `{key}`."
    )


def role_sections() -> str:
    """Each role's standards, practice skills, and extensions (`roles:by-role`), one section per role: an agent file
    points here instead of carrying lists it needs for some Tasks only. The standards are a table, one row each with
    its edition, because a wording and its edition note together run far past one readable sentence."""
    data = resources.roles()
    out = []
    for key in data["order"]:
        r = data["roles"][key]
        standards = _table("Standards applied | Edition", ([name, note or "—"] for name, note in role_standards_cells(r.get("standards", []))))
        # Names only: the harness lists every skill with its description.
        practices = ", ".join(f"`aidd-team:{x}`" for x in r["practices"]) or "none listed; this role works from its standards and the domain packs"
        lines = [
            f"### {key}",
            "",
            standards,
            "",
            f"- **Practice skills (`Skill`, two per Task at most):** {practices}.",
        ]
        listed = [x for x in dict.fromkeys([*r["practices"], *r.get("preload", [])]) if open_choices_placement(x) == "reference"]
        if listed:
            where = ", ".join(f"`aidd-team:{x}` (its `references/open-choices.md`)" for x in listed)
            lines.append(f"- **Open choices:** {where}. Use aidd's default until a `[[standards]]` entry fills one.")
        if r.get("extends"):
            names = ", ".join(x["name"] for x in r["extends"])
            lines.append(f"- **Extensions:** {names}. Use one only when the project already has it connected, verified, and pinned.")
        out.append("\n".join(lines))
    # A pack no role lists, whose open choices sit in a reference: the pack's own References section links it too.
    listed_by_roles = {x for r in data["roles"].values() for x in [*r["practices"], *r.get("preload", [])]}
    packs_ = [d["slug"] for d in data["domains"] if d["slug"] not in listed_by_roles and open_choices_placement(d["slug"]) == "reference"]
    if packs_:
        where = ", ".join(f"`aidd-team:{x}` (its `references/open-choices.md`)" for x in packs_)
        out.append(f"### Domain packs\n\n- **Open choices:** {where}. Use aidd's default until a `[[standards]]` entry fills one.")
    return "\n\n".join(out)


def lead_block() -> str:
    """The lead's rules (`roles:lead`), in every command: MODELS becomes each tier's model on the plugin's harness."""
    models = resources.MODELS_BY_HARNESS[resources.PLUGIN_HARNESS]
    named = ", ".join(f"`{m}` for {t}" for t, m in models.items())
    rules = "\n".join(f"{i}. {x.replace('MODELS', named)}" for i, x in enumerate(resources.roles()["loop"]["lead"], 1))
    return f"**You are the lead.** You run this command and the roles do its work:\n\n{rules}"


def contract_block() -> str:
    """The whole loop contract once (`roles:contract`), each rule with the roles it binds; an agent file carries only its own."""
    data = resources.roles()
    loop, order = data["loop"], data["order"]
    lines = []
    for i, (x, scope) in enumerate(zip(loop["contract"], loop["contract_applies_to"], strict=True), 1):
        who = "every role" if scope is None else _roles_text([k for k in order if x in resources.contract_for(k)], order, code=True)
        lines.append(f"{i}. {x} *(binds: {who})*")
    return "\n".join(lines)


def tiers_table() -> str:
    """Each model tier (`roles:tiers`): what it is for and its model per harness. Which role sits in which tier is the
    reference's `roles:models` table."""
    harness_names = [harnesses.HARNESSES[h].label if h in harnesses.HARNESSES else h for h in resources.MODELS_BY_HARNESS]
    rows = [[f"`{tier}`", meaning, *(f"`{m[tier]}`" for m in resources.MODELS_BY_HARNESS.values())] for tier, meaning in resources.TIER_MEANING.items()]
    return _table("Tier | For | " + " | ".join(harness_names), rows)


def capabilities_table() -> str:
    caps = resources.roles()["loop"]["capabilities"]
    counts = {k: sum(1 for c in caps["processes"] if c["coverage"] == k) for k in ("agents", "agents, a person decides", "people")}
    summary = (
        f"All {len(caps['processes'])} processes of {caps['standard']}:\n\n- {counts['agents']} run by agents under the gate\n"
        f"- {counts['agents, a person decides']} run by agents with a person deciding\n- {counts['people']} kept by people"
    )
    rows = ([c["group"], c["process"], ", ".join(f"`{b}`" for b in c["by"]) or "people", c["coverage"], c["how"]] for c in caps["processes"])
    return summary + "\n\n" + _table("Group | Process | Covered by | Who acts | How", rows)


def _roles_text(names: list[str], order: list[str], code: bool = False) -> str:
    """Role keys (or steps) as a list, or, when they are most of the roles, as `every role but ...`: a long list of role
    keys reads like a hand-kept roster that drifts, and says less than the few it leaves out."""
    fmt = (lambda k: f"`{k}`") if code else (lambda k: k)  # noqa: E731
    if set(names) <= set(order) and len(names) > len(order) / 2:
        return "every role but " + ", ".join(fmt(k) for k in order if k not in names)
    return ", ".join(fmt(k) for k in names)


def loop_tables() -> str:
    data = resources.roles()
    loop, order, roles = data["loop"], data["order"], data["roles"]
    marks = ([step, *("●" if step in roles[k]["steps"] else "" for k in order)] for step in loop["steps"])
    steps = _table("Step | " + " | ".join(f"`{k}`" for k in order), marks)
    when = _table("Role | Starts when | Done when", ([f"`{k}`", roles[k]["starts_when"], roles[k]["done_when"]] for k in order))
    contract = [
        f"{i}. {x}" + ("" if s is None else f" *(applies to: {_roles_text(s, order)})*")
        for i, (x, s) in enumerate(zip(loop["contract"], loop["contract_applies_to"], strict=True), 1)
    ]
    return "\n\n".join([steps, when, "Every role keeps the loop contract; a rule that names roles or steps binds only those:", "\n".join(contract)])


def loops_text() -> str:
    loop = resources.roles()["loop"]
    lo = loop["loops"]
    outer, inner = ", ".join(loop_points(loop, lo["outer_steps"], gates=True)), ", ".join(loop_points(loop, lo["inner_steps"]))
    who = [
        ["Outer", "a human: by approval at Spec approval and Merge approval, by recorded agreement for Plan, Ship, and Learn", outer],
        ["Inner", "the agent: it drafts the contract in Specify, then works inside it once Spec approval freezes it", inner],
    ]
    return "\n\n".join(
        [
            f"*Loop contract version {loop['version']}: a change that adds, removes, or reorders a step, an approval, or a lane bumps its major number.*",
            f"**The way in.** {loop['entry']}",
            f"**Outer loop — human strategy and governance.** {lo['outer']}",
            f"**Inner loop — autonomous agentic execution.** {lo['inner']}",
            f"**What crosses between them.** {lo['boundary']}",
            _table("Loop | Who decides | Steps", who),
            "Control passes at the two approvals on machine-checkable evidence, and at Plan, Ship, and Learn on a recorded human decision:",
            "\n".join(f"- {g}" for g in lo["gates"]),
            "**Human feedback.** A person sends work back on these paths, drawn dashed in the loop diagram; each is a normal part of the loop, not a failure:",
            "\n".join(f"- **{f['from']} → {f['to']}** ({f['when']}): {f['note']}" for f in lo["feedback"]),
        ]
    )


def roles_table(name: str) -> str:
    """The `roles:*` reference tables, one row per role, domain, extension, flow, or handoff; `roles:flows:when` says
    when a person picks each command."""
    data = resources.roles()
    order, roles, loop = data["order"], data["roles"], data["loop"]
    if name == "roles":
        return _table(
            "Role | Loop steps | Industry name | May write | Hands off",
            ([f"`{k}`", role_loop(roles[k]), roles[k]["industry"], role_area(roles[k]), roles[k]["hands_off"]] for k in order),
        )
    if name == "roles:models":
        models = resources.MODELS_BY_HARNESS
        tiers = {k: roles[k]["tier"] for k in order}
        rows = [[f"`{k}`", f"`{t}`", *(f"`{m.get(t, '—')}`" for m in models.values()), roles[k]["tier_reason"]] for k, t in tiers.items()]
        return _table("Role | Tier | " + " | ".join(models) + " | Why", rows)
    if name == "roles:practices":
        rows = []
        for x in practice_names():
            front = practice_front(x)
            who = ", ".join(f"`{k}`" for k in order if x in roles[k]["practices"])
            rows.append([f"`aidd-team:{x}`", front["description"].removeprefix("Practice skill: "), who, front["checked"]])
        return _table("Practice skill | Does | Roles that load it | Checked", rows)
    if name == "roles:standards":
        return _table("Role | Standards applied", ([f"`{k}`", "; ".join(role_standards_text(roles[k].get("standards", [])))] for k in order))
    if name == "roles:domains":
        # An overview, one row per standard: the name, the bare edition, and the date. The notes, caveats, and sources
        # live in each pack. A domain's own cells fill only its first row.
        return _table(
            "Domain | Pack | When the change touches | Standard | Edition | Checked",
            (
                [*((x["name"], f"`aidd-team:{x['slug']}`", x["signal"]) if i == 0 else ("", "", "")), *standard_cells(s)]
                for x in data["domains"]
                for i, s in enumerate(x["standards"])
            ),
        )
    if name == "roles:extends":
        rows = []
        for k in order:
            for x in roles[k].get("extends", []):
                kind = x["kind"] + (", emerging" if x.get("maturity") == "emerging" else "")
                source = f"<{x['source']}>" + (f" (listed in <{x['listed_in']}>)" if x.get("listed_in") else "")
                license = x.get("license", "—") + (f" ({x['license_note']})" if x.get("license_note") else "")
                rows.append([f"`{k}`", x["name"], kind, x["tier"], capabilities_text(x), x["adds"], source, license, x.get("pin", "—")])
        return _table("Role | Extension | Kind | Tier | Can | Adds | Source | License | Pin", rows)
    if name == "roles:flows":
        rows = []
        for f in loop["flows"]:
            runs = " then ".join(", ".join(f"`{r}`" for r in g) for g in f["runs"])
            rows.append([f"`/aidd-team:{f['command']}`", ", ".join(f["steps"]), ", ".join(f["lanes"]), runs, f["stops_at"]])
        return _table("Command | Loop steps | Lanes | Runs, in order (a group runs in parallel) | Stops at", rows)
    if name == "roles:flows:when":
        rows = [[f"`/aidd-team:{f['command']}`", f["when"], f["stops_at"]] for f in loop["flows"]]
        if "autopilot" in loop:
            a = loop["autopilot"]
            rows.append([f"`/aidd-team:{a['command']}` (experimental)", a["when"], a["stops_at"]])
        return _table("Command | When | Stops at", rows)
    if name == "roles:handoffs":
        arts = loop["artifacts"]
        party = lambda x: f"`{x}`" if x in roles else x  # noqa: E731
        rows = []
        for h in loop["handoffs"]:
            where = "; ".join(f"{arts[a]['name']}: {arts[a]['where']}" for a in h["artifact"])
            rows.append([", ".join(map(party, h["from"])), ", ".join(map(party, h["to"])), h["through"], where, h["note"]])
        return _table("From | To | Through | Artifact | The note adds", rows)
    raise KeyError(f"unknown generated block {name!r}")


def _examples_root() -> Path:
    root = resources.repo_root()
    if root is None:
        raise LookupError("the examples/ case table is generated from a source checkout")
    return root


def inline_list(name: str) -> str:
    """A list inside a sentence: `list:team-commands` names every flow's command, the first one in full."""
    if name != "team-commands":
        raise KeyError(name)
    commands = team_commands()
    return ", ".join([f"`/aidd-team:{commands[0]}`", *(f"`{c}`" for c in commands[1:])])


def team_commands() -> list[str]:
    """Every aidd-team command: one per flow, then the experimental autopilot, which runs the flow `aidd autopilot next` names."""
    loop = resources.roles()["loop"]
    return [f["command"] for f in loop["flows"]] + ([loop["autopilot"]["command"]] if "autopilot" in loop else [])


def render(name: str) -> str:
    from . import mcp

    kind, _, arg = name.partition(":")
    prefixed = {
        "fields": fields_table,
        "count": lambda x: str(count(x)),
        "list": inline_list,
        "vocab": vocab_table,
        "role": role_block,
        "practice": practice_standards,
    }
    if kind in prefixed:
        return prefixed[kind](arg)
    blocks = {
        "examples:cases": lambda: examples_table(_examples_root()),
        "mcp:revisions": lambda: _series(list(mcp.SUPPORTED), "and"),
        "mcp:latest": lambda: mcp.PROTOCOL,
        "cli:commands": cli_table,
        "cli:when": when_table,
        "workitems": work_items,
        "cli:env": env_table,
        "profiles": profiles_table,
        "profiles:carry": lambda: _table(
            "Profile | A Merge approval carries across a trivial rebase | On routes",
            (
                [p, _cell(g["approval_carry"]), _cell(g["approval_carry_routes"] if g["approval_carry"] != "none" else [])]
                for p, g in ((p, resources.profiles()["profiles"][p]) for p in resources.profiles()["order"])
            ),
        ),
        "status:groups": groups_table,
        "baseline": baseline_table,
        "baseline:summary": baseline_summary,
        "roles:capabilities": capabilities_table,
        "roles:commands": lambda: (
            "- **Commands:** "
            + ", ".join(f"`/aidd-team:{f['command']}`" for f in resources.roles()["loop"]["flows"])
            + "; one per flow in the registry, each running its roles in order and stopping where a person decides. "
            + "`/aidd-team:autopilot` (experimental) runs those flows between your decisions, one `aidd autopilot next` action at a time."
        ),
        "roles:loop": loop_tables,
        "roles:lead": lead_block,
        "roles:contract": contract_block,
        "roles:by-role": role_sections,
        "roles:preloaded": preloaded_sections,
        "roles:tiers": tiers_table,
        "roles:loops": loops_text,
        "roles:loop:diagram": loop_diagram,
        "roles:flows:diagram": flows_diagram,
        "autopilot:steps": autopilot_steps_table,
        "roles:handoffs:diagram": handoffs_diagram,
        "harnesses": harnesses.table,
        "standards:open-choices": lambda: _standards().catalog_choices(),
        "standards:library": lambda: _standards().catalog_library(),
        "standards:stacks": lambda: _standards().catalog_stacks(),
        "harnesses:summary": harnesses_summary,
        "rules:method": lambda: _table("Rule | Level on miss | Holds when", ([f"`{r.name}`", r.levels, r.holds] for r in rulebook.RULES)),
        "rules:skill": lambda: _table("Rule | Holds when | How you satisfy it", ([f"`{r.name}`", r.holds, r.fix] for r in rulebook.RULES)),
        "rules:codes": lambda: _table(
            "Code | Rule | Fires when",
            ([f"`{code}`", f"`{r.name}`", meaning.replace("|", "\\|")] for r in rulebook.RULES for code, meaning in sorted(r.codes.items())),
        ),
    }
    if name in blocks:
        return blocks[name]()
    return roles_table(name)


def autopilot_steps_table() -> str:
    """The step-code contract (experimental): every code the engine can emit, who takes it, and the flow `aidd autopilot next`
    runs for it, from nextstep.STEP_CODES, autopilot.AUTOPILOT_CODES, and each flow's `starts_on`."""
    from . import autopilot

    flows = autopilot.flow_map()
    rows = (
        [f"`{code}`", who, f"`/aidd-team:{flows[code]}`" if code in flows else "none: a person's step"] for code, who in sorted(autopilot.contract().items())
    )
    return _table("Step code | Who takes it | The flow `aidd autopilot next` runs", rows)


def _mermaid(lines: list[str]) -> str:
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def _label(text: str, width: int | None = None) -> str:
    """Text inside a quoted Mermaid label. Backticks go (entity codes render inconsistently), double quotes become
    single ones, and a `width` breaks the text into lines at word boundaries so a node stays narrow."""
    text = text.replace("`", "").replace('"', "'")
    if not width:
        return text
    lines: list[str] = []
    for word in text.split():
        if lines and len(lines[-1]) + 1 + len(word) <= width:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return "<br/>".join(lines)


# One look for every place a person decides, readable on GitHub's light and dark themes alike: an amber fill with
# dark text set explicitly. Everything else keeps the viewer's theme, so it follows light or dark by itself.
HUMAN_CLASS = "  classDef human fill:#fde68a,stroke:#b45309,stroke-width:2px,color:#1c1917"


def _node_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", text)


# Node ids are single words; Mermaid reads a space as the end of the id, and GitHub then renders nothing.
GATES = {
    "Specify": ("SpecApproval", "Spec approval", "a human approves the Spec and its tests"),
    "Review": ("MergeApproval", "Merge approval", "a human approves the head commit"),
}


def _wrap(words: list[str], width: int = 26) -> str:
    """Join words with commas, breaking the line (`<br/>`) before one would pass `width` characters, short enough
    that Mermaid never wraps a line itself and splits a hyphenated role name."""
    rows: list[str] = []
    for word in words:
        if rows and len(rows[-1]) + len(word) + 2 <= width:
            rows[-1] += ", " + word
        else:
            rows.append(word)
    return ",<br/>".join(rows)


# The loop in three rows, read top to bottom, so it stays narrow enough to review on a page. Every change enters by
# its route, which `aidd assess` shows before the first edit; the lane follows from it: the fast and emergency lanes skip
# Plan and Specify and start at Implement.
LOOP_ROWS = (
    ("before", "Before any code: the fast lane skips to Implement", ("Plan", "Specify")),
    ("build", "Build and prove", ("Implement", "Verify", "Review")),
    ("run", "Ship and learn", ("Ship", "Learn")),
)

# The inner loop's own way back, drawn solid: a red test or a mismatch the Verifier finds returns the head to Implement.
VERIFY_BACK = ("Verify", "Implement", "red, or a mismatch")

# Human feedback paths are dashed, in an amber that reads on GitHub's light and dark themes alike: the same family as
# the human decision nodes, dark enough on white and light enough on near-black.
FEEDBACK_STYLE = "stroke:#d97706,stroke-width:2px,stroke-dasharray:6 4"


def _point_id(point: str) -> str:
    """The node id of a loop step, or of one of the two human approvals."""
    return next((gate for gate, name, _ in GATES.values() if name == point), _node_id(point))


def loop_diagram() -> str:
    """The loop with the roles of each step, the two human approvals, and the human feedback paths, dashed.

    A feedback path inside one row joins its two nodes. One back to an earlier row (Learn to Plan) ends at a
    "back to Plan" marker in its own row: a link from a node to another row makes Mermaid drop the rows'
    left-to-right direction, and a back link between rows makes it stack the rows in the wrong order."""
    data = resources.roles()
    loop = data["loop"]
    steps = loop["steps"]
    if [x for _, _, row in LOOP_ROWS for x in row] != steps:
        raise ValueError(f"LOOP_ROWS must list the loop steps in order: {steps}")
    row_of = {}
    for key, _, row in LOOP_ROWS:
        for step in row:
            row_of[_node_id(step)] = key
            if step in GATES:
                row_of[GATES[step][0]] = key
    feedback = [(f, _point_id(f["from"]), _point_id(f["to"])) for f in loop["loops"]["feedback"]]
    covered = {(a, b) for _, a, b in feedback}
    lines = ["flowchart TD"]
    dashed: list[str] = []
    links = 0  # Mermaid numbers links in the order they are drawn, and linkStyle picks the dashed ones by number
    for key, title, row in LOOP_ROWS:
        lines += [f'  subgraph {key}["{title}"]', "    direction LR"]
        chain = []
        for step in row:
            roles = [k for k in data["order"] if step in data["roles"][k]["steps"]]
            label = step + "<br/><i>" + (_wrap(roles) or "a human merges") + "</i>"
            lines.append(f'    {_node_id(step)}["{label}"]')
            chain.append(_node_id(step))
            if step in GATES:
                gate, name, meaning = GATES[step]
                lines.append(f'    {gate}{{{{"{name}<br/>{meaning}"}}}}')  # a hexagon: a diamond grows too large for its text
                chain.append(gate)
        run = [chain[0]]
        for a, b in zip(chain, chain[1:], strict=False):
            if (a, b) in covered:  # a path people take only on a signal is drawn once, dashed
                lines += ["    " + " --> ".join(run)] if len(run) > 1 else []
                run = [b]
            else:
                run.append(b)
                links += 1
        lines += ["    " + " --> ".join(run)] if len(run) > 1 else []
        if VERIFY_BACK[0] in row:
            src, dst, why = VERIFY_BACK
            lines.append(f'    {_node_id(src)} -->|"{why}"| {_node_id(dst)}')
            links += 1
        for f, a, b in feedback:
            if row_of[a] != key:
                continue
            if row_of[b] != key:  # the way back to an earlier row ends at a marker in this row, named for its target
                lines.append(f'    {b}_again(["back to {f["to"]}"])')
                b = f"{b}_again"
            lines.append(f'    {a} -.->|"{_label(f["when"], 22)}"| {b}')
            dashed.append(str(links))
            links += 1
        lines.append("  end")
    keys = [key for key, _, _ in LOOP_ROWS]
    for a, b in zip(keys, keys[1:], strict=False):
        lines.append(f"  {a} --> {b}")
        links += 1
    lines += [HUMAN_CLASS, "  class " + ",".join(gate for gate, _, _ in GATES.values()) + " human"]
    lines.append(f"  linkStyle {','.join(dashed)} {FEEDBACK_STYLE}")
    return _mermaid(lines)


def flows_diagram() -> str:
    """Every command as one row, top to bottom: its role groups in order (several roles in a group run in parallel),
    and the person it stops for. Invisible links stack the rows, so the diagram grows down, not across."""
    data = resources.roles()
    lines, rows, stops = ["flowchart TB"], [], []
    for f in data["loop"]["flows"]:
        cmd = f["command"]
        rows.append(cmd)
        lines += [f'  subgraph {cmd}["/aidd-team:{cmd}"]', "    direction LR"]
        ids = []
        for i, group in enumerate(f["runs"]):
            nid = f"{cmd}_{i}"
            label = "<br/>".join(group) + ("<br/><i>in parallel</i>" if len(group) > 1 else "")
            lines.append(f'    {nid}["{label}"]')
            ids.append(nid)
        stop = f"{cmd}_stop"
        lines.append(f'    {stop}{{{{"{_label(f["stops_at"], 26)}"}}}}')
        stops.append(stop)
        lines += ["    " + " --> ".join(ids + [stop]), "  end"]
    lines.append("  " + " ~~~ ".join(rows))
    lines += [HUMAN_CLASS, "  class " + ",".join(stops) + " human"]
    return _mermaid(lines)


def handoffs_diagram() -> str:
    """Each handoff as one row, top to bottom: who hands off, what travels (the edge's label), and who receives it.
    A side with several roles is one node; a person who receives is drawn as a decision point."""
    data = resources.roles()
    lines, rows, people = ["flowchart TB"], [], []
    for i, h in enumerate(data["loop"]["handoffs"]):
        row, src, dst = f"h{i}", f"h{i}_from", f"h{i}_to"
        rows.append(row)
        lines += [f'  subgraph {row}[" "]', "    direction LR"]
        lines.append(f'    {src}["{"<br/>".join(h["from"])}"]')
        lines.append(f'    {dst}["{_label("<br/>".join(h["to"]))}"]')
        lines.append(f'    {src} -- "{_label(h["through"], 26)}" --> {dst}')
        lines.append("  end")
        if any(not t.replace("-", "").isalpha() or " " in t for t in h["to"]):
            people.append(dst)
    lines.append("  " + " ~~~ ".join(rows))
    lines.append(HUMAN_CLASS)
    if people:
        lines.append("  class " + ",".join(people) + " human")
    return _mermaid(lines)


PACKS_DIR = "plugins/aidd-team/skills"
AGENTS_DIR = "plugins/aidd-team/agents"

# Claude Code names a plugin's MCP tool `mcp__plugin_<plugin>_<server>__<tool>`, and a project server from
# `.mcp.json` `mcp__<server>__<tool>`. The aidd plugin's server is `aidd`, and `aidd init` wires the same server
# into `.mcp.json` as `aidd` for a team installed as project files, so a role's `tools:` allowlist names both.
# Without them a subagent's allowlist hides the aidd tools its prompt tells it to use. A `tools:` entry
# `mcp__<server>__*` grants every tool of that server (code.claude.com/docs/en/sub-agents, "Available tools",
# checked 2026-09-28); every aidd MCP tool reads, computes, or checks, and none writes or approves.
MCP_TOOL_PREFIXES = ("mcp__plugin_aidd_aidd__", "mcp__aidd__")

# The skill every role preloads: the aidd skill, the rulebook each agent file tells the role to follow. In the aidd
# plugin its name is `aidd:aidd`; `aidd init --team` writes it as the project skill `aidd`.
CORE_SKILL = "aidd:aidd"

# Built-in helper types a role may hand read-only work to, next to helpers of its own type (loop contract: "helpers
# of your own `aidd-team:<role>` type or read-only ones"). Explore is Claude Code's read-only search agent.
READ_ONLY_HELPERS = ("Explore",)

# Tools every role gets on top of its hand-chosen harness tools, in this order: `Skill` loads a practice skill or a
# domain pack by name, `Agent(...)` delegates to helpers, and `WebFetch`/`WebSearch` serve the research-first rule.
# The docs name the delegation tool `Agent` (it was `Task` before v2.1.63). Claude Code honors the type list in
# `Agent(a, b)` only for an agent run as the main thread (`claude --agent`); in a subagent it ignores the list
# (code.claude.com/docs/en/sub-agents, checked 2026-09-28, and a probe run on Claude Code 2.1.283 spawned an unlisted
# type). So the list states the rule, the guard hook denies writes from any helper that is not a role, and a
# read-only role (no write area) gets no `Agent` at all, as the docs advise for a reviewer that must stay read-only.
GENERATED_TOOLS = ("Skill", "Agent", "WebFetch", "WebSearch")


def split_tools(line: str) -> list[str]:
    """A `tools:` value as its entries: commas split them, except inside `Agent(a, b)`."""
    return [t.strip() for t in re.split(r",(?![^()]*\))", line) if t.strip()]


def role_tools(key: str, base: list[str]) -> list[str]:
    """A role's whole `tools:` list: its hand-chosen harness tools, the generated ones, and one server-level pattern per
    aidd MCP server. Only a role with a write area delegates (`Agent(aidd-team:<key>, Explore)`): the Reviewer and the
    Verifier work alone, so no helper they spawn can write on their behalf."""
    own = [t for t in base if not t.startswith("mcp__") and t.split("(", 1)[0] not in GENERATED_TOOLS]
    agent = f"Agent({', '.join((f'aidd-team:{key}', *READ_ONLY_HELPERS))})"
    delegates = bool(resources.roles()["roles"][key]["writes"])
    generated = [agent if t == "Agent" else t for t in GENERATED_TOOLS if t != "Agent" or delegates]
    return own + generated + [prefix + "*" for prefix in MCP_TOOL_PREFIXES]


def agent_with_tools(text: str, key: str | None = None) -> str:
    """An agent file whose front matter carries the generated `tools:` and `skills:` for its role.

    `tools:` keeps the file's hand-chosen harness tools (Read, Write, Bash, ...) and adds the generated ones; `skills:`
    is a YAML list, the form the subagent docs give for preloading. `key` defaults to the front matter's `name`.
    """
    end = text.index("\n---", 4)
    front = text[:end]
    m = re.search(r"^tools: (.*)$", front, re.M)
    if not m:
        raise ValueError("an aidd-team agent file needs a `tools:` line in its front matter")
    name = re.search(r"^name: (.*)$", front, re.M)
    key = key or (name.group(1).strip() if name else "")
    if key not in resources.roles()["roles"]:
        raise ValueError(f"an aidd-team agent file must be named for a role, not {key!r}")
    role = resources.roles()["roles"][key]
    front = front[: m.start()] + "tools: " + ", ".join(role_tools(key, split_tools(m.group(1)))) + front[m.end() :]
    front = re.sub(r"^(?:model|maxTurns): .*\n?", "", front + "\n", flags=re.M)
    front = re.sub(r"^skills:\n(?:  - .*\n?)*", "", front, flags=re.M).rstrip("\n")
    # The model follows the tier (resources.MODELS_BY_HARNESS), and `maxTurns` caps one run (Claude Code: a positive
    # integer, "maximum number of agentic turns (API round-trips) before stopping", read from 2.1.284's agent schema).
    front += f"\nmodel: {resources.tier_model(role['tier'])}\nmaxTurns: {role['max_turns']}"
    # The skills a role preloads: the aidd skill for a role that writes a Spec or tests, then the practice skills and
    # domain packs it uses on most runs. Every other role loads the aidd skill by name when it needs a rule.
    skills = [*([CORE_SKILL] if preloads_core(key) else []), *(f"aidd-team:{x}" for x in role.get("preload", []))]
    if skills:
        front += "\nskills:\n" + "".join(f"  - {s}\n" for s in skills).rstrip("\n")
    return front + text[end:]


def preloads_core(key: str) -> bool:
    """Whether role `key` preloads the aidd skill (11 KB into every run): only a role that writes a Spec, a Spec stub,
    or tests, where the Spec format and the frozen-test rules are the work itself."""
    r = resources.roles()["roles"][key]
    return bool({"{spec}", "{specs_dir}", "{tests}"} & set(r["writes"])) or "{tests}" in r.get("writes_unfrozen", [])


# A pack's checklist item for the entry check, before the first edit, when `aidd assess` shows the route and the lane.
ENTRY_LABEL = "Entry (`aidd assess`)"


# A pack's description: scoped to aidd repositories first, so it never fires elsewhere, then the nouns a change names.
PACK_TRIGGER = "In an aidd repository, use when code touches "

# The pack template, in order; `aidd eval packs` fails on a pack or a file that breaks it. A section in brackets
# appears only when the registry has something for it.
PACK_SECTIONS = ("Scope", "Standards", "Dated obligations", "Checklist by loop step", "Test commands", "Owned elsewhere", "References", "Keep it current")

# The one line every pack ends with: what the registry's dates mean, and where a missing standard goes.
KEEP_CURRENT = (
    "Each entry is due after its `review_every_days` (else emerging 90 days, established 365) or by its `review_due`. An emerging one "
    "applies only when the change needs it, said in the Spec. One `aidd eval standards` lists as due is looked up in Specify, and a "
    "missing one is proposed to aidd's `schemas/roles.json`."
)


def standard_row(s: dict) -> list[str]:
    """A standard's cells in a pack or practice skill: the name (marked emerging), the bare edition, the date, and the
    source. The edition's history stays in the registry's `notes`, which no skill renders."""
    name = s["name"] + (" (emerging)" if s.get("maturity") == "emerging" else "")
    date = s["checked"] if s.get("checked") else f"{s['reviewed']} (reviewed)"
    return [name, s.get("release") or "—", date, f"<{s['source']}>" if s.get("source") else "—"]


def _labels(d: dict) -> dict[str, str]:
    """Each pack standard's short label, `S1` to `S8`, in the order the pack lists them."""
    return {s["id"]: f"S{i}" for i, s in enumerate(d["standards"], 1)}


def pack_scope(d: dict) -> str:
    """The Scope section's text: applies when, not when, and the neighbours."""
    near = ", ".join(f"`aidd-team:{x}`" for x in d["scope"]["neighbours"])
    return f"Applies when the change touches {d['signal']}. Not when {d['scope']['not_when']}. Neighbours: {near}."


def defaults_row(d: dict) -> str:
    """The one checklist row that points to the product defaults a pack's domain builds."""
    keys = ", ".join(f"`{k}`" for k in d["defaults"])
    return f"Product defaults ({keys}): build each one `[project.defaults] off` does not name, as `aidd-team:product-defaults` says."


def render_pack(d: dict, choices: bool = True) -> str:
    """One domain pack: a skill generated from schemas/roles.json, in the pack template's order (PACK_SECTIONS)."""
    label = _labels(d)

    def cited(ids: list[str]) -> str:
        return ", ".join(label.get(x, x) for x in ids)

    preloaded = d["slug"] in preloaded_skills()
    if preloaded:
        # As a preloaded practice skill does: the dates, sources, and steward are in the roles reference.
        stds = _table("# | Standard | Edition", ([label[s["id"]], *standard_row(s)[:2]] for s in d["standards"]))
    else:
        stds = _table("# | Standard | Edition | Checked | Source", ([label[s["id"]], *standard_row(s)] for s in d["standards"]))
    rows = [[ENTRY_LABEL if c["step"] == "Entry" else c["step"], c["item"], cited(c["cites"])] for c in d["checklist"]]
    if d.get("defaults"):
        at = max((i for i, c in enumerate(d["checklist"]) if c["step"] == "Entry"), default=-1) + 1
        rows.insert(at, [ENTRY_LABEL, defaults_row(d), "—"])
    # A harness picks a skill by its description: scoped to aidd repositories, then the nouns a change names. Every
    # session and every subagent lists every description, so it stays under 200 characters.
    description = f"{PACK_TRIGGER}{_series(d['triggers'], 'or')}."
    parts = [
        f"---\nname: {d['slug']}\ndescription: {json.dumps(description)}\n---\n",
        "<!-- generated by `aidd gen-docs` from schemas/roles.json; edit the registry, not this file -->\n",
        f"# {d['name']}\n",
        f"## Scope\n\n{pack_scope(d)}\n",
        f"## Standards\n\n{stds}\n",
    ]
    if choices and open_choices_placement(d["slug"]) == "skill":
        parts[-1] += f"\n{open_choices_section(d['slug'])}\n"
    if d.get("obligations"):
        parts.append(
            f"## Dated obligations\n\n{_table('From | Obligation | Standard', ([o['date'], o['what'], cited(o['cites'])] for o in d['obligations']))}\n"
        )
    parts.append(f"## Checklist by loop step\n\n{_table('Step | Item | Standard', rows)}\n")
    tests = []
    if d["tests"]:
        tests.append(
            _table(
                "Command | Proves | How | Standard",
                (
                    [t["name"] + (" (emerging)" if t.get("maturity") == "emerging" else ""), t["proves"], t["how"], cited(t.get("cites", [])) or "—"]
                    for t in d["tests"]
                ),
            )
        )
    if d.get("tests_elsewhere"):
        tests.append("\n".join(f"- From `aidd-team:{x['owner']}`: {', '.join(x['tests'])}." for x in d["tests_elsewhere"]))
    parts.append("## Test commands\n\n" + "\n\n".join(tests) + "\n")
    if d.get("owned_elsewhere"):
        parts.append("## Owned elsewhere\n\n" + "\n".join(f"- {x['what']}: `aidd-team:{x['owner']}`." for x in d["owned_elsewhere"]) + "\n")
    refs = [f"- [{r['path']}]({r['path']}): {r['holds']}." for r in d.get("references", [])]
    # A pack no role preloads, whose choices would pass its cap, points to them itself; a preloaded one adds no bytes.
    if choices and d["slug"] not in preloaded_skills() and open_choices_placement(d["slug"]) == "reference":
        refs.append(f"- [references/{OPEN_CHOICES_REF}](references/{OPEN_CHOICES_REF}): its open choices, with aidd's defaults.")
    if refs:
        parts.append("## References\n\n" + "\n".join(refs) + "\n")
    # The person or team who keeps the pack current, when the registry names one (`aidd owners` lists them all).
    steward = f" Steward: {d['steward']}, who reviews every change to this pack's standards." if d.get("steward") else ""
    parts.append(f"## Keep it current\n\n{preloaded_pointer(d['slug']) if preloaded else KEEP_CURRENT + steward}\n")
    return "\n".join(parts)


def _standards():
    from . import standards

    return standards


OPEN_CHOICES_REF = "open-choices.md"


def preloaded_skills() -> set[str]:
    """The packs and practice skills some role preloads: their SKILL.md loads into every run of that role."""
    return {x for r in resources.roles()["roles"].values() for x in r.get("preload", [])}


# A preloaded skill loads whole into every run of its role, but a standard's checked date and source matter only when
# a role looks up or records an edition. So a preloaded skill carries each standard's name and edition and this
# pointer; the full rows, the steward, and when an entry is due are in the roles reference, once (`roles:preloaded`).
def preloaded_pointer(name: str) -> str:
    return f"Each standard's checked date and source are in {ROLE_REFERENCE}, section `aidd-team:{name}`."


def preloaded_sections() -> str:
    """Each preloaded pack's and practice skill's Standards rows in full (`roles:preloaded`): the edition, the checked
    date, and the source, with the steward. The skill itself carries only the names and editions."""
    data = resources.roles()
    out = [KEEP_CURRENT]
    for name in sorted(preloaded_skills()):
        pack = next((d for d in data["domains"] if d["slug"] == name), None)
        if pack is not None:
            label = _labels(pack)
            table = _table("# | Standard | Edition | Checked | Source", ([label[s["id"]], *standard_row(s)] for s in pack["standards"]))
            steward = pack.get("steward")
        else:
            table = _table("Standard | Edition | Checked | Source", (standard_row(s) for s in data["practices"][name]["standards"]))
            steward = practice_steward(name)
        out.append(f"### aidd-team:{name}\n\n{table}" + (f"\n\nSteward: {steward}." if steward else ""))
    return "\n\n".join(out)


def open_choices_section(owner: str) -> str:
    """The open choices of a pack or practice skill, as they appear inside its SKILL.md."""
    return (
        "### Open choices\n\nThe team decides these. aidd's default holds until a `[[standards]]` entry fills one "
        f"(`aidd standard list`).\n\n{_standards().open_choices_table(owner)}"
    )


def open_choices_reference(owner: str) -> str:
    """`references/open-choices.md` of a pack or practice skill that is preloaded or near its cap."""
    return (
        "<!-- generated by `aidd gen-docs` from schemas/roles.json; edit the registry, not this file -->\n\n"
        f"# Open choices: {owner}\n\n"
        f"`aidd-team:{owner}` leaves these decisions to the team. aidd's default holds until a `[[standards]]` entry fills one. "
        "`aidd standard list` names the library standards for each choice, and `aidd standard add` adopts one.\n\n"
        f"{_standards().open_choices_table(owner)}\n"
    )


def open_choices_placement(owner: str) -> str | None:
    """Where a pack's or practice skill's open choices go: `skill` (its SKILL.md), `reference` (its generated
    `references/open-choices.md`, when a role preloads the skill or the section would pass its cap), or None (none)."""
    from . import packs

    if not any(c["owner"] == owner for c in _standards().open_choices().values()):
        return None
    if owner in preloaded_skills():
        return "reference"
    extra = packs.estimate_tokens(open_choices_section(owner)) + 1
    pack = next((d for d in resources.roles()["domains"] if d["slug"] == owner), None)
    if pack is not None:
        return "reference" if packs.estimate_tokens(render_pack(pack, choices=False)) + extra > packs.PACK_TOKENS else "skill"
    path = resources.data_dir("team") / "skills" / owner / "SKILL.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = f"practice:{owner}"
    without = BLOCK.sub(lambda m: f"{m.group(1)}{practice_standards(owner, choices=False)}\n{m.group(4)}" if m.group(2) == block else m.group(0), text)
    return "reference" if packs.estimate_tokens(without) + extra > packs.PRACTICE_TOKENS else "skill"


def practice_steward(name: str) -> str | None:
    """A practice skill's steward: `metadata.steward` in its front matter when set, else its `practices` entry's
    `steward` in schemas/roles.json."""
    return practice_front(name).get("steward") or (resources.roles().get("practices", {}).get(name) or {}).get("steward")


def practice_standards(name: str, choices: bool = True) -> str:
    """A practice skill's Standards table (`practice:<name>`), from its registry ids, so `aidd eval standards` checks each."""
    entry = resources.roles().get("practices", {}).get(name)
    if entry is None:
        raise KeyError(f"practice skill {name!r} has no `practices` entry in schemas/roles.json")
    if name in preloaded_skills():
        # A preloaded skill keeps the name and edition; the dates, sources, and steward are in the roles reference.
        table = _table("Standard | Edition", (standard_row(s)[:2] for s in entry["standards"]))
        return f"{table}\n\n{preloaded_pointer(name)}"
    table = _table("Standard | Edition | Checked | Source", (standard_row(s) for s in entry["standards"]))
    # Kept to one short line: a practice skill loads whole into an agent's context, under its size cap.
    steward = practice_steward(name)
    out = f"{table}\n\nSteward: {steward}." if steward else table
    return out + (f"\n\n{open_choices_section(name)}" if choices and open_choices_placement(name) == "skill" else "")


def pack_path(root: Path, d: dict) -> Path:
    return root / PACKS_DIR / d["slug"] / "SKILL.md"


def targets(root: Path) -> list[Path]:
    found = []
    for pattern in ("*.md", "docs/**/*.md", ".agents/skills/**/*.md", "plugins/**/*.md", "examples/*.md"):
        found += [p for p in root.glob(pattern) if p.is_file() and not p.is_symlink()]
    return sorted(set(found))


def empty_tables(text: str) -> int:
    """How many Markdown tables in `text` have a header and no rows."""
    empty, run = 0, 0
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            run += 1
            continue
        empty += run in (1, 2)
        run = 0
    return empty


def _render_checked(name: str) -> str:
    out = render(name)
    if empty_tables(out):
        raise ValueError(f"generated block {name!r} rendered a table with no rows; its source is empty or a $ref did not resolve")
    return out


def regenerate(text: str) -> str:
    text = BLOCK.sub(lambda m: f"{m.group(1)}{_render_checked(m.group(2))}\n{m.group(4)}", text)
    return INLINE.sub(lambda m: f"{m.group(1)}{render(m.group(2))}{m.group(4)}", text)


def gen_docs(root: Path, check: bool = False) -> list[Path]:
    """Return the files that are (or were) stale."""
    stale: list[Path] = []

    def update(path: Path, new: str) -> None:
        if not path.is_file() or path.read_text(encoding="utf-8") != new:
            stale.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new, encoding="utf-8")

    for path in targets(root):
        text = path.read_text(encoding="utf-8")
        is_agent = path.parent == root / AGENTS_DIR
        if "<!-- aidd:gen " in text or is_agent:
            new = regenerate(text)
            update(path, agent_with_tools(new, path.stem) if is_agent else new)
    baseline = root / "schemas" / "baseline.json"
    if baseline.is_file():
        update(baseline, resources.baseline_json_text(baseline.read_text(encoding="utf-8")))
    for d in resources.roles()["domains"]:
        update(pack_path(root, d), render_pack(d))
    # A preloaded skill, or one near its cap, carries its open choices in a generated reference instead.
    owners = {c["owner"] for c in _standards().open_choices().values()}
    for owner in sorted(owners):
        if open_choices_placement(owner) == "reference":
            update(root / PACKS_DIR / owner / "references" / OPEN_CHOICES_REF, open_choices_reference(owner))
    for path in sorted((root / PACKS_DIR).glob(f"*/references/{OPEN_CHOICES_REF}")):
        if open_choices_placement(path.parent.parent.name) != "reference":
            stale.append(path)
            if not check:
                path.unlink()
    return stale
