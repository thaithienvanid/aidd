"""What the commands share: the exit codes, running from the repository root, reading the config, and the flags' values."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git, globs, repo_paths, resources

JSON_SCHEMA_VERSION = "1"

# What each exit code means, by command: the table in docs/CLI.md (`aidd gen-docs` reads it through cli_facts). Each row
# is a command and what 0, 1, and 2 mean for it ("" where it never exits so).
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
    for p, kind in candidates:
        try:
            data, _ = documents.split_front_matter(p.read_text(encoding="utf-8", errors="replace"), str(p))
        except (documents.DocumentError, OSError):
            continue
        if data.get("type") == kind and str(data.get("id")) == value:
            found.append(p.as_posix())
    if len(found) == 1:
        return found[0]
    if found:
        raise ValueError(f"{len(found)} files have the id {value} ({', '.join(found)}); name the file")
    raise ValueError(f"no Spec has the id {value} in {folder}/, and no proposal has it in {proposals}/; name the file, such as {named}")
