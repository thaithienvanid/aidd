"""What more than one command shares: running from the repository root, the arguments people type in more than one
form (approvers, specialists, a body, a Spec by id), the config when there is one, and the vocabularies.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import re
import sys
from pathlib import Path

from aidd import config, platforms
from aidd.kernel import documents, git, globs, repo_paths, resources

# `aidd metrics --guard` with no path: the log `aidd hook pre-tool` keeps in the git directory (config.guard_log).
GUARD_LOG_DEFAULT = "-"

# Set only while aidd's own MCP server records the answer of its dialog, in its own process: a shell's
# `aidd approve --decided-via mcp:...` runs in another process, where it is never set.
_IN_MCP_DIALOG: contextvars.ContextVar[bool] = contextvars.ContextVar("aidd_in_mcp_dialog", default=False)


@contextlib.contextmanager
def mcp_dialog():
    """Mark the CLI run inside it as aidd's MCP server recording its dialog's answer (mcp_server._record_approval)."""
    token = _IN_MCP_DIALOG.set(True)
    try:
        yield
    finally:
        _IN_MCP_DIALOG.reset(token)


def in_mcp_dialog() -> bool:
    return _IN_MCP_DIALOG.get()


# Set only while aidd's prompt hook records what the person typed (`approve SPEC-1`), in the hook's own process: a
# `--decided-via prompt` from any other process never counts.
_IN_PROMPT_HOOK: contextvars.ContextVar[bool] = contextvars.ContextVar("aidd_in_prompt_hook", default=False)


@contextlib.contextmanager
def prompt_hook():
    """Mark the CLI run inside it as aidd's prompt hook recording the person's typed decision (session_hooks)."""
    token = _IN_PROMPT_HOOK.set(True)
    try:
        yield
    finally:
        _IN_PROMPT_HOOK.reset(token)


def in_prompt_hook() -> bool:
    return _IN_PROMPT_HOOK.get()


# Where the person decided, for a `--confirmed` answer (`--decided-via`): the aidd-mods plugin in Claude Code, or the terminal
# plugin in OpenCode, from a prompt the person typed or its dialog; an MCP client's elicitation dialog (`mcp:<client>`);
# or a prompt the person typed, which aidd's own prompt hook records (`prompt`). The record carries it.
DECIDED_VIA = "claude-code"
DECIDED_WHERE = re.compile(r"claude-code|opencode|prompt|mcp:[A-Za-z0-9.:_-]{1,48}")


def confirmation_problem(decided_via: str) -> str | None:
    """Why a `--confirmed` answer cannot stand in for a person at their terminal, or None. `--confirmed` skips the check
    that an agent started this shell, so something else must keep an agent from typing it: aidd's MCP server in its own
    process (`mcp:`), aidd's prompt hook in its own process (`prompt`), or, for aidd-mods and the OpenCode terminal half
    (`claude-code`, `opencode`), the guard, which always denies an agent's `--confirmed`."""
    if not DECIDED_WHERE.fullmatch(decided_via):
        return f"--decided-via {decided_via!r} must be claude-code, opencode, prompt, or mcp:<client>"
    if decided_via.startswith("mcp:"):
        if not in_mcp_dialog():
            return "an MCP client's confirmation counts only from aidd's MCP server, which asks the person itself. Type `/aidd approve` instead"
        return None
    if decided_via == "prompt":
        return None if in_prompt_hook() else "a typed prompt counts only from aidd's own prompt hook, which reads what the person typed"
    return None


def confirmed_here(args) -> bool:
    """Whether this run carries a person's confirmed answer that counts here: `--confirmed`, from a place
    `confirmation_problem` accepts. Land, approve, and publish take it as the person's decision (guard.check_decision)."""
    return getattr(args, "confirmed", None) is not None and confirmation_problem(str(getattr(args, "decided_via", "") or "")) is None


# The version of the other --json objects: `gate --json` (schemas/record.schema.json), `gate --paths --json`
# (schemas/forecast.schema.json), `list --json`, `standard list --json`, `stack list --json`, `log --json`, and
# `observe --band --json`, `eval packs --json`, and `record export --format json`. A new key keeps it; a renamed or
# removed one bumps it. `metrics --json` carries metrics.SCHEMA_VERSION.
JSON_SCHEMA_VERSION = "1"

EXIT = {"pass": 0, "fail": 1, "pending": 3}
# What each exit code means, by command: the table in docs/CLI.md and the exit codes in docs/ERRORS.md (`aidd gen-docs`
# reads it through cli_facts). Each row is a command and what 0, 1, 2, and 3 mean for it ("" where it never exits so).
EXIT_CODES: tuple[tuple[str, tuple[str, str, str, str]], ...] = (
    ("`gate` (local or `--context`)", ("pass", "fail", "error", "pending")),
    ("`gate github`", ("posted (pass or pending; advisory always)", "fail", "error (an `error` status is posted)", "")),
    ("`gate gitlab`", ("pass (pending with `--pending-ok`; advisory always)", "fail, pending, or a stale pipeline", "error", "")),
    (
        "`record verify`",
        (
            "the change record holds and is signed (or unsigned with `--allow-unsigned`)",
            "it does not hold, its signature does not verify, or it is unsigned",
            "error (no such record)",
            "",
        ),
    ),
    ("everything else", ("success", "a check failed", "error", "")),
)


VOCAB = resources.load_json("common.schema.json")["$defs"]
TYPES = VOCAB["type"]["enum"]
DIMENSIONS = VOCAB["dimension"]["enum"]


PASS_ENV_HELP = (
    "pass this credential-like variable to the command (repeatable); by default every *TOKEN*, *SECRET*, *PASSWORD*, *_KEY, "
    "and *CREDENTIAL* variable is dropped"
)


def enter_repo(args, *path_attrs: str, file_attrs: tuple[str, ...] = ()) -> None:
    """Run from the repository root. Repo-relative arguments are rebased; file arguments become absolute."""
    top = Path(git.toplevel(check=True))
    cwd = Path.cwd()
    for attr in file_attrs:
        value = getattr(args, attr, None)
        if value:
            setattr(args, attr, str((cwd / value).resolve()))
    for attr in path_attrs:
        value = getattr(args, attr, None)
        # A bare work-item id (`SPEC-1`) names no file here: it stays as typed, for `spec_by_id` to find from the root.
        if value and _WORK_ITEM_ID.fullmatch(value) and not (cwd / value).exists():
            continue
        if value:
            abs_path = (cwd / repo_paths.repo_path(value)).resolve()
            setattr(args, attr, abs_path.relative_to(top.resolve()).as_posix() if abs_path.is_relative_to(top.resolve()) else repo_paths.repo_path(value))
    os.chdir(top)


def repo_relative(path: Path) -> str:
    """A path as printed after `enter_repo`: relative to the repository root when it is inside it, else as given."""
    p = path.resolve()
    here = Path.cwd().resolve()
    return p.relative_to(here).as_posix() if p.is_relative_to(here) else str(path)


def body(args) -> str | None:
    if getattr(args, "body_file", None):
        return Path(args.body_file).read_text(encoding="utf-8")
    if getattr(args, "spec", None):
        return platforms.spec_block(args.spec)
    return None


_APPROVER = re.compile(
    r"^(?:(?!email:|agent:)[a-z0-9][a-z0-9_.-]*:(?!//))?"  # an optional tenant
    r"(?:@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?"  # @user or @org/team
    r"|email:[^@\s,]+@[^@\s,]+\.[^@\s,]+"  # email:you@example.com
    r"|[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[bot\])?)$"  # a bare login
)


def approvers(values: list[str] | None) -> list[str] | None:
    """--approvers as people type it: space or comma separated (`--approvers "@a,@b"`), each a valid identity."""
    if not values:
        return values
    out = [v.strip() for value in values for v in value.split(",") if v.strip()]
    bad = [v for v in out if v.lower().startswith("agent:") or not _APPROVER.match(v)]
    if bad:
        raise ValueError(
            f"--approvers: {', '.join(repr(b) for b in bad)} is not an approver identity; use @user, @org/team, email:you@example.com, or a "
            "login (agents never approve)"
        )
    return list(dict.fromkeys(out))


def specialists(entries: list[str] | None) -> dict[str, list[str]]:
    """--specialist security=@org/security,@alice -> {"security": ["@org/security", "@alice"]}."""
    out: dict[str, list[str]] = {}
    for entry in entries or []:
        pool, sep, who = entry.partition("=")
        if not sep or not pool.strip() or not who.strip():
            raise ValueError(f"--specialist takes POOL=WHO[,WHO], got {entry!r}")
        out.setdefault(pool.strip(), []).extend(w.strip() for w in who.split(",") if w.strip())
    return out


def counted(n: int, noun: str) -> str:
    """`1 stack`, `3 stacks`."""
    return f"{n} {noun}{'' if n == 1 else 's'}"


def config_or_none() -> config.Config | None:
    if not Path(config.CONFIG_PATH).is_file():
        return None
    return config.load_file(config.CONFIG_PATH)


_SPEC_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
# A work item's id as aidd writes one (`SPEC-1`, `PROP-3`): what `enter_repo` leaves as typed.
_WORK_ITEM_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")


def spec_by_id(value: str, ref: str | None) -> str:
    """`value` as a Spec or proposal path: itself when it names a file (in the working tree, or in `ref`), else, when it
    is an id (`SPEC-1`, `PROP-3`), the one Spec under the specs folder or proposal under the proposals folder whose id
    it is. Run from the repository root."""
    if Path(value).is_file() or (ref and git.show(ref, value) is not None) or not _SPEC_ID.fullmatch(value) or value.endswith(".md"):
        return value
    cfg = config_or_none()
    folder = cfg.specs_dir if cfg else "specs"
    proposals = cfg.proposals_dir if cfg else "proposals"
    named = globs.under(folder, f"{value}.md")
    for path in (named, globs.under(proposals, f"{value}/proposal.md")):
        if Path(path).is_file() or (ref and git.show(ref, path) is not None):
            return path
    found = []
    candidates = [(p, "spec") for p in sorted(Path(folder).glob("*.md"))] + [(p, "proposal") for p in sorted(Path(proposals).glob("*/proposal.md"))]
    for p, kind in candidates:
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), str(p))
        except (documents.DocumentError, OSError):
            continue
        if data.get("kind") == kind and str(data.get("id")) == value:
            found.append(p.as_posix())
    if len(found) == 1:
        return found[0]
    if found:
        raise ValueError(f"{len(found)} files have the id {value} ({', '.join(found)}); name the file")
    raise ValueError(f"no Spec has the id {value} in {folder}/, and no proposal has it in {proposals}/; name the file, such as {named}")


# The config problems this process has said already, by the folder and the line: a command that reads the config
# twice, such as `aidd list`, says it once.
_CONFIG_PROBLEMS_SHOWN: set[tuple[str, str]] = set()


def config_or_none_quiet() -> config.Config | None:
    """The config, or None when there is none or it does not load. A config that exists and does not load gets one line
    on stderr, once in a process, so the command that goes on without it never hides why: what is wrong, and the next
    step."""
    try:
        return config_or_none()
    except (config.ConfigError, documents.DocumentError, OSError) as exc:
        line = config_load_problem(exc)
        key = (os.path.realpath(os.getcwd()), line)
        if key not in _CONFIG_PROBLEMS_SHOWN:
            _CONFIG_PROBLEMS_SHOWN.add(key)
            print(line, file=sys.stderr)
        return None


def config_load_problem(exc: BaseException) -> str:
    """The one line that says the config does not load: the first line of the reason, with no control character, cut
    short, and `aidd validate`."""
    reason = documents.one_line((str(exc).strip().splitlines() or [type(exc).__name__])[0], 120)
    return f"aidd: {config.CONFIG_PATH} does not load ({reason}), so this command goes on without it. Run `aidd validate` to see what to fix."


def base_from_spec(args) -> None:
    """Locally, with no `--base`: compare against, and land in, the goal branch this branch's Spec lands in (its
    `base`, the goal branch it lands in), when its one active Spec names a `goal/` branch this one builds on
    (workitems.builds_on). An agent writes the `base`, so it never picks another target: any other base takes an
    explicit `--base`. Several Specs naming different bases name none. On the goal branch itself, whose Specs name
    it, the default branch stays the base. A platform's pull request target decides there, never this."""
    if getattr(args, "base", None):
        return
    from aidd import workitems

    cfg = config_or_none_quiet()
    if cfg is None:
        return
    bases = {str(d["base"]) for _, d in workitems.active_specs(".", cfg) if d.get("base")}
    if len(bases) == 1:
        base = bases.pop()
        here = git.run(["symbolic-ref", "-q", "--short", "HEAD"], check=False).strip()
        if base != here and base.startswith(workitems.GOAL_PREFIX) and workitems.builds_on(".", base):
            args.base = base


def base_sha(args, head: str = "HEAD") -> str | None:
    """Where `head` meets the base branch (`--base`, else the default branch), or None when there is none to find."""
    try:
        base = getattr(args, "base", None) or git.default_base()
        return git.merge_base(git.rev_parse(base), git.rev_parse(head))
    except git.GitError:
        return None


def html_arg(value: str | None) -> str | None:
    """`--html` alone means the default page path (""); absent means no page (None). A given PATH is made absolute."""
    return None if value is None else str(Path(value).resolve()) if value else ""


def default_branch(root: str) -> str:
    """The origin's default branch (`refs/remotes/origin/HEAD`), or main."""
    try:
        head = git.run(["symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"], root, check=False).strip()
    except (git.GitError, OSError):
        head = ""
    return head.removeprefix("origin/") or "main"


BASE_HELP = "base branch to compare against (default: origin/HEAD, then origin/main, origin/master, main, master)"
