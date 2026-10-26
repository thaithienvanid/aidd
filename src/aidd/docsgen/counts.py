"""The numbers and lists the docs state, counted from the data that defines them: the counts, the environment
variables, the coding agents, and the conformance cases.
"""

from __future__ import annotations

import json
from pathlib import Path

from aidd import config, knowledge
from aidd.docsgen import blocks, schema_tables, team_reference
from aidd.kernel import resources
from aidd.kernel.text import md_cell

# Every environment variable aidd reads or sets, and who reads it. tests/test_docs_generation.py fails when
# src/aidd names an AIDD_* variable this table does not, so the contract cannot drift from the code.
ENV_VARS = (
    (
        "AIDD_MODE",
        "`aidd gate github` and `aidd gate gitlab`",
        "`enforce` when neither the base config's `mode` nor `--mode` sets one (the default either way): any job or pipeline can set an environment variable, so it can never relax the gate. On GitHub the reusable workflow passes its `mode` input as `--mode`; on GitLab only `mode: advisory` in the base config makes the gate advisory",
    ),
    ("AIDD_PROTECTED_BRANCHES", "`aidd gate github`", "extra protected bases besides the default branch, comma-separated, globs allowed"),
    (
        "AIDD_ORG_PRESET",
        "every command that loads the config (the gate, `test`, `doctor`, `validate`, the guard)",
        "path to an org preset file, applied as the root parent of the repository config",
    ),
    (
        "GITHUB_TOKEN",
        "`aidd gate github`, `aidd eval standards --online`, `aidd doctor --autopilot`",
        "the token for the GitHub API (the App installation token in the reusable workflow; for the online standards check, a read-only token sent to api.github.com alone). `doctor --autopilot` reads its first four characters only, with `GH_TOKEN`'s, to warn on a long-lived GitHub token (`ghp_` or `gho_`)",
    ),
    ("AIDD_GITLAB_TOKEN", "`aidd gate gitlab`", "the token for the GitLab API (`read_api`; `api` with `--post-status`)"),
    ("AIDD_SPEC", "`aidd hook pre-tool`, `aidd mcp`", "the active Spec, when a branch changes more than one"),
    (
        "AIDD_WORKTREE",
        "your test commands (set by `aidd test`), `project.dev_services.teardown` (set by `aidd worktrees clean`)",
        "a stable name for the worktree, such as `shop_3f9a1c`: name the database, bucket, and ports each worktree uses in the shared dev stack by it",
    ),
    (
        "AIDD_HOOK_OFFLINE",
        "`aidd hook pre-tool`, the session hooks",
        "`1` makes the guard skip network fetches of `extends` parents, and the session hooks skip the doctor's network checks; "
        "the aidd plugin's hook and the session hooks set it",
    ),
    (
        "AIDD_HOOK_FAIL_CLOSED",
        "`aidd hook pre-tool`, the guard hook `aidd init` writes, the plugin's hook launcher",
        "`1` blocks when the guard cannot run, crashes, or runs past its deadline, and denies a shell command it cannot parse, only in a "
        "repository with `.aidd/config.yaml`. An organization sets it in its managed settings; a project needs no variable, since the "
        "audited profile and `mode: enforce` do the same. Never set it in user settings",
    ),
    (
        "AIDD_SUBAGENTS_MAY_WRITE",
        "`aidd hook pre-tool`",
        "`1`, in the environment Claude Code starts with, lets a subagent that is not an aidd-team role write; by default such a helper only reads",
    ),
    (
        "AIDD_AGENT",
        "`aidd approve`, `aidd land`",
        "any value marks a shell started by an agent, so both refuse; set it in agent runners that set neither `CLAUDECODE` nor `CLAUDE_CODE_CHILD_SESSION` (Claude Code) nor `AI_AGENT`, which count the same",
    ),
    (
        "AIDD_OFFLINE",
        "`aidd init`, `aidd upgrade`, `aidd doctor`",
        "`1` keeps the CI files at the release tag instead of asking GitHub (`git ls-remote`) for the commit it names, when aidd runs from an installed wheel; "
        "it also skips the doctor's pin and branch-protection checks, which `aidd gate --paths`, `aidd list`, and `aidd digest` run too, "
        "and the daily update check",
    ),
    (
        "AIDD_NO_UPDATE_CHECK",
        "every command run at a terminal",
        "`1` turns off the daily note that a newer release is out; `aidd self-update` still works",
    ),
    (
        "AIDD_SESSION_ID",
        "aidd's OpenCode plugin",
        "not a variable: the word `${AIDD_SESSION_ID}` in a shell command, which the plugin replaces with the OpenCode session's id before the command runs, so `/aidd-autopilot` binds its lease to that session",
    ),
    (
        "AIDD_AUTO_UPDATE",
        "every command run at a terminal",
        "`1` lets the daily check install a newer release itself instead of only saying it is out, from the release's wheel "
        "once it matches the release's SHA256SUMS (and its build provenance, with gh); never the tip of main",
    ),
    (
        "ORCA_PANE_KEY",
        "`aidd hook session-start`, `aidd hook stop`",
        "set by Orca in the terminals it manages; this, `ORCA_WORKTREE_ID`, or `ORCA_AGENT_HOOK_PORT` means the hook runs inside Orca, "
        "so it puts this change's next step on the worktree's Orca card (`hooks.orca_status`). The guard never reads any of them",
    ),
    ("ORCA_WORKTREE_ID", "`aidd hook session-start`, `aidd hook stop`", "set by Orca, like `ORCA_PANE_KEY`"),
    ("ORCA_AGENT_HOOK_PORT", "`aidd hook session-start`, `aidd hook stop`", "set by Orca, like `ORCA_PANE_KEY`"),
    ("ORCA_CLI_COMMAND", "`aidd hook session-start`, `aidd hook stop`", "set by Orca in managed WSL sessions: the Orca CLI to call instead of `orca`"),
    (
        "CLAUDE_CODE_DISABLE_ADVISOR_TOOL",
        "`aidd doctor --autopilot`",
        "Claude Code's own switch: `1` turns its advisor off, so the doctor says a configured `advisorModel` does not apply",
    ),
    ("AIDD_DEBUG", "every command", "`1` prints the traceback of an error to stderr; a crash then asks you to report it with that traceback"),
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
    ("AIDD_NOTICE", "your `autopilot.notify` command (set by `aidd autopilot next`)", "the stop message, also passed as the command's last argument"),
)


def env_table() -> str:
    from aidd.kernel.processes import SECRET_ENV

    table = blocks.markdown_table("Variable | Read by | Meaning", ([f"`{name}`", who, meaning] for name, who, meaning in ENV_VARS))
    return table + f"\n\nStripped from the environment of every test, Policy, and Observe command: {schema_tables._codes(list(SECRET_ENV))}."


def _source_root() -> Path:
    root = resources.repo_root()
    if root is None:
        raise RuntimeError("counts of examples and evals need the aidd source checkout")
    return root


def count(name: str) -> int:
    """A number the docs state, counted from the data that defines it, so prose cannot drift."""
    from aidd import evals

    counters = {
        "harnesses": lambda: len(config.HARNESSES),
        "roles": lambda: len(knowledge.roles()["order"]),
        "packs": lambda: len(knowledge.roles()["domains"]),
        "practices": lambda: len(knowledge.practice_names()),
        "commands": lambda: len(team_reference.team_commands()),
        "types": lambda: len(schema_tables._node("common.schema.json", ["$defs", "type"])["enum"]),
        "dimensions": lambda: len(schema_tables._node("common.schema.json", ["$defs", "dimension"])["enum"]),
        "product-defaults": lambda: len(config.PROJECT_DEFAULTS),
        "examples": lambda: sum(1 for p in (_source_root() / "examples").iterdir() if (p / "context.json").is_file()),
        "mutations": lambda: len(list((_source_root() / "examples").glob("*/mutations/*.json"))),
        "routing-scenarios": lambda: len(evals.load_scenarios(_source_root() / "evals" / "routing")),
        "role-scenarios": lambda: len(evals.load_scenarios(_source_root() / "evals" / "roles")),
    }
    if name not in counters:
        raise KeyError(f"unknown count {name!r}")
    return counters[name]()


def harnesses_summary() -> str:
    """The short agent table: each agent the guard runs in, in its own row, then every other agent, grouped by which
    pointer files init creates and which it only appends to."""
    hs = config.HARNESSES
    main = config.guarded_harnesses()
    others = [h for h in hs.values() if h not in main]
    agents_md = [h.label for h in others if not h.pointer]
    created = [f"{h.label} (`{h.pointer}`)" for h in others if h.pointer and not h.only_if_present]
    appended = [f"{h.label} (`{h.pointer}`)" for h in others if h.pointer and h.only_if_present]
    md = config.AGENTS_MD
    rows = [[f"**{h.label}**", h.wiring, h.you] for h in main]
    native = ", ".join(h.label for h in others if h.agent_dirs)
    rows.append(
        [
            ", ".join(agents_md),
            f"vendors the skill in `.agents/skills/aidd/` and points `{md}` at it; `--team` adds a short roles section to `{md}`"
            + (f", plus native agent files for {native}" if native else "")
            + "; no hook checks the agent, so the team is advisory",
            "nothing",
        ]
    )
    if created:
        rows.append([", ".join(created), "the same, plus a pointer in the agent's own instruction file, which init creates", "nothing"])
    if appended:
        own = "the same, and appends the pointer to the agent's own instruction file only when that file already exists"
        rows.append([", ".join(appended), own, "nothing, except Aider: `read: CONVENTIONS.md` in `.aider.conf.yml`"])
    rows.append(["Anything else", f"`{md}` and `.agents/skills/aidd/`", f"tell the agent to read `{md}`"])
    gemini = "Gemini CLI was retired on June 18, 2026 for most users, who moved to the Antigravity CLI; it still serves some paid licenses ([details](docs/INSTALL.md#your-coding-agent))."
    notes = [gemini] if "gemini" in hs else []
    return "\n\n".join([blocks.markdown_table("Your agent | What `aidd init` does | What you do", rows), *notes, config.PLUGIN_NOTE])


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
    return blocks.markdown_table("Case | Title | Decision | What it shows | Mutations", rows)


def _examples_root() -> Path:
    root = resources.repo_root()
    if root is None:
        raise LookupError("the examples/ case table is generated from a source checkout")
    return root
