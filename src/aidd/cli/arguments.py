"""What the commands share: the exit codes, running from the repository root, reading the config, and the flags' values."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, globs, repo_paths, resources

JSON_SCHEMA_VERSION = "1"

# What each exit code means, by command: the table in docs/CLI.md (`aidd gen-docs` reads it through cli_facts). Each row
# is a command and what 0, 1, and 2 mean for it ("" where it never exits so). The table lists the rows in this order.
EXIT_CODES: tuple[tuple[str, tuple[str, str, str]], ...] = (
    ("`test`", ("every command passed (and every new-behavior command failed on the base)", "a test failed", "error")),
    ("`validate`, `doctor`", ("no errors", "an error or a failed check", "error")),
    ("everything else", ("success", "a check failed", "error")),
)

VOCAB = resources.load_json("common.schema.json")["$defs"]
CHANGE_TYPES = VOCAB["change_type"]["enum"]
DIMENSIONS = VOCAB["dimension"]["enum"]

PASS_ENV_HELP = (
    "pass this credential-like variable to the command (repeatable); by default every *TOKEN*, *SECRET*, *PASSWORD*, *_KEY, "
    "and *CREDENTIAL* variable is dropped"
)

# A work item's id as aidd writes one (`SPEC-1`, `PROP-3`): what `enter_repo` leaves as typed.
_WORK_ITEM_ID = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")
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
        raise ValueError(git.no_repository_problem(getattr(args, "command", None)))
    top = Path(found)
    for attr in path_attrs:
        value = getattr(args, attr, None)
        if isinstance(value, list) and value:  # paths or globs, such as `aidd risk --paths`
            args.planned = planned_readings(value, top, cwd)
            setattr(args, attr, args.planned.every)
        elif isinstance(value, str) and value and not (_WORK_ITEM_ID.fullmatch(value) and not (cwd / value).exists()):
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
    """--approvers as people type it: space or comma separated (`--approvers "@a,@b"`), each a person."""
    if not values:
        return values
    out = [v.strip() for value in values for v in value.split(",") if v.strip()]
    bad = [v for v in out if v.lower().startswith("agent:") or v.lower().endswith("[bot]") or not _PERSON.match(v)]
    if bad:
        raise ValueError(f"--approvers: {', '.join(repr(b) for b in bad)} is not a person; use @user, @org/team, email:you@example.com, or a login")
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


_CONFIG_PROBLEMS_SHOWN: set[tuple[str, str]] = set()


def config_or_none_quiet() -> config.Config | None:
    """The config, or None when there is none or it does not load. A config that exists and does not load gets one line
    on stderr, once in a process: what is wrong, and the next step."""
    try:
        return config_or_none()
    except (config.ConfigError, documents.DocumentError, OSError) as exc:
        reason = documents.one_line((str(exc).strip().splitlines() or [type(exc).__name__])[0], 120)
        line = f"aidd: {config.CONFIG_PATH} does not load ({reason}), so this command goes on without it. Run `aidd validate` to see what to fix."
        key = (os.path.realpath(os.getcwd()), line)
        if key not in _CONFIG_PROBLEMS_SHOWN:
            _CONFIG_PROBLEMS_SHOWN.add(key)
            print(line, file=sys.stderr)
        return None


def spec_by_id(value: str) -> str:
    """`value` as a Spec or proposal path: itself when it names a file, else, when it is an id (`SPEC-1`, `PROP-3`), the
    one Spec under the specs folder or proposal under the proposals folder whose id it is. Run from the repository root."""
    if Path(value).is_file() or not _SPEC_ID.fullmatch(value) or value.endswith(".md"):
        return value
    cfg = config_or_none_quiet()
    folder = cfg.specs_dir if cfg else "specs"
    proposals = cfg.proposals_dir if cfg else "proposals"
    named = globs.under(folder, f"{value}.md")
    for path in (named, globs.under(proposals, f"{value}/proposal.md")):
        if Path(path).is_file():
            return path
    found = []
    candidates = [(p, "spec") for p in sorted(Path(folder).glob("*.md"))] + [(p, "proposal") for p in sorted(Path(proposals).glob("*/proposal.md"))]
    for p, item_type in candidates:
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), str(p))
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
