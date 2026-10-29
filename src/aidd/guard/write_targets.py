"""The obvious writes of a shell command (redirections, tee, cp, mv, sed -i, patch, and the like), each judged
as an edit of its target.
"""

from __future__ import annotations

import fnmatch
import os
import posixpath
import re
from collections.abc import Callable
from pathlib import Path

from aidd import config, workitems
from aidd.guard import (
    delegation,
    dialects,
    edit_check,
    helper_runs,
    indirect_runs,
    path_location,
    program_options,
    repo_config,
    role_areas,
    shell_parser,
    verdicts,
)
from aidd.kernel import git

_IGNORED_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "-", ""}


def _patch_targets(text: str, strip: int, git_style: bool) -> list[str]:
    targets = []
    for line in text.splitlines():
        if line.startswith(("+++ ", "--- ")):
            path = line[4:].split("\t", 1)[0].strip()
            if path in ("/dev/null", ""):
                continue
            parts = path.split("/")
            parts = parts[1:] if git_style and parts[0] in ("a", "b") else parts[strip:]
            if parts:
                targets.append("/".join(parts))
    return list(dict.fromkeys(targets))


# Codex's patch format (its `apply_patch` tool, OpenCode's `apply_patch`): each file it adds, changes, deletes, or moves to.
_PATCH_FILE_LINE = re.compile(r"(add file|update file|delete file|move to)\s*:\s*(.+)", re.I | re.S)
_PATCH_MARKS = frozenset({"begin patch", "end patch", "end of file"})
_HIDING = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")


def apply_patch_targets(text: str) -> list[str] | None:
    """The files a patch in Codex's format writes, in order, each once; None when a `***` line is one the check
    cannot read, or holds a control or an invisible character, since the harness's own parser might take it as
    another file. Each line is read stripped of any whitespace, Unicode's included."""
    targets: list[str] = []
    for line in text.split("\n"):  # as the harnesses split a patch: on a newline alone, one CR dropped
        stripped = line.removesuffix("\r").strip()
        if not stripped.startswith("***"):
            continue
        if _HIDING.search(stripped):
            return None  # a control or a line separator inside a header could read one way here and another there
        body = stripped[3:].strip()
        if " ".join(body.lower().split()) in _PATCH_MARKS:
            continue
        m = _PATCH_FILE_LINE.fullmatch(body)
        if not m or not m.group(2).strip():
            return None
        targets.append(m.group(2).strip())
    return list(dict.fromkeys(targets))


# Writers whose own targets (not their redirects) only add, remove, or rename a name: the file under another hard link
# keeps its content.
_NAME_ONLY = frozenset({"rm", "unlink", "rmdir", "mv", "ln", "link"})


def _short_flag(args: list[str], letter: str, long: str, past_values: bool = False) -> bool:
    """Whether `ln` or `cp` args hold the option `letter` or `long` (program_options.has_option): read either way, or with
    `past_values` only past the values of `-S` and `-t`, as GNU reads them, for ln's hard links (`ln -S -s` makes one)."""
    values = ("St", ("--suffix", "--target-directory"))
    return program_options.has_option(args, letter, long, values) or (not past_values and program_options.has_option(args, letter, long))


def _write_targets(sc: shell_parser.SimpleCommand, cwd: Path) -> tuple[list[str], list[str]]:
    """(paths a simple command writes, reasons it cannot tell) — best-effort, for the obvious writers only. A hard
    link's source counts as written (`ln`, `link`, `cp -l`), and a symbolic one `cp -s` makes: the new name writes the
    same file."""
    argv = shell_parser.program_argv(sc.argv)
    targets = list(sc.out)
    unknown: list[str] = []
    if not argv:
        return targets, unknown
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    plain = [a for a in args if not a.startswith("-")]
    for rest in shell_parser.aidd_runs(argv):
        # `aidd revise <ID>` writes the Spec (its `revisions`, which void the approval): judged as an edit of the Spec.
        words = program_options.positional_words(rest, set())
        if words[:1] == ["revise"] and len(words) > 1:
            targets.append(_spec_file(words[1], cwd))
    if name == "link":
        return targets + plain, unknown
    if name == "tee":
        targets += plain
    elif name == "sed":
        inplace = any(
            a in ("-i", "--in-place") or a.startswith(("-i", "--in-place=")) or (a[:1] == "-" and a[1:2] != "-" and "i" in a[1:] and a[1:].isalpha())
            for a in args
        )
        if inplace:
            # BSD sed (macOS) takes the backup suffix as the next word: `sed -i '' 's/x/y/' f` keeps no backup.
            args = [a for k, a in enumerate(args) if not (a == "" and k and args[k - 1] == "-i")]
            has_script_flag = any(a in ("-e", "-f", "--expression", "--file") or a.startswith(("--expression=", "--file=")) for a in args)
            words = program_options.positional_words(args, {"-e", "-f", "--expression", "--file"})
            targets += words if has_script_flag else words[1:]
    elif name in ("cp", "mv", "install", "ln"):
        dest = program_options.flag_value(args, "-t", "--target-directory")
        sources = plain if dest else plain[:-1]
        dest = dest or (plain[-1] if len(plain) >= 2 else None)
        if dest:
            d = (cwd / dest) if not os.path.isabs(dest) else Path(dest)
            targets += [str(d / os.path.basename(s)) for s in sources] if d.is_dir() else [dest]
        links = _short_flag(args, "l", "--link") or _short_flag(args, "s", "--symbolic-link")
        if name == "mv" or (name == "ln" and not _short_flag(args, "s", "--symbolic", past_values=True)) or (name == "cp" and links):
            targets += sources
    elif name in ("rm", "touch", "truncate", "shred", "unlink", "rmdir"):
        targets += program_options.positional_words(args, {"-s", "--size", "-r", "--reference"}) if name == "truncate" else plain
        if name in ("rm", "rmdir") and any(_is_top(cwd, p) for p in plain):
            targets += _person_only_files(cwd)  # removing the top removes the config and the wiring with it
    elif name == "dd":
        targets += [a[3:] for a in args if a.startswith("of=")]
    elif name in indirect_runs.FIND_LIKE:
        targets += _find_targets(args, cwd)
    elif (
        name == "git"
        and program_options.positional_words(args, {"-C", "-c"})[:1] in (["checkout"], ["restore"])
        and not program_options.restore_writes_index_only(args[args.index(program_options.positional_words(args, {"-C", "-c"})[0]) :])
    ):
        # `git checkout <ref> -- <paths>` and `git restore <paths>` write the named files from another commit.
        at = args.index(program_options.positional_words(args, {"-C", "-c"})[0])
        rest, base = args[at + 1 :], program_options.flag_value(args[:at], "-C")
        if any(_reads_pathspecs(a) for a in rest):
            targets.append("*")  # the paths are in a file the check does not read: any file may be among them
        source = program_options.flag_value(rest, "-s", "--source") if args[at] == "restore" else None
        if "--" in rest:
            paths = rest[rest.index("--") + 1 :]
            if args[at] == "checkout":
                source = next(iter(program_options.positional_words(rest[: rest.index("--")], {"-b", "-B", "--orphan"})), None)
        elif args[at] == "restore":
            paths = program_options.positional_words(rest, {"-s", "--source"})
        else:
            words = program_options.positional_words(rest, {"-b", "-B", "--orphan"})
            # A first word that names a file here is a path (`git checkout <file>` restores it from the index); else
            # it is the branch or commit, and the words after it are the paths it restores.
            first = (cwd / base / words[0]) if words and base else (cwd / words[0]) if words else None
            is_ref = bool(words) and git.ok(["rev-parse", "--verify", "--quiet", f"{words[0]}^{{commit}}"], str(cwd / base if base else cwd))
            paths = words if first is not None and (first.exists() or not is_ref) else words[1:]
            source = words[0] if words and paths is not words else None
        targets += _pathspecs(paths, base) + _person_only_files_changed(cwd / base if base else cwd, paths, source)
    elif name == "git" and program_options.positional_words(args, {"-C", "-c"})[:1] in (["rm"], ["mv"]):
        # `git rm <paths>` and `git mv <paths> <dest>` remove or rename files, as rm and mv do.
        at = args.index(program_options.positional_words(args, {"-C", "-c"})[0])
        base = program_options.flag_value(args[:at], "-C")
        if any(_reads_pathspecs(a) for a in args[at + 1 :]):
            targets.append("*")  # the paths are in a file the check does not read: any file may be among them
        targets += _pathspecs([a for a in args[at + 1 :] if not a.startswith("-")], base)
    elif name == "git" and any(_names_output(a) for a in args):
        # `git diff|log|show --output=<file>` writes its output to that file; git takes the option abbreviated too
        # (`--outp=<file>`), and from a `-C` folder.
        # The path as written, and under each folder a `-C` may name (git joins several in turn): reading every one,
        # never only the right one, so a misread option can only add a target, never hide one (`git diff -C` detects
        # copies, and takes no folder).
        named = [a.split("=", 1)[1] for a in args if _names_output(a) and "=" in a]
        named += [args[i + 1] for i, a in enumerate(args[:-1]) if _names_output(a) and "=" not in a]
        folders = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "-C"]
        bases = folders + ([str(Path(*folders))] if len(folders) > 1 else [])
        targets += named + [str(Path(b) / p) for b in bases for p in named if not os.path.isabs(p)]
    elif name in ("patch",) or (name == "git" and args[:1] == ["apply"]):
        git_style = name == "git"
        files = [a for a in (args[1:] if git_style else args) if not a.startswith("-")]
        if git_style:
            files = files or sc.inp
        else:
            files = [f for f in files if f.endswith((".diff", ".patch"))] or sc.inp or [f for f in (program_options.flag_value(args, "-i", "--input"),) if f]
        strip = int(program_options.flag_value(args, "-p") or (1 if git_style else 0)) if (program_options.flag_value(args, "-p") or "0").isdigit() else 0
        if not files:
            unknown.append(f"`{name}` reads the patch from a pipe, so its target files are unknown")
        for f in files:
            try:
                text = ((cwd / f) if not os.path.isabs(f) else Path(f)).read_text(encoding="utf-8", errors="replace")
            except OSError:
                unknown.append(f"cannot read the patch {f} to see which files it changes")
                continue
            targets += _patch_targets(text, strip, git_style and strip == 1)
    return targets, unknown


# find's actions that write the file named by their next word, its options before the starting points (`-D` takes a
# value), its operators, and git's and aidd's own file names in a git directory, which a find pattern must not match.
_FIND_WRITES = frozenset({"-fprint", "-fprint0", "-fprintf", "-fls"})
_FIND_OPERATORS = frozenset({"(", ")", "\\(", "\\)", "!", "\\!", ",", "-o", "-or", "-not"})
_FIND_ACTIONS = indirect_runs.FIND_ALL_RUNS | _FIND_WRITES | {"-delete"}


def _find_parts(args: list[str]) -> tuple[list[str], list[str], list[str]]:
    """find's `args` as (its options before the starting points, the starting points, the expression)."""
    i = 0
    while i < len(args) and (args[i] in ("-H", "-L", "-P", "-D") or args[i].startswith("-O")):
        i += 2 if args[i] == "-D" else 1
    j = i
    while j < len(args) and not args[j].startswith("-") and args[j] not in _FIND_OPERATORS:
        j += 1
    return args[:i], args[i:j] or ["."], args[j:]


def _find_targets(args: list[str], cwd: Path) -> list[str]:
    """What find writes by itself: the file after `-fprint`, `-fprint0`, `-fprintf`, and `-fls`, and with `-delete`, or
    a pattern the shell may expand into an action (indirect_runs.find_glob_injects), every file under each starting
    point, unless what it finds is bound to a name (find_input_bound)."""
    _, starts, expr = _find_parts(args)
    targets = [expr[k + 1] for k, a in enumerate(expr[:-1]) if a in _FIND_WRITES]
    injects = indirect_runs.find_glob_injects(args)
    if "-delete" in expr or injects:
        bound = None if injects else find_input_bound(args, cwd)
        targets += bound if bound is not None else [p for s in starts for p in (s, f"{s.rstrip('/') or '/'}/*")]
    return targets


def find_input_bound(args: list[str], cwd: Path) -> list[str] | None:
    """The patterns every path find acts on matches, or None when the guard cannot bound them: a starting point and
    one `-name` or `-iname` test before any action, with no operator, no `-L`, and no pattern the shell may expand
    (find_glob_injects); a quoted glob is find's own. So `find . -name cache.db -exec rm {} \\;` writes only
    files named cache.db. None too when the name may be a file in a git directory under a starting point, or one git
    or aidd keeps there: only git and aidd write there."""
    options, starts, expr = _find_parts(args)
    if "-L" in options or "-follow" in expr or _FIND_OPERATORS & set(expr) or indirect_runs.find_glob_injects(args):
        return None
    inside = {j for _, start, end in indirect_runs.find_clauses(expr) for j in range(start, end if end is not None else len(expr))}
    tests = [j for j, a in enumerate(expr) if a in indirect_runs.FIND_PATTERNS and j not in inside]
    first_action = next((j for j, a in enumerate(expr) if a in _FIND_ACTIONS), len(expr))
    if len(tests) != 1 or expr[tests[0]] not in ("-name", "-iname") or tests[0] + 1 >= first_action:
        return None
    pattern, fold = expr[tests[0] + 1], expr[tests[0]] == "-iname"
    if any(_UNEXPANDED.search(w) or _BRACES.search(w) or w.startswith("~") for w in (*starts, pattern)) or any(c in s for s in starts for c in "*?["):
        return None
    if _may_find_in_git_dir(starts, pattern, fold, cwd):
        return None
    fold_case = str.casefold if fold else str
    named = [s for s in starts if fnmatch.fnmatchcase(fold_case(posixpath.basename(s.rstrip("/"))), fold_case(pattern))]
    return [f"{s.rstrip('/') or '/'}/*{pattern}" for s in starts] + named  # a starting point is found too, when it matches


def _may_find_in_git_dir(starts: list[str], pattern: str, fold: bool, cwd: Path) -> bool:
    """Whether a find `-name` pattern may match a file in a git directory find walks from `starts`: a name git or aidd
    keeps there, or one there now (the object store aside, whose names are hashes). Fails closed on any error."""
    pat = pattern.casefold() if fold else pattern

    def matches(name: str) -> bool:
        return fnmatch.fnmatchcase(name.casefold() if fold else name, pat)

    if any(matches(n) for n in path_location.GIT_OWN_NAMES):
        return True
    try:
        here_top = git.run(["rev-parse", "--show-toplevel"], str(cwd), check=False).strip()
        for s in starts:
            start = (cwd / s).resolve()
            tops = {here_top, git.run(["rev-parse", "--show-toplevel"], str(start), check=False).strip() if start.is_dir() else ""} - {""}
            # Each git directory git names, also one kept outside the work tree (`--separate-git-dir`, a bare repository).
            for gitdir in {d for top in tops for d in (Path(top).resolve() / ".git", *path_location.git_dirs(top))}:
                if gitdir == start or gitdir in start.parents:
                    return True  # it starts inside the git directory
                if gitdir.is_dir() and start in (gitdir.parent, *gitdir.parents) and _names_in(gitdir, matches):
                    return True
    except OSError:
        return True
    return False


def _names_in(gitdir: Path, matches) -> bool:
    """Whether any file or folder in `gitdir`, past its object stores, has a name `matches` accepts."""
    for _, folders, files in os.walk(gitdir, onerror=_raise):
        folders[:] = [f for f in folders if f not in ("objects", "lfs")]
        if any(matches(n) for n in (*folders, *files)):
            return True
    return False


def _raise(error: OSError) -> None:
    raise error


_SHELL_PARTS = re.compile(r"[*?\[{~$`]")


def _is_top(cwd: Path, path: str) -> bool:
    """Whether `path`, from `cwd`, names the top of the repository that holds it."""
    top = git.run(["rev-parse", "--show-toplevel"], str(cwd), check=False).strip()
    try:
        return bool(top) and (cwd / path).resolve() == Path(top).resolve()
    except OSError:
        return False


def _person_only_files(cwd: Path) -> list[str]:
    """The person-only files (the config and the guard's wiring) of the repository that holds `cwd`, as absolute paths."""
    top = git.run(["rev-parse", "--show-toplevel"], str(cwd), check=False).strip()
    return [str(Path(top) / f) for f in (config.CONFIG_PATH, *edit_check.GUARD_WIRING)] if top else []


def _person_only_files_changed(cwd: Path, paths: list[str], source: str | None) -> list[str]:
    """For `git checkout` or `git restore` of the repository's top: each person-only file the source (a commit, or the index)
    holds otherwise than the working tree, which the command would write. The files as they are stay unwritten."""
    if not any(p == ":/" or _is_top(cwd, p) for p in paths):
        return []
    tree = None
    if source:
        # The command's own word, resolved first: never handed to git as an option (`-s --output=<file>`).
        tree = git.run(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{source}^{{tree}}"], str(cwd), check=False).strip()
        if not tree:
            return _person_only_files(cwd)  # a source the check cannot read may hold any of them
    return [f for f in _person_only_files(cwd) if not git.ok(["diff", "--quiet", *([tree] if tree else []), "--", f], str(cwd))]


def _reads_pathspecs(arg: str) -> bool:
    """Whether a git option reads its paths from a file: `--pathspec-from-file`, or any abbreviation git takes of it
    (any `--pathspec...` option, `--pathspec-file-nul` aside, fails closed)."""
    name = arg.split("=", 1)[0]
    return name.startswith("--pathspec") and name != "--pathspec-file-nul"


def _pathspecs(paths: list[str], base: str | None) -> list[str]:
    """git's pathspecs as write targets, under a `-C` folder. One with magic (`:(glob)...`, `:/`) may name any file, so
    it reads as `*`."""
    return ["*" if p.startswith(":") else str(Path(base) / p) if base and not os.path.isabs(p) else p for p in paths]


def _may_name_person_only_file(here: Path, root: str, pattern: str) -> str | None:
    """The person-only file (the config, or the guard's wiring) a pattern written in `here` may name, or None. The shell's
    parts the check does not expand (a variable, a command substitution, a glob, a brace) each match anything, so a
    bare `$F` may name every file; an absolute pattern is matched against the files' absolute paths."""
    try:
        top = Path(root).resolve()
        base = here.resolve().relative_to(top).as_posix()
    except (OSError, ValueError):
        return None
    # A new temporary file is never a person-only file, when the target is that file and nothing else.
    loose = "/mktemp" if _MKTEMP.fullmatch(pattern) else _UNEXPANDED.sub("*", pattern)
    if ".." in loose.split("/"):
        return config.CONFIG_PATH  # a `..` after an unexpanded part may lead anywhere
    pat = re.sub(r"\{[^{}]*\}", "*", posixpath.normpath(loose if loose.startswith(("/", "*")) else posixpath.join(base, loose))).casefold()
    for held in (config.CONFIG_PATH, *edit_check.GUARD_WIRING):
        for name in (held.casefold(), (top / held).as_posix().casefold()):
            if fnmatch.fnmatchcase(name, pat) or fnmatch.fnmatchcase(name, pat.rstrip("/") + "/*"):
                return held
    return None


# `$(mktemp)` with options and plain words only: any shell character in it may run something else.
_MKTEMP = re.compile(r"\$\(\s*mktemp(?:\s+[\w./=-]+)*\s*\)|`\s*mktemp(?:\s+[\w./=-]+)*\s*`")
# A shell part the check does not expand: `$NAME`, `${...}`, `$(...)`, or backticks.
_UNEXPANDED = re.compile(r"\$\{[^}]*\}|\$\([^)]*\)|\$\w+|`[^`]*`")


def _names_output(arg: str) -> bool:
    """Whether a git argument is `--output`, whole or abbreviated as git accepts it (`--ou`, `--outp=<file>`)."""
    name = arg.split("=", 1)[0]
    return len(name) >= 4 and "--output".startswith(name)


def _spec_file(value: str, cwd: Path) -> str:
    """The Spec file `aidd revise` writes, resolved as the CLI resolves it (workitems.revise_target)."""
    top, _ = path_location.repo_top(cwd)
    cfg = repo_config.load_config(top) if top and repo_config.is_adopted(top) else None
    return str(workitems.revise_target(value, top=Path(top) if top else cwd, cwd=cwd, specs_dir=cfg.specs_dir if cfg else "specs"))


def shell_writes(root: str | None, cwd: str, command: str, event: dict) -> verdicts.Verdict:
    """(decision, reason) for the obvious shell writes of `command`, each judged in the repository that holds its
    target (`delegation.judge_write`). A target the check cannot read (a patch from a pipe, an unexpanded `$VAR` or glob), or a
    command it cannot read whole, is denied where the guard holds the actor in `root`. A `cd` inside a subshell group
    or a child shell ends with it. A command with a here-document is read twice, with the bodies and without them, so
    a body's text can neither hide a write nor shift the groups."""
    held = delegation.holds(root, event) if root else False
    cfg = repo_config.load_config(root) if root else None
    # A helper runs only reads where enforce mode holds edits; in advisory mode it works as the main session does.
    helper = held and role_areas.is_read_only_subagent(event, cfg) and (cfg is None or workitems.edits_held(cfg, root or "."))
    worst: verdicts.Decision = "allow"
    reasons: list[str] = []
    broken: list[str] = []
    # What a helper may not run on this line, denied once at the end with the reads it may (helper_runs.denial).
    unread = [helper_runs.POWERSHELL] if helper and event.get("tool_name") == "PowerShell" else []
    stripped, _ = shell_parser.split_heredocs(command)
    for text in dict.fromkeys((command, stripped)):
        dirs = [(Path(cwd), Path(cwd))]  # per group: (the folder, the one `cd -` returns to)
        # The line's own plain assignments (`D=.git/refs`), read with each `cd` into a second folder (`dirs` as the
        # shell may see it), so `$D/x` names a file inside the git directory. A guess, since `read` or a subshell can
        # change a value: it only ever adds the git directory's denial, and never allows a write.
        known: dict[str, str] = {}
        guessed = [Path(cwd)]
        links: dict[str, str] = {}  # each link a command on the line makes, which the disk holds only once it runs
        for sc in shell_parser.simple_commands(text, broken=broken, quoting=event.get("tool_name") != "PowerShell"):
            dirs = (dirs + [dirs[-1]] * sc.depth)[: sc.depth + 1]
            guessed = (guessed + [guessed[-1]] * sc.depth)[: sc.depth + 1]
            here = dirs[-1][0]
            argv = shell_parser.program_argv(sc.argv)
            if helper and (what := helper_runs.unread_code(sc)):
                unread.append(what)
            if not argv and not sc.out:
                known.update(_assignments(sc.argv, known))
                continue
            if argv and shell_parser.program_name(argv[0]) == "cd":
                guessed[-1] = shell_parser.cd_target(guessed[-1], guessed[-1], [_expanded(a, known) for a in argv[1:]])
                dirs[-1] = (shell_parser.cd_target(here, dirs[-1][1], argv[1:]), here)
                continue
            if held and _opaque(sc, argv):
                worst = "deny"
                reasons.append(OPAQUE)
            if argv and shell_parser.program_name(argv[0]) in _PATCH_PROGRAMS:
                for decision, reason in _shell_patch_verdicts(command, here, root, event):
                    worst = decision
                    reasons.append(reason)
            found = _target_verdicts(sc, argv, (here, guessed[-1]), root, event, held, known, rewrite=_through_links(links, here))
            links.update(_links_made(argv, here))
            for decision, reason in found + _indirect_verdicts(sc, argv, here, _judge_with(guessed[-1], root, event, held, dict(known))):
                worst = decision
                reasons.append(reason)
    if unread:
        worst = "deny"
        reasons.append(helper_runs.denial(unread))
    if held and _substitutes_a_program(command):
        worst = "deny"
        reasons.append(OPAQUE)
    if broken and held:
        worst = "deny"
        reasons.append(f"the shell check cannot read all of the command ({broken[0][:80]}); write it plainly, so its targets can be checked")
    return worst, "; ".join(dict.fromkeys(reasons)) or "no shell write the guard can see"


def _links_made(argv: list[str], here: Path) -> dict[str, str]:
    """The symbolic links `ln -s` makes: each link's path, and the path it points to (`*` when only the shell names it)."""
    if not argv or shell_parser.program_name(argv[0]) != "ln" or not _short_flag(argv[1:], "s", "--symbolic"):
        return {}
    plain = [a for a in argv[1:] if not a.startswith("-")]
    sources, dest = (plain[:-1], plain[-1]) if len(plain) > 1 else (plain, ".")
    into = len(sources) > 1 or (here / dest).is_dir()
    links = {os.path.normpath(here / dest / os.path.basename(s) if into else here / dest): s for s in sources}
    return {link: "*" if _SHELL_PARTS.search(s) else os.path.normpath(Path(link).parent / s) for link, s in links.items()}


def _through_links(links: dict[str, str], here: Path) -> Rewrite | None:
    """A rewrite of each target into itself and the path it names through each link an earlier command on the line
    made (`ln -s .git g && echo x > g/HEAD`), which the disk does not hold yet when the guard reads the line."""
    if not links:
        return None

    def rewrite(target: str) -> list[str]:
        path = os.path.normpath(target if os.path.isabs(target) else here / target)
        through = [(to, path[len(link) :].lstrip(os.sep)) for link, to in links.items() if path == link or path.startswith(link + os.sep)]
        return [target] + [f"*/{rest}" if to == "*" else os.path.join(to, rest) for to, rest in through]

    return rewrite


# Codex's patch program, run from a shell (`apply_patch <<'EOF'`): its patch is in the command's own text.
_PATCH_PROGRAMS = frozenset({"apply_patch", "applypatch"})
UNREAD_PATCH = (
    "the guard cannot read which files this patch writes; send each file as `*** Add File: <path>`, `*** Update File: <path>`, or `*** Delete File: <path>`"
)


def _shell_patch_verdicts(command: str, here: Path, root: str | None, event: dict) -> list[verdicts.Verdict]:
    """The denials for a patch program a shell runs: each file the command's patch text names, judged as an edit of
    it, or a denial when the guard reads no file in it."""
    targets = apply_patch_targets(command)
    if not targets:
        return [("deny", UNREAD_PATCH)]
    found: list[verdicts.Verdict] = []
    for t in targets:
        if root and _in_git_dir(here, t, root):
            found.append(("deny", f"patch of {t}: {GIT_DIR}"))
            continue
        verdict = delegation.judge_write(Path(t) if os.path.isabs(t) else here / t, root, event)
        if verdict is not None and verdict[0] != "allow":
            found.append((verdict[0], f"patch of {t}: {verdict[1]}"))
    return found


GIT_DIR = "it is inside the git directory, where only git and aidd commands write. Run the git or aidd command that changes it"
OPAQUE = "this command runs code the guard cannot read; use the Edit or Write tool, or split the command"
# A command substitution or backticks where a command starts: what runs is known only when the shell runs it.
_SUBSTITUTED_PROGRAM = re.compile(r"(?:^|[;&|\n(]|\b(?:then|do|else)\b)\s*(?:[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])?\+?=\S*\s+)*\"?(?:\$\(|`)")
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_BRACES = re.compile(r"\{[^{}]*(?:,|\.\.)")  # no `}` needed: one pass over a word, and an unclosed brace fails closed
_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
_VARIABLE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def _expanded(word: str, known: dict[str, str]) -> str:
    """`word` with the variables the line itself set plainly put in; any other expansion stays as written."""
    return _VARIABLE.sub(lambda m: known.get(m.group(1) or m.group(2), m.group(0)), word)


def _assignments(words: list[str], known: dict[str, str]) -> dict[str, str]:
    """The plain values a command of assignments alone sets (`D=.git/refs; P=$D/aidd`)."""
    found: dict[str, str] = {}
    for w in words:
        m = _ASSIGNMENT.match(w)
        if m:
            found[m.group(1)] = _expanded(m.group(2), {**known, **found})
    return found


def _in_git_dir(here: Path, target: str, root: str) -> bool:
    """Whether `target`, written from `here`, names a path inside a git directory (`.git/refs/...`, after `cd .git`),
    as written or through a link (`g/HEAD`, with `g` a link to `.git`): a write follows the link. Also one `root`'s
    repository keeps outside its work tree (`git init --separate-git-dir`, a bare repository's worktree)."""
    path = Path(target) if os.path.isabs(target) else here / target
    if any(part.casefold() == ".git" for p in (path, Path(os.path.realpath(path))) for part in p.parts):
        return True
    return path_location.in_git_dir(path, [root])


def _moved_write_denial(folders: tuple[Path, Path], root: str, target: str) -> str | None:
    """Why a relative write after the line's own `cd` is denied, or None: a person-only file in the folder the line's
    assignments name (`D=.aidd; cd $D`), or, in a folder only the shell names (after `cd "$(...)"`, or `*/<target>`),
    a person-only file or a git directory's file under any folder."""
    here, guessed = folders
    if os.path.isabs(target):
        return None
    named = _may_name_person_only_file(guessed, root, target) if guessed != here else None
    moved = guessed.relative_to(root).parts if guessed.is_relative_to(root) else guessed.parts  # not the repository's own path
    rest = target[2:] if target.startswith("*/") else target if any(_SHELL_PARTS.search(p) for p in moved) else None
    if not named and rest is not None:
        named = _may_name_person_only_file(Path(root), root, f"*/{rest}")
        if not named and Path(rest).parts[:1] and Path(rest).parts[0] in path_location.GIT_DIR_TOPS:
            return "it is in a folder only the shell names, which may be a git directory. Only git and aidd commands write there: run the git or aidd command that changes it"
    return f"it may name {named}, which only a person changes; name the files literally" if named else None


def _opaque(sc: shell_parser.SimpleCommand, argv: list[str]) -> bool:
    """Whether a simple command runs a command string the parser never sees (the closed list in the module docstring):
    a shell fed by stdin (a here-string, a here-document, an input file, or a pipe), `trap` with a command, `source` or
    `.`, and a program that runs commands (indirect_runs.RUNS_COMMANDS: `xargs`, `parallel`, `find -exec`, `fd -x`, and their kin), unless what
    xargs or find runs is a literal reader. `exec`, `command`, and `builtin` are followed as wrappers."""
    if not argv:
        return False
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if name in shell_parser.SHELLS:
        inline, at = shell_parser.shell_operand(name, args)
        return not inline and at is None and bool(sc.inp or sc.after in ("|", "|&"))
    if name in shell_parser.POWERSHELLS:
        return not any(a.lower() in ("-c", "-command", "-file", "-f") for a in args) and bool(sc.inp or sc.after in ("|", "|&"))
    if name == "trap":
        pos = [a for a in args if not a.startswith("-") or a == "-"]
        return bool(pos) and pos[0] not in ("", "-") and len(pos) > 1
    if name in ("source", "."):
        return True
    if indirect_runs.runs_a_command(sc):
        # Except a literal read-only program, which the guard reads (indirect_runs).
        return not indirect_runs.runs_only_readers(sc)
    return False


def _substitutes_a_program(command: str) -> bool:
    """A command substitution or backticks in the program position. Here-document bodies and the text inside quotes
    are not commands: a quoted word keeps only its first two characters, so `"$(cmd)" -c ...` is still seen."""
    stripped, _ = shell_parser.split_heredocs(command)
    masked = _QUOTED.sub(lambda m: m.group(0)[:3] + m.group(0)[-1] if m.group(0)[0] == '"' else "''", stripped)
    return bool(_SUBSTITUTED_PROGRAM.search(masked))


Rewrite = Callable[[str], list[str]]
Judge = Callable[[shell_parser.SimpleCommand, list[str], Path, Rewrite], list[verdicts.Verdict]]


def _judge_with(guessed: Path, root: str | None, event: dict, held: bool, known: dict[str, str]) -> Judge:
    """_target_verdicts for a command xargs, find, or their kin run, from the folder it runs in and the line's own context."""

    def judge(inner: shell_parser.SimpleCommand, inner_argv: list[str], folder: Path, rewrite: Rewrite) -> list[verdicts.Verdict]:
        return _target_verdicts(inner, inner_argv, (folder, guessed), root, event, held, known, rewrite=rewrite)

    return judge


def _indirect_verdicts(sc: shell_parser.SimpleCommand, argv: list[str], here: Path, judge: Judge) -> list[verdicts.Verdict]:
    """The denials `judge` gives for what each command xargs, find, or their kin run writes (indirect_runs.indirect_commands),
    with INPUT for each word it fills in. For find, INPUT is bound to the names find acts on, when the guard can bound
    them (find_input_bound). A `cd` inside follows the folder, and a folder only the input names (`find -execdir`, `cd
    "$0"`) may be any folder, so a name written there reads as `*/name`."""
    if not indirect_runs.runs_a_command(sc):
        return []
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    found_dir = name in indirect_runs.FIND_LIKE and bool({"-execdir", "-okdir"} & set(args))
    # find's bound on INPUT, read once, and only when a target needs it (it reads the git directory)
    bounds: dict[str, list[str] | None] = {} if name in indirect_runs.FIND_LIKE and not found_dir else {"": None}
    dirs: list[tuple[Path, bool]] = [(here, found_dir)]  # per level: (the folder, whether only the input names it)
    found: list[verdicts.Verdict] = []
    for inner in indirect_runs.indirect_commands(sc):
        level = max(0, inner.depth - sc.depth)
        dirs = (dirs + [dirs[-1]] * level)[: level + 1]
        inner_argv = shell_parser.program_argv(inner.argv)
        if inner_argv and shell_parser.program_name(inner_argv[0]) == "cd":
            unread = any(_UNEXPANDED.search(a) for a in inner_argv[1:])
            dirs[-1] = (shell_parser.cd_target(dirs[-1][0], dirs[-1][0], inner_argv[1:]), dirs[-1][1] or unread)
            continue
        anywhere = dirs[-1][1]

        def rewrite(target: str, anywhere: bool = anywhere) -> list[str]:
            target = f"*/{target}" if anywhere and not os.path.isabs(target) else target
            if indirect_runs.INPUT not in target:
                return [target]
            if "" not in bounds:
                bounds[""] = find_input_bound(args, here)
            bound = bounds[""]
            return [target] if bound is None else [target.replace(indirect_runs.INPUT, b) for b in bound]

        found += judge(inner, inner_argv, dirs[-1][0], rewrite)
    return found


def _target_verdicts(
    sc: shell_parser.SimpleCommand,
    argv: list[str],
    folders: tuple[Path, Path],
    root: str | None,
    event: dict,
    held: bool,
    known: dict[str, str],
    rewrite: Rewrite | None = None,
) -> list[verdicts.Verdict]:
    """The denials for the write targets of one simple command run from `folders`: the folder the check reads, and
    the one the line's own assignments suggest (`shell_writes`). `rewrite` turns each target into the paths it may
    name (_indirect_verdicts)."""
    here, guessed = folders
    found: list[verdicts.Verdict] = []
    targets, unknown = _write_targets(sc, here)
    name_only = set(targets[len(sc.out) :]) if argv and shell_parser.program_name(argv[0]) in _NAME_ONLY else set()
    if rewrite is not None:
        targets = [r for t in targets for r in rewrite(t)]
        name_only = {r for t in name_only for r in rewrite(t)}
    for u in unknown if held else []:
        found.append(("deny", f"{u}; save the patch to a file and apply that file, so its targets can be checked"))
    for t in targets:
        t = os.path.expanduser(t) if t[:1] == "~" else t  # bash expands a leading ~ before the write; the reader keeps no quotes
        if t in _IGNORED_TARGETS or t.startswith("/dev/"):
            continue
        if root and (why := _moved_write_denial(folders, root, _expanded(t, known))):
            found.append(("deny", f"shell write to {t}: {why}"))
            continue
        if root and (_in_git_dir(here, t, root) or _in_git_dir(guessed, _expanded(t, known), root)):
            # Only git and aidd commands write in the git directory: a ref, HEAD, a hook, or the config written by hand
            # could record a person's decision or switch to a branch where the guard holds nothing.
            found.append(("deny", f"shell write to {t}: {GIT_DIR}"))
            continue
        if "$" in t or "`" in t or any(c in t for c in "*?[") or _BRACES.search(t):
            if root and path_location.may_name_git_file(t):
                found.append(("deny", f"shell write to {t}: {GIT_DIR}"))
                continue
            if why := delegation.harness_record(Path(os.path.expandvars(os.path.expanduser(t)))):
                found.append(("deny", f"shell write to {t}: {why}"))
                continue
            if dialects.HARNESS_RECORDS.search(t.replace("\\", "/") + "/"):
                found.append(("deny", f"shell write to {t}: {delegation.HARNESS_RECORD_DENY.format(path=t)}"))
                continue
            if not held:
                # As written, and as the line's own values guess it: a value may change before the write (`read`).
                if root and (named := _may_name_person_only_file(here, root, t) or _may_name_person_only_file(here, root, _expanded(t, known))):
                    found.append(("deny", f"shell write to {t}: it may name {named}, which only a person changes; name the files literally"))
                continue
            verdict: verdicts.Verdict | None = (
                "deny",
                f"cannot tell which file `{t}` names, because the shell check does not expand it; name the file literally",
            )
        else:
            path = (here / t) if not os.path.isabs(t) else Path(t)
            verdict = delegation.judge_write(path, root, event, content=t not in name_only)
        if verdict is not None and verdict[0] != "allow":
            found.append((verdict[0], f"shell write to {t}: {verdict[1]}"))
    return found
