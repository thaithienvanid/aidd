"""What the commands share: the exit codes, running from the repository root, reading the config, and the flags' values."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from aidd import config, knowledge, workitems
from aidd.kernel import command_names, documents, git, globs, json_schema, regular_files, repo_paths, resources, retired_names
from aidd.kernel.text import did_you_mean

JSON_SCHEMA_VERSION = "1"


class NoRepositoryError(ValueError):
    """A command that works on a git repository ran in a folder that no repository holds; the message says what to do."""


def error_object(error: dict) -> dict:
    """What a `--json` command prints on stdout before it exits 2 (`error` in the common schema): the finding that says what
    stopped it, under the output's version. The words for a person go on stderr as before."""
    return {"schema_version": JSON_SCHEMA_VERSION, "error": error}


# What each exit code means, by command: the table in docs/CLI.md (`aidd gen-docs` reads it through cli_facts). Each row
# is a command and what 0, 1, and 2 mean for it ("" where it never exits so). The table lists the rows in this order.
EXIT_CODES: tuple[tuple[str, tuple[str, str, str]], ...] = (
    (
        "`test`",
        (
            "every command passed (and every new-behavior command failed on the base)",
            "a test failed, a full run ran no command where one is needed, or a full run was in a dirty tree",
            "error",
        ),
    ),
    ("`validate`, `doctor`", ("no errors", "an error or a failed check", "error; with `--json`, the error object on stdout")),
    ("everything else", ("success", "a check failed", "error; with `--json`, the error object on stdout")),
)

VOCAB = resources.load_json("common.schema.json")["$defs"]
CHANGE_TYPES = VOCAB["change_type"]["enum"]
DIMENSIONS = VOCAB["dimension"]["enum"]
BRANCHES = resources.load_json("risks.json")["branches"]
# The routes a Spec approval covers: the routes that need a Spec. An emergency is a backfill after the repair, so it is
# never the route being approved.
APPROVAL_ROUTES = [route for route in config.ROUTES if config.LANE_OF[route] == "spec"]

# The types of word `aidd explain` knows, as the help names them: "an action, an area, ..., or a profile".
_TYPES = [f"{'an' if word_type[0] in 'aeiou' else 'a'} {word_type.replace('_', ' ')}" for word_type in knowledge.EXPLAIN_TYPES]
EXPLAIN_TYPES_PHRASE = ", ".join(_TYPES[:-1]) + ", or " + _TYPES[-1]


class Default(str):
    """A flag's default that reads as its text, so a command can tell it from the same text typed (`risk --change-type`)."""


PASS_ENV_HELP = (
    "pass this credential-like variable to the command (repeatable); by default every *TOKEN*, *SECRET*, *PASSWORD*, *_KEY, "
    "and *CREDENTIAL* variable is dropped"
)

_SPEC_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class PlannedPaths:
    """Planned paths as `planned_readings` reads them: as `typed`, `every` reading (the text readings, and where a link
    leads), which routes, so the stricter wins; for each path typed, its first reading (`here`: the typed folder's, from the
    top) and its last (`top`), and the one `status <path>` takes (`scope`): the first that names a file or a folder in
    the repository, else the first. A new Spec's scope takes `here`."""

    typed: list[str]
    every: list[str]
    here: list[str]
    top: list[str]
    scope: list[str]

    def differ(self) -> bool:
        return self.here != self.top


def _folder_in_repo(top: Path, cwd: Path) -> str:
    """The folder aidd runs in, relative to the repository's top ("" at the top), as text."""
    for a, b in ((str(cwd), str(top)), (os.path.realpath(cwd), os.path.realpath(top))):
        rel = os.path.relpath(a, b).replace(os.sep, "/")
        if rel != ".." and not rel.startswith("../"):
            return "" if rel == "." else rel
    return ""


def planned_readings(values: list[str], top: Path, cwd: Path) -> PlannedPaths:
    """The one reading of planned paths for every caller (`aidd risk --paths`, `aidd new spec --paths`, `aidd status
    <path>`, and the MCP tools, which run at the top): each path read from the folder it was typed in and from the
    repository's top (`repo_paths.readings`), so a subfolder never makes a path read safer than git prints it, and
    again where a link inside the repository leads. A path outside the repository is a ValueError with the next step."""
    here_dir = _folder_in_repo(top, cwd)
    every, here, top_reading, scope = [], [], [], []
    for value in values:
        found = repo_paths.readings(value, top=str(top), here=here_dir)
        every += (
            found
            + repo_paths.bare_readings(value, found)
            + repo_paths.link_readings(found, top=str(top))
            + repo_paths.real_readings(value, top=str(top), here=here_dir)
        )
        here.append(found[0])
        top_reading.append(found[-1])
        scope.append(next((r for r in found if os.path.lexists(top / r.rstrip("/"))), found[0]))
    return PlannedPaths(list(values), list(dict.fromkeys(every)), here, top_reading, scope)


def enter_repo(args, *path_attrs: str, file_attrs: tuple[str, ...] = (), outside_ok: bool = False) -> None:
    """Run from the repository root. Repo-relative arguments are rebased; file arguments become absolute. In a folder that
    no repository holds, a command that works on files alone (`outside_ok`) runs where it is, with its arguments as
    typed; any other stops with the next step (`git.no_repository_problem`). A list of paths, such as `--paths`, is read
    by `planned_readings`, and its readings are kept as `args.planned`; one path takes the reading its scope would."""
    _enter_top(args, git.repository_top(), path_attrs, file_attrs, outside_ok)


def setup_root(path: str | None, command: Literal["init", "upgrade", "uninstall", "doctor"]) -> Path:
    """The repository a setup command (`init`, `upgrade`, `uninstall`, `doctor`) works on. With no path, it is the top of the
    repository the current folder is in, so a subfolder never gets a second aidd that no work command reads; and a folder in no repository stays as it is. A path names a folder: it must be the top, or hold no repository,
    and a folder inside one is refused with the way out. A path that is no directory comes back as typed, for the command to word."""
    start = Path(path or ".").absolute()
    if not start.is_dir():
        return start
    found = git.repository_top(str(start))
    if found is None:
        return start
    top = Path(found)
    if path is None:
        return top
    if os.path.realpath(start) == os.path.realpath(top):
        return start
    word = command_names.quoted(str(top))  # the folder's name is the machine's text, so it joins a command only as a plain name
    named = f"`aidd {command} {word}`, or " if word else ""
    raise ValueError(
        f"{start} is inside the repository at {top}, not at its top, and `aidd {command}` works on the top folder, where the config lives. "
        f"Run {named}`aidd {command}` with no path from anywhere inside it. "
        f"To make this folder a repository of its own, run `git init` there first"
    )


def _refuse_empty_paths(args, path_attrs: tuple[str, ...]) -> None:
    """An empty path in a list of paths, such as `--paths ""`, is an error with the next step, never a command line that
    silently drops it and answers for something else."""
    for attr in path_attrs:
        value = getattr(args, attr, None)
        if isinstance(value, list) and not all(value):
            raise ValueError(f"--{attr} got an empty path: name a path inside the repository, such as src/billing/charge.py, or ./ for all of it")


def _enter_top(args, found: str | None, path_attrs: tuple[str, ...], file_attrs: tuple[str, ...], outside_ok: bool) -> None:
    """`enter_repo`, once git has told the repository's top (`found`, None outside every repository)."""
    cwd = Path.cwd()
    _refuse_empty_paths(args, path_attrs)
    for attr in file_attrs:
        value = getattr(args, attr, None)
        if value:
            setattr(args, attr, str((cwd / value).resolve()))
    if not found:
        if outside_ok:
            return
        raise NoRepositoryError(git.no_repository_problem(getattr(args, "command", None)))
    top = Path(found)
    for attr in path_attrs:
        value = getattr(args, attr, None)
        if isinstance(value, list) and value:  # paths or globs, such as `aidd risk --paths`
            args.planned = planned_readings(value, top, cwd)
            setattr(args, attr, args.planned.every)
        # A work item's id stays as typed, unless a file has that name.
        elif isinstance(value, str) and value and not (workitems.WORK_ID.fullmatch(value) and not (cwd / value).exists()):
            try:
                one = planned_readings([value], top, cwd)
            except ValueError:
                continue  # a path outside stays as typed, for the command that reads it to refuse
            args.planned = one
            setattr(args, attr, one.scope[0])
    os.chdir(top)


def enter_where_it_runs(args) -> tuple[str | None, bool]:
    """For `aidd risk`: the folder its command line runs in, and whether no repository holds this folder. The folder is
    read before aidd moves to a repository's top, for its git state only: "." here, or --folder's checkout, or None for
    a --folder that is no git checkout, which is another repository to aidd, so the command reads no branch there, and
    asks. Outside every repository no branch can be read, so the answer comes from the rules in this folder, with a note
    that says why. A --folder that names a checkout moves aidd to that checkout's top, from inside a repository or
    outside one, so its config decides, as it does when the command runs from inside it."""
    folder = getattr(args, "folder", None)
    _refuse_empty_paths(args, ("paths",))
    top = git.repository_top()
    outside = top is None
    where: str | None = None if outside else "."
    if folder:
        found = Path(folder).resolve()
        inside = found.is_dir() and git.run(["rev-parse", "--is-inside-work-tree"], str(found), check=False).strip() == "true"
        where = str(found) if inside else None
    if folder and where:
        os.chdir(git.repository_top(where) or where)
        outside = False
    elif not outside:
        _enter_top(args, top, ("paths",), (), False)  # the top git just told, read once; a path typed in a subfolder is read from there
    return where, outside


def repo_relative(path: Path) -> str:
    """A path as printed after `enter_repo`: relative to the repository root when it is inside it, else as given."""
    p = path.resolve()
    here = Path.cwd().resolve()
    return p.relative_to(here).as_posix() if p.is_relative_to(here) else str(path)


_PERSON = re.compile(
    r"^(?:@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?"  # @user or @org/team
    r"|email:[^@\s,]+@[^@\s,]+\.[^@\s,]+"  # email:you@example.com
    r"|[A-Za-z0-9][A-Za-z0-9_.-]*)$"  # a bare login
)


def approvers(values: list[str] | None) -> list[str] | None:
    """--approvers as people type it: each flag takes one person or several joined by commas (`--approvers "@a,@b"`), each a person."""
    if not values:
        return values
    out = [v.strip() for value in values for v in value.split(",") if v.strip()]
    bad = [v for v in out if not _PERSON.match(v) or config.approver_is_agent(v)]
    if bad:
        raise ValueError(
            f"--approvers: {', '.join(repr(b) for b in bad)} is not a person; write the person's `@handle` (or @org/team, email:you@example.com, or a login)"
        )
    return list(dict.fromkeys(out))


# What to do about a person that follows `--approvers` or `--specialist` bare: each flag takes one value.
REPEAT_FLAG = {
    "--approvers": "repeat --approvers for each person, or join them with commas",
    "--specialist": "repeat --specialist for each pool, or join its people with commas",
}


def stray_person_hint(word: str, before: list[str]) -> str:
    """For a bare `@name` or `email:name` that follows an `--approvers` or `--specialist` in `before` (the words typed), the
    way to give more than one; else "". Both flags take one value each time, so the word is a stray, or it was read as the path."""
    flag = next((f for f in reversed(before) if f.split("=", 1)[0] in REPEAT_FLAG), None)
    return f" {REPEAT_FLAG[flag.split('=', 1)[0]].capitalize()}." if flag and word.startswith(("@", "email:")) else ""


def specialists(entries: list[str] | None) -> dict[str, list[str]]:
    """--specialist security=@org/security,@alice -> {"security": ["@org/security", "@alice"]}."""
    out: dict[str, list[str]] = {}
    pools = sorted(set(config.POOL_OF.values()))  # the pools a change's risk dimensions name; any other is never asked
    for entry in entries or []:
        pool, sep, who = entry.partition("=")
        if not sep or not pool.strip() or not who.strip():
            raise ValueError(f"--specialist takes POOL=WHO[,WHO], got {entry!r}")
        if pool.strip() not in pools:
            raise ValueError(
                f"--specialist {pool.strip()!r} is not a pool aidd asks. {did_you_mean(pool.strip(), pools) or 'The pools: ' + ', '.join(pools) + '.'}"
            )
        out.setdefault(pool.strip(), []).extend(w.strip() for w in who.split(",") if w.strip())
    return out


def prototype_reading(args) -> list[str]:
    """The prototype tool's command that prints what it reads from a design, for `aidd prototype --components`, `--screens`,
    `--shots` with the options that size it, or `--stories`; empty for any other. The sizing options go with `--shots` only."""
    sizing = [f"--changed-screen={s}" for s in args.changed_screen or []] + [f"--changed-component={c}" for c in args.changed_component or []]
    if (sizing or args.frames) and not args.shots:
        raise ValueError("--changed-screen, --changed-component, and --frames size the fidelity pass's views: add --shots to list them")
    reads = {"shots": ["shots", *sizing, f"--frames={args.frames}"], "stories": ["stories", args.stories], "screens": ["screens"], "components": ["components"]}
    return next((command for flag, command in reads.items() if getattr(args, flag)), [])


NO_ENVIRONMENT = "none"
NO_HARNESS = "none"
TAG_REF = "refs/tags/"
BRANCH_REF = "refs/heads/"


def _environment_entry(entry: str, flag: str) -> tuple[str, str, str]:
    """`NAME=REF` as (name, "branches" or "tags", ref): `main` and `refs/heads/main` are branches, `refs/tags/v*` is a tag glob."""
    name, sep, ref = (part.strip() for part in entry.partition("="))
    ref = ref.removeprefix(BRANCH_REF) if ref.startswith(BRANCH_REF) else ref
    ref_type, glob = ("tags", ref.removeprefix(TAG_REF)) if ref.startswith(TAG_REF) else ("branches", ref)
    if name == NO_ENVIRONMENT:
        raise ValueError(
            f"{flag}: `{NO_ENVIRONMENT}` is reserved to say no push deploys (--environment {NO_ENVIRONMENT}), so name the environment something else"
        )
    if not sep or json_schema.validate({"name": name, ref_type: [glob]}, "config.schema.json#/$defs/environment"):
        raise ValueError(f"{flag} takes NAME=REF, with a lowercase name such as production and a branch such as main or a tag as refs/tags/v*, got {entry!r}")
    return name, ref_type, glob


def harnesses(values: list[str] | None) -> list[str] | None:
    """--harness as given: the coding agents to wire; `--harness none` -> [], the answer that none is wired; no flag -> None,
    detect them. `none` says no coding agent, so it stands alone as `--environment none` does: beside a name it is an
    error that names both, never a name wired while `none` is dropped."""
    if not values:
        return None
    named = list(dict.fromkeys(v for v in values if v != NO_HARNESS))
    if named and NO_HARNESS in values:
        raise ValueError(f"--harness {NO_HARNESS} says no coding agent, so give it alone: it cannot stand beside --harness {', --harness '.join(named)}")
    return named


def environments(entries: list[str] | None, own: list[str] | None = None) -> list[dict] | None:
    """--environment production=main -> [{"name": "production", "branches": ["main"]}]; refs/tags/v* is a tag glob;
    --own-environment dev=dev adds `shared: false`, and its ref names no wildcard; `--environment none` -> [], the
    answer that no push deploys; no flag -> None, the answer unknown. A name repeats to list more refs."""
    if entries and NO_ENVIRONMENT in entries:
        if len(entries) > 1 or own:
            raise ValueError(
                f"--environment {NO_ENVIRONMENT} says no push deploys, so give it alone: it cannot stand beside another --environment or an --own-environment"
            )
        return []
    found: dict[str, dict] = {}
    mine: set[str] = set()
    for flag, values, own_flag in (("--environment", entries, False), ("--own-environment", own, True)):
        for entry in values or []:
            name, ref_type, glob = _environment_entry(entry, flag)
            if own_flag and globs.is_pattern(glob):
                raise ValueError(f"{flag}: {glob!r} has a wildcard, which can match another person's ref, so name the branch or tag of {name} exactly")
            if name in found and (name in mine) != own_flag:
                raise ValueError(f"environment {name} is given to both --environment and --own-environment: give each name to one flag")
            env = found.setdefault(name, {"name": name})
            env[ref_type] = list(dict.fromkeys([*env.get(ref_type, []), glob]))
            if own_flag:
                mine.add(name)
    return [env | ({"shared": False} if env["name"] in mine else {}) for env in found.values()] or None


def counted(count: int, noun: str) -> str:
    """`1 stack`, `3 stacks`."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


def config_or_none() -> config.Config | None:
    """The config, or None when there is none. A config that exists and does not load stops the command, with why and the
    next step: a command that decides never goes on with the built-in rules alone."""
    if not Path(config.CONFIG_PATH).is_file():
        return None
    return config.load_or_stop(config.CONFIG_PATH)


def config_or_none_quiet(args) -> config.Config | None:
    """The config, or None when there is none or it does not load, for a view that shows what it can. A config that exists
    and does not load gets one line on stderr, once for a command, and marks `args`, so the command exits 1 (`cli.app`)."""
    if not Path(config.CONFIG_PATH).is_file():
        return None
    try:
        return config.load_file(config.CONFIG_PATH)
    except (config.ConfigError, documents.DocumentError, OSError) as exc:
        if not getattr(args, "config_unreadable", False):
            print(config.config_load_problem(exc, goes_on=True), file=sys.stderr)
            args.config_finding = config.config_unreadable_finding(exc, goes_on=True)
        args.config_unreadable = True
        return None


def spec_by_id(value: str) -> str:
    """`value` as a Spec or proposal path: itself when it names a file, else, when it is an id (`SPEC-1`, `PROP-3`), the
    one Spec under the specs folder or proposal under the proposals folder whose id it is. Run from the repository root."""
    if Path(value).is_file() or not _SPEC_ID.fullmatch(value) or value.endswith(".md"):
        return value
    cfg = config_or_none()
    folder = (cfg or config.EMPTY).specs_dir
    proposals = (cfg or config.EMPTY).proposals_dir
    named = globs.under(folder, f"{value}.md")
    for path in (named, globs.under(proposals, f"{value}/proposal.md")):
        if Path(path).is_file():
            return path
    found = []
    candidates = [(p, "spec") for p in sorted(Path(folder).glob("*.md"))] + [(p, "proposal") for p in sorted(Path(proposals).glob("*/proposal.md"))]
    for p, item_type in candidates:
        try:
            data, _ = documents.split_front_matter(regular_files.file_text(Path("."), p, documents.MAX_DOCUMENT_BYTES) or "", str(p))
        except (documents.DocumentError, OSError):
            continue
        if data.get("type") == item_type and str(data.get("id")) == value:
            found.append(p.as_posix())
    if len(found) == 1:
        return found[0]
    if found:
        raise ValueError(f"{len(found)} files have the id {value} ({', '.join(found)}); name the file")
    raise ValueError(f"no Spec has the id {value} in {folder}/, and no proposal has it in {proposals}/; name the file, such as {named}")


def tracked_files() -> list[str]:
    """The files git tracks in the repository, for the route over planned paths and globs."""
    return [p for p in git.run(["ls-files", "-z"], check=False).split("\0") if p]


def check_new_team_flags(item_type: str, retired_flag: str, team: str, cfg: config.Config | None) -> None:
    """`aidd new --delivery-team` names the team behind what the command writes. A Spec or an Intent names a team of the config, and
    a proposal, a runbook, or a postmortem does too once the config has `delivery_teams`. `retired_flag` is what the retired `--owner-team`
    held: any value is a ValueError that names its replacement."""
    if retired_flag:
        row = retired_names.row_for("cli_flag", ("--owner-team",))
        raise ValueError(f"--owner-team was retired in {row['retired_in']}: use {row['new']}. {row['note']}" if row else "--owner-team was retired")
    if not team:
        return
    if item_type in config.types_with("backlog") or (cfg is not None and cfg.get("delivery_teams", default={})):
        config.delivery_team(cfg, team)  # a team the config does not name is an error that names the teams
