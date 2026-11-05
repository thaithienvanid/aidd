"""The numbers and lists the docs state, counted from the data that defines them: the counts, the environment
variables, the coding agents, and the conformance cases.
"""

from __future__ import annotations

from pathlib import Path

from aidd import config, knowledge
from aidd.docsgen import blocks, schema_tables, team_reference
from aidd.kernel import resources

# Every environment variable aidd reads or sets, and who reads it. tests/test_docs_generation.py fails when
# src/aidd names an AIDD_* variable this table does not, so the contract cannot drift from the code. The docs list the rows in
# this order.
ENV_VARS = (
    (
        "AIDD_OFFLINE",
        "every command that loads the config, and `aidd self-update`",
        "`1` stops every optional network call: `extends` parents by URL are skipped with a warning, no update check runs, and `aidd init --claude-plugins` wires the repository instead",
    ),
    ("AIDD_ORG_PRESET", "every command that loads the config", "the path of an org preset, read as the first parent of every config"),
    ("AIDD_DEBUG", "every command", "`1` prints the traceback of an error to stderr; a crash then asks you to report it"),
    ("AIDD_AGENT", "`aidd self-update`'s daily check", "any non-empty value tells aidd an agent runs the shell, so the daily update check stays off"),
    (
        "AIDD_UPDATE",
        "every command a person runs at a terminal",
        "the daily check for a newer release: `off` runs none, `notify` (the default) says one is out, `install` installs it, verified",
    ),
    ("AIDD_REF", "the one-line installer", "the release tag or commit to install, such as `v1.0.0`"),
    ("AIDD_WORKTREE", "your test commands (set by `aidd test`)", "the worktree's folder name as a slug, so a project can name its test database by it"),
    ("GH_TOKEN", "`aidd eval standards --online`, `aidd self-update`", "a read-only GitHub token, for a higher rate limit; never required"),
)


def env_table() -> str:
    from aidd.kernel.processes import SECRET_ENV

    table = blocks.markdown_table("Variable | Read by | Meaning", ([f"`{name}`", who, meaning] for name, who, meaning in ENV_VARS))
    return table + f"\n\nStripped from the environment of every test command: {schema_tables.code_list(list(SECRET_ENV))}."


def _source_root() -> Path:
    root = resources.repo_root()
    if root is None:
        raise RuntimeError("counts of the evals need the aidd source checkout")
    return root


def count(name: str) -> int:
    """A number the docs state, counted from the data that defines it, so prose cannot drift."""
    from aidd import evals

    counters = {
        "harnesses": lambda: len(config.HARNESSES),
        "ask-rule-harnesses": lambda: len(config.ask_rule_harnesses()),
        "roles": lambda: len(knowledge.roles()["order"]),
        "packs": lambda: len(knowledge.roles()["domains"]),
        "practices": lambda: len(knowledge.practice_names()),
        "commands": lambda: len(team_reference.team_commands()),
        "types": lambda: len(schema_tables.schema_node("common.schema.json", ["$defs", "change_type"])["enum"]),
        "dimensions": lambda: len(schema_tables.schema_node("common.schema.json", ["$defs", "dimension"])["enum"]),
        "product-defaults": lambda: len(config.PROJECT_DEFAULTS),
        "areas": lambda: len(resources.load_json("risks.json")["areas"]),
        "actions": lambda: len(resources.load_json("risks.json")["actions"]),
        "risk-rules": lambda: len(resources.load_json("risks.json")["rules"]),
        "routing-scenarios": lambda: len(evals.load_scenarios(_source_root() / "evals" / "routing")),
        "role-scenarios": lambda: len(evals.load_scenarios(_source_root() / "evals" / "roles")),
    }
    if name not in counters:
        raise KeyError(f"unknown count {name!r}")
    return counters[name]()


def harnesses_summary() -> str:
    """The short agent table: each agent `aidd init` writes the ask rules for, in its own row, then every other agent."""
    main = config.ask_rule_harnesses()
    others = [h for h in config.HARNESSES.values() if h not in main]
    agents_md = [h.label for h in others]
    md = config.AGENTS_MD
    rows = [[f"**{h.label}**", h.wiring, config.what_you_do(h)] for h in main]
    native = ", ".join(h.label for h in others if h.agent_dirs)
    rows.append(
        [
            ", ".join(agents_md),
            f"vendors the skill in `.agents/skills/aidd/` and points `{md}` at it; `--aidd-team` adds a short roles section to `{md}`"
            + (f", plus native agent files for {native}" if native else "")
            + "; the skill says when to ask",
            "nothing",
        ]
    )
    rows.append(["Anything else", f"`{md}` and `.agents/skills/aidd/`", f"tell the agent to read `{md}`"])
    return "\n\n".join([blocks.markdown_table("Your agent | What `aidd init` does | What you do", rows), config.PLUGIN_NOTE])
