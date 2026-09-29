"""Generate the Markdown tables that restate schemas, so docs and schemas never drift.

A generated block sits between `<!-- aidd:gen NAME -->` and `<!-- aidd:end -->`.
`aidd gen-docs --check` fails when any block is stale.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import harnesses, resources, rulebook, schema
from .util import md_cell

BLOCK = re.compile(r"(<!-- aidd:gen (\S+) -->\n)(.*?)(<!-- aidd:end -->)", re.S)
# A value inside a sentence, on one line: `<!-- aidd:gen count:roles -->14<!-- aidd:end -->`.
INLINE = re.compile(r"(<!-- aidd:gen ((?:count|mcp):\S+) -->)([^\n<]*)(<!-- aidd:end -->)")
# The schema node each `fields:<key>` block documents: a file, and the path inside it.
FIELD_SCHEMAS = {
    **{k: (f"{k}.schema.json", []) for k in ("spec", "change-request", "config", "evidence", "record", "epic", "initiative", "proposal")},
    **{k: ("spec.schema.json", ["$defs", k]) for k in ("task", "outcome", "triage")},
    **{k: ("common.schema.json", ["$defs", k]) for k in ("relation", "risk", "tests", "test_command", "emergency", "observe")},
    **{
        f"config-{k}": ("config.schema.json", ["properties", k])
        for k in ("owners", "targets", "agents", "policy", "observe", "gates", "identities", "evidence", "emergency", "guard", "hooks")
    },
    **{f"config-{k}": ("config.schema.json", ["properties", k, "items"]) for k in ("extends", "risk_rules", "standard_changes", "standards")},
    "config-owners-paths": ("config.schema.json", ["properties", "owners", "properties", "paths", "items"]),
    "config-agents-autonomy": ("config.schema.json", ["properties", "agents", "properties", "autonomy"]),
    "config-guard-gated_commands": ("config.schema.json", ["properties", "guard", "properties", "gated_commands", "items"]),
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


def fields_table(key: str) -> str:
    sch, base = resolve(*FIELD_SCHEMAS[key])
    required, conditional = set(sch.get("required", [])), _conditions(sch)
    rows = []
    for name, prop in sch.get("properties", {}).items():
        desc = prop.get("description") or _deref(prop, base)[0].get("description", "")
        rows.append([f"`{name}`", _type(prop, base), "yes" if name in required else conditional.get(name, "no"), desc.replace("|", "\\|")])
    return _table("Field | Type | Required | Meaning", rows)


def vocab_table(name: str) -> str:
    d = _node("common.schema.json", ["$defs", name])
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
    ("max_changed_lines", "Changed-line budget per route"),
    ("unlinked_authors", "Commit authors with no platform account"),
    ("spec_approval_proof", "Spec approval proven before implementation"),
    ("max_open_per_approver", "Open waits per Approver before `aidd next` warns (0: off; never gated)"),
    ("escalate_after_minutes", "Minutes before `aidd next` escalates a wait (0: off; never gated)"),
]


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
        shown = {k: n for k, n in v.items() if n}
        return ", ".join(f"{k} {n}" for k, n in shown.items()) if shown else "none"
    return str(v)


def profiles_table() -> str:
    data = resources.profiles()
    order = data["order"]
    return _table("Gate | " + " | ".join(order), ([label, *(_cell(data["profiles"][p][key]) for p in order)] for key, label in _GATE_ROWS))


def _codes(xs: list[str]) -> str:
    return ", ".join(f"`{x}`" for x in xs) or "none"


def baseline_table() -> str:
    b = resources.baseline()
    protected = f"<details><summary>{len(b['protected_paths'])} paths</summary>{_codes(b['protected_paths'])}</details>"
    rows = [["protected (cannot be disabled)", "major", "none", protected, "none; also every file a bound Policy or Observe command runs"]]
    rows += [[f"`{r['name']}`", r["route"], ", ".join(r["dimensions"]) or "none", _codes(r["paths"]), _codes(r.get("exclude", []))] for r in b["risk_rules"]]
    return _table("Rule | Minimum route | Dimensions | Paths | Excluded", rows)


_PLACEHOLDERS = {
    "{specs_dir}": "the Specs folder",
    "{proposals_dir}": "the proposals folder",
    "{spec}": "the active Spec",
    "{tests}": "its test files",
    "{design}": "its design files",
    "{scope}": "the scope of its Tasks",
}


def role_writes(writes: list[str]) -> str:
    """A role's write area in words."""
    return ", ".join(_PLACEHOLDERS.get(w, f"`{w}`") for w in writes) or "nothing (read-only)"


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
    """The artifacts a role acts on, by their short names."""
    arts = resources.roles()["loop"]["artifacts"]
    return "; ".join(arts[a]["name"] for a in r["reads"]) + "."


def standard_text(s: dict, edition: str = "edition") -> str:
    """`name (edition)` for a registry entry, with `emerging` when the registry marks it so; `edition` names the field
    to print (`release` is the bare edition, without the publication date and notes)."""
    notes = [x for x in (s.get(edition), "emerging" if s.get("maturity") == "emerging" else None) if x]
    return f"{s['name']} ({'; '.join(notes)})" if notes else s["name"]


def maturity_text(x: dict) -> str:
    """An extension's kind, its tier, and `emerging` when the registry marks it so."""
    return f"{x['kind']}, {x['tier']}" + (", emerging" if x.get("maturity") == "emerging" else "")


def capabilities_text(x: dict) -> str:
    """What an extension can touch, in words: `network, runs commands`, or `read-only` when it touches nothing."""
    words = [c.replace("_", " ") for c in x["capabilities"]]
    if "telemetry" in x["capabilities"]:
        words[x["capabilities"].index("telemetry")] = "telemetry (" + ("can be turned off" if x["telemetry_opt_out"] else "always on") + ")"
    return ", ".join(words) or "read-only"


def role_standards_text(stds: list[dict], full: bool = True) -> list[str]:
    """A role's standards, each document's edition printed once: a second use of one document shows its wording only.

    `full` prints the whole edition note (publication date and notes), as the reference tables do; an agent file
    carries the bare edition, and its note lives once, in docs/TEAM-REFERENCE.md.
    """
    seen: set[str] = set()
    out = []
    for s in stds:
        out.append(s["name"] if s["id"] in seen else standard_text(s, "edition" if full else "release"))
        seen.add(s["id"])
    return out


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
    """The front matter of a practice skill: `name`, `description`, and `checked` (from `metadata`)."""
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
    """The CLI's subcommand parsers, by name, from the same builder `aidd` runs."""
    import argparse

    from . import cli

    parser = cli.build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return dict(action.choices)


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
    for name, sub in _subcommands().items():
        args = [a for a in sub._actions if a.dest != "help"]
        positional = "".join(" " + _arg_text(a) for a in args if not a.option_strings)
        flags = ", ".join(_arg_text(a) for a in args if a.option_strings) or "none"
        rows.append([f"`{name}`{positional}", (sub.description or "").replace("|", "\\|"), flags])
    return _table("Command | What it does | Flags", rows)


# Every environment variable aidd reads or sets, and who reads it. tests/test_docs_generation.py fails when
# src/aidd names an AIDD_* variable this table does not, so the contract cannot drift from the code.
ENV_VARS = (
    (
        "AIDD_MODE",
        "`aidd gate github` and `aidd gate gitlab`",
        '`enforce` or `advisory` when neither the base config\'s `mode` nor `--mode` sets one (default `enforce`); on GitLab it can never relax the gate, so only `mode = "advisory"` in the base config makes it advisory',
    ),
    ("AIDD_PROTECTED_BRANCHES", "`aidd gate github`", "extra protected bases besides the default branch, comma-separated, globs allowed"),
    (
        "AIDD_ORG_PRESET",
        "every command that loads the config (the gate, `test`, `doctor`, `validate`, the edit-time guard)",
        "path to an org preset file, applied as the root parent of the repository config",
    ),
    ("GITHUB_TOKEN", "`aidd gate github`", "the token for the GitHub API (the App installation token in the reusable workflow)"),
    ("AIDD_GITLAB_TOKEN", "`aidd gate gitlab`", "the token for the GitLab API (`read_api`; `api` with `--post-status`)"),
    ("AIDD_SPEC", "`aidd hook pre-edit`, `aidd mcp`", "the active Spec, when a branch changes more than one"),
    ("AIDD_HOOK_OFFLINE", "`aidd hook pre-edit`", "`1` makes the edit-time guard skip network fetches of `extends` parents; the aidd plugin's hook sets it"),
    (
        "AIDD_HOOK_FAIL_CLOSED",
        "`aidd hook pre-edit`, the plugin's hook launcher",
        "`1` (the regulated managed settings set it) blocks when the guard cannot run or crashes, and denies a shell command it cannot parse",
    ),
    (
        "AIDD_HELPERS_MAY_WRITE",
        "`aidd hook pre-edit`",
        "`1`, in the environment Claude Code starts with, lets a subagent that is not an aidd-team role write; by default such a helper only reads",
    ),
    (
        "AIDD_AGENT",
        "`aidd approve`, `aidd ship`",
        "any value marks a shell started by an agent, so both refuse; set it in agent runners that set neither `CLAUDECODE` nor `CLAUDE_CODE_CHILD_SESSION` (Claude Code) nor `AI_AGENT`, which count the same",
    ),
    (
        "AIDD_OFFLINE",
        "`aidd init`, `aidd upgrade`",
        "`1` keeps the CI files at the release tag instead of asking GitHub (`git ls-remote`) for the commit it names, when aidd runs from an installed wheel",
    ),
    (
        "ORCA_PANE_KEY",
        "`aidd hook session-start`, `aidd hook stop`",
        "set by Orca in the terminals it manages; this, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT` means the hook runs inside Orca, "
        "so it puts `aidd next` on the worktree's Orca card (`[hooks] orca_status`). The edit-time guard never reads any of them",
    ),
    ("ORCA_WORKTREE_ID", "`aidd hook session-start`, `aidd hook stop`", "set by Orca, like `ORCA_PANE_KEY`"),
    ("ORCA_AGENT_HOOK_PORT", "`aidd hook session-start`, `aidd hook stop`", "set by Orca, like `ORCA_PANE_KEY`"),
    ("ORCA_CLI_COMMAND", "`aidd hook session-start`, `aidd hook stop`", "set by Orca in managed WSL sessions: the Orca CLI to call instead of `orca`"),
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
        "commands": lambda: len(resources.roles()["loop"]["flows"]),
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
    """`a, b, and c`: items as one phrase."""
    return ", ".join(items[:-1]) + f", {conj} {items[-1]}" if len(items) > 1 else items[0]


def role_block(key: str) -> str:
    """One role's facts in its agent file (`role:<key>`)."""
    r = resources.roles()["roles"][key]
    standards = "".join(f"\n  - {x}" for x in role_standards_text(r.get("standards", []), full=False))
    # The agent file names each extension with its kind and tier; what it adds, its source, license, and pin are
    # in the extensions reference, since an extension is used only when the project already has it.
    extends = "; ".join(f"{x['name']} ({maturity_text(x)})" for x in r.get("extends", [])) or "none listed yet; any capability, added through a change"
    # Names only: the harness lists every skill with its description, so the agent file does not repeat them.
    practices = ", ".join(f"`aidd-team:{x}`" for x in r["practices"]) or "none listed; this role works from its standards and the domain packs"
    contract = "".join(f"\n  {i}. {x}" for i, x in enumerate(resources.contract_for(key), 1))
    return (
        f"- **Loop steps:** {role_loop(r)}\n- **Starts when:** {r['starts_when']}\n- **Done when:** {r['done_when']}\n"
        f"- **Does:** {r['does']}\n"
        f"- **Reads:** {role_reads(r)}\n"
        f"- **May write:** {role_area(r)} (the edit-time guard checks edits; the gate decides on the diff)\n- **Hands off:** {r['hands_off']}\n"
        f"- **Model tier:** `{r['tier']}` ({resources.tier_models_text(r['tier'])})\n"
        f"- **Loop contract (the rules that bind this role):**{contract}\n- **Standards applied:**{standards}\n"
        f"- **Practice skills (load the one for each Task's kind of work with `Skill`, at most two per Task):** {practices}.\n"
        f"- **Extend with (optional, only when the project already uses it; what each adds is in the extensions reference):** {extends}."
    )


def capabilities_table() -> str:
    caps = resources.roles()["loop"]["capabilities"]
    counts = {k: sum(1 for c in caps["processes"] if c["coverage"] == k) for k in ("agents", "agents, a person decides", "people")}
    summary = (
        f"All {len(caps['processes'])} processes of {caps['standard']}: {counts['agents']} run by agents under the gate, "
        f"{counts['agents, a person decides']} run by agents with a person deciding, and {counts['people']} kept by people."
    )
    rows = ([c["group"], c["process"], ", ".join(f"`{b}`" for b in c["by"]) or "people", c["coverage"], c["how"]] for c in caps["processes"])
    return summary + "\n\n" + _table("Group | Process | Covered by | Who acts | How", rows)


def loop_tables() -> str:
    data = resources.roles()
    loop, order, roles = data["loop"], data["order"], data["roles"]
    marks = ([step, *("●" if step in roles[k]["steps"] else "" for k in order)] for step in loop["steps"])
    steps = _table("Step | " + " | ".join(f"`{k}`" for k in order), marks)
    when = _table("Role | Starts when | Done when", ([f"`{k}`", roles[k]["starts_when"], roles[k]["done_when"]] for k in order))
    contract = [
        f"{i}. {x}" + ("" if s is None else f" *(applies to: {', '.join(s)})*")
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
    """The `roles:*` reference tables, one row per role, domain, extension, flow, or handoff."""
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
        return _table(
            "Domain | Pack | When the change touches | Standards to apply",
            ([x["name"], f"`aidd-team:{x['slug']}`", x["signal"], "; ".join(standard_text(s) for s in x["standards"])] for x in data["domains"]),
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


def render(name: str) -> str:
    from . import mcp

    kind, _, arg = name.partition(":")
    prefixed = {"fields": fields_table, "count": lambda x: str(count(x)), "vocab": vocab_table, "role": role_block}
    if kind in prefixed:
        return prefixed[kind](arg)
    blocks = {
        "examples:cases": lambda: examples_table(_examples_root()),
        "mcp:revisions": lambda: _series(list(mcp.SUPPORTED), "and"),
        "mcp:latest": lambda: mcp.PROTOCOL,
        "cli:commands": cli_table,
        "cli:env": env_table,
        "profiles": profiles_table,
        "status:groups": groups_table,
        "baseline": baseline_table,
        "roles:capabilities": capabilities_table,
        "roles:commands": lambda: (
            "- **Commands:** "
            + ", ".join(f"`/aidd-team:{f['command']}`" for f in resources.roles()["loop"]["flows"])
            + "; one per flow in the registry, each running its roles in order and stopping where a person decides."
        ),
        "roles:loop": loop_tables,
        "roles:loops": loops_text,
        "roles:loop:diagram": loop_diagram,
        "roles:flows:diagram": flows_diagram,
        "roles:handoffs:diagram": handoffs_diagram,
        "harnesses": harnesses.table,
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


# The loop in three rows, read top to bottom, so it stays narrow enough to review on a page. Every change enters with
# `aidd next`, which computes the route and picks the lane: the fast and emergency lanes skip Plan and Specify and start at Implement.
LOOP_ROWS = (
    ("before", "Before any code: the fast lane skips to Implement", ("Plan", "Specify")),
    ("build", "Build and prove", ("Implement", "Verify", "Review")),
    ("run", "Ship and learn", ("Ship", "Learn")),
)

# The inner loop's own way back, drawn solid: a red test or a verifier's mismatch returns the head to Implement.
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
# type). So the list states the rule, the edit-time hook denies writes from any helper that is not a role, and a
# read-only role (no write area) gets no `Agent` at all, as the docs advise for a reviewer that must stay read-only.
GENERATED_TOOLS = ("Skill", "Agent", "WebFetch", "WebSearch")


def role_mcp_tools() -> list[str]:
    """The aidd MCP tools every role may call: all of them read, compute, or check, and none writes or approves."""
    from . import mcp

    return [prefix + str(t["name"]) for prefix in MCP_TOOL_PREFIXES for t in mcp.TOOLS]


def split_tools(line: str) -> list[str]:
    """A `tools:` value as its entries: commas split them, except inside `Agent(a, b)`."""
    return [t.strip() for t in re.split(r",(?![^()]*\))", line) if t.strip()]


def role_tools(key: str, base: list[str]) -> list[str]:
    """A role's whole `tools:` list: its hand-chosen harness tools, the generated ones, and one server-level pattern per
    aidd MCP server. Only a role with a write area delegates (`Agent(aidd-team:<key>, Explore)`): the reviewer and the
    verifier work alone, so no helper they spawn can write on their behalf."""
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
    front = front[: m.start()] + "tools: " + ", ".join(role_tools(key, split_tools(m.group(1)))) + front[m.end() :]
    front = re.sub(r"^skills:\n(?:  - .*\n?)*", "", front + "\n", flags=re.M).rstrip("\n")
    # The skills a role preloads: the aidd skill, then the practice skills and domain packs it uses on most runs.
    skills = [CORE_SKILL, *(f"aidd-team:{x}" for x in resources.roles()["roles"][key].get("preload", []))]
    front += "\nskills:\n" + "".join(f"  - {s}\n" for s in skills).rstrip("\n")
    return front + text[end:]


# A pack's checklist item for the entry rule, before the first step, when `aidd next` computes the route and the lane.
ENTRY_LABEL = "Entry (`aidd next`)"


def render_pack(d: dict) -> str:
    """One domain pack: a skill generated from schemas/roles.json."""
    stds = "\n".join(
        f"| {s['name']}{' (emerging)' if s.get('maturity') == 'emerging' else ''} | {s.get('edition') or '—'} | {s.get('checked') or s['reviewed'] + ' (reviewed)'} | "
        f"{('<' + s['source'] + '>') if s.get('source') else '—'} |"
        for s in d["standards"]
    )
    checklist = "\n".join(f"| {ENTRY_LABEL if c['step'] == 'Entry' else c['step']} | {c['item']} |" for c in d["checklist"])
    tests = "\n".join(f"| {c['name']}{' (emerging)' if c.get('maturity') == 'emerging' else ''} | {c['proves']} | {c['how']} |" for c in d["tests"])
    topic = d["name"] if d["name"].startswith(("AI", "API")) else d["name"][0].lower() + d["name"][1:]
    # A harness picks a skill by its description, so it leads with the nouns a change names (Claude Code truncates the
    # listing text at 1,536 characters: code.claude.com/docs/en/skills, checked 2026-09-28).
    description = (
        f"Use when code touches {_series(d['triggers'], 'or')}. Domain pack for {topic}, loaded on top of your aidd-team role: "
        f"the standards with their editions, a checklist per loop step, and the test commands to put in the Spec's tests."
    )
    return (
        f"---\nname: {d['slug']}\ndescription: {json.dumps(description)}\n---\n\n"
        f"<!-- generated by `aidd gen-docs` from schemas/roles.json; edit the registry, not this file -->\n\n"
        f"# {d['name']}\n\n"
        f"Applies when the change touches: {d['signal']}. Every role loads this pack for the steps it works in, on top of its own playbook. "
        f"The test commands below are best practices the gate runs: put them in the Spec's `[[tests.commands]]`, so a red one blocks the merge. "
        f"Name the pack in the Spec's Context; it does not count against a Task's `skills`.\n\n"
        f"## Standards\n\n| Standard | Edition | Checked | Source |\n| --- | --- | --- | --- |\n{stds}\n\n"
        f"## Checklist by loop step\n\n| Step | Item |\n| --- | --- |\n{checklist}\n\n"
        f"## Test commands\n\n| Command | Proves | How |\n| --- | --- | --- |\n{tests}\n\n"
        f"## Keep it current\n\n"
        f"A standard marked emerging is a draft, a first edition, or a young practice: apply it only when the change clearly needs it, and say so in the Spec. "
        f"A standard checked more than a year ago is stale: `aidd eval standards` lists it, and the loop contract's research-first rule applies. "
        f"When the change needs a standard this pack lacks, look up the authoritative source, record the edition in the Spec's Context, "
        f"and propose the update to the aidd project's roles registry (`schemas/roles.json` in the aidd repository) as an improvement.\n"
    )


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
    return stale
