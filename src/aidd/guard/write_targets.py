"""The obvious writes of a shell command (redirections, tee, cp, mv, sed -i, patch, and the like), each judged
as an edit of its target.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from aidd import workitems
from aidd.guard import delegation, path_location, repo_config, shell_parser, verdicts

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


def _short_flag(args: list[str], letter: str, long: str) -> bool:
    """Whether `args` hold the short option `letter` (alone or in a cluster such as `-sf`) or the long option `long`."""
    return any(a == long or (a.startswith("-") and not a.startswith("--") and letter in a[1:]) for a in args)


def _write_targets(sc: shell_parser.SimpleCommand, cwd: Path) -> tuple[list[str], list[str]]:
    """(paths a simple command writes, reasons it cannot tell) — best-effort, for the obvious writers only. A hard
    link's source counts as written (`ln`, `link`, `cp -l`): the new name writes the same file."""
    argv = shell_parser.program_argv(sc.argv)
    targets = list(sc.out)
    unknown: list[str] = []
    if not argv:
        return targets, unknown
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    plain = [a for a in args if not a.startswith("-")]
    for rest in shell_parser.aidd_runs(argv):
        # `aidd revise <ID>` writes the Spec (its `revisions`, which void the approval): judged as an edit of the Spec.
        words = shell_parser.positional_words(rest, set())
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
            words = shell_parser.positional_words(args, {"-e", "-f", "--expression", "--file"})
            targets += words if has_script_flag else words[1:]
    elif name in ("cp", "mv", "install", "ln"):
        dest = shell_parser.flag_value(args, "-t", "--target-directory")
        sources = plain if dest else plain[:-1]
        dest = dest or (plain[-1] if len(plain) >= 2 else None)
        if dest:
            d = (cwd / dest) if not os.path.isabs(dest) else Path(dest)
            targets += [str(d / os.path.basename(s)) for s in sources] if d.is_dir() else [dest]
        if name == "mv" or (name == "ln" and not _short_flag(args, "s", "--symbolic")) or (name == "cp" and _short_flag(args, "l", "--link")):
            targets += sources
    elif name in ("rm", "touch", "truncate", "shred", "unlink", "rmdir"):
        targets += shell_parser.positional_words(args, {"-s", "--size", "-r", "--reference"}) if name == "truncate" else plain
    elif name == "dd":
        targets += [a[3:] for a in args if a.startswith("of=")]
    elif name == "git" and shell_parser.positional_words(args, {"-C", "-c"})[:1] in (["checkout"], ["restore"]):
        # `git checkout <ref> -- <paths>` and `git restore <paths>` write the named files from another commit.
        at = args.index(shell_parser.positional_words(args, {"-C", "-c"})[0])
        rest, base = args[at + 1 :], shell_parser.flag_value(args[:at], "-C")
        if "--" in rest:
            paths = rest[rest.index("--") + 1 :]
        elif args[at] == "restore":
            paths = shell_parser.positional_words(rest, {"-s", "--source"})
        else:
            paths = shell_parser.positional_words(rest, {"-b", "-B", "--orphan"})[1:]  # one word alone switches branches
        targets += [str(Path(base) / p) if base and not os.path.isabs(p) else p for p in paths]
    elif name in ("patch",) or (name == "git" and args[:1] == ["apply"]):
        git_style = name == "git"
        files = [a for a in (args[1:] if git_style else args) if not a.startswith("-")]
        if git_style:
            files = files or sc.inp
        else:
            files = [f for f in files if f.endswith((".diff", ".patch"))] or sc.inp or [f for f in (shell_parser.flag_value(args, "-i", "--input"),) if f]
        strip = int(shell_parser.flag_value(args, "-p") or (1 if git_style else 0)) if (shell_parser.flag_value(args, "-p") or "0").isdigit() else 0
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
    worst: verdicts.Decision = "allow"
    reasons: list[str] = []
    broken: list[str] = []
    stripped, _ = shell_parser.split_heredocs(command)
    for text in dict.fromkeys((command, stripped)):
        dirs = [(Path(cwd), Path(cwd))]  # per group: (the folder, the one `cd -` returns to)
        # The line's own plain assignments (`D=.git/refs`), read with each `cd` into a second folder (`dirs` as the
        # shell may see it), so `$D/x` names a file inside the git directory. A guess, since `read` or a subshell can
        # change a value: it only ever adds the git directory's denial, and never allows a write.
        known: dict[str, str] = {}
        guessed = [Path(cwd)]
        for sc in shell_parser.simple_commands(text, broken=broken):
            dirs = (dirs + [dirs[-1]] * sc.depth)[: sc.depth + 1]
            guessed = (guessed + [guessed[-1]] * sc.depth)[: sc.depth + 1]
            here = dirs[-1][0]
            argv = shell_parser.program_argv(sc.argv)
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
            for decision, reason in _target_verdicts(sc, argv, (here, guessed[-1]), root, event, held, known):
                worst = decision
                reasons.append(reason)
    if held and _substitutes_a_program(command):
        worst = "deny"
        reasons.append(OPAQUE)
    if broken and held:
        worst = "deny"
        reasons.append(f"the shell check cannot read all of the command ({broken[0][:80]}); write it plainly, so its targets can be checked")
    return worst, "; ".join(dict.fromkeys(reasons)) or "no shell write the guard can see"


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
        if root and _in_git_dir(here, t):
            found.append(("deny", f"patch of {t}: {GIT_DIR}"))
            continue
        verdict = delegation.judge_write(Path(t) if os.path.isabs(t) else here / t, root, event)
        if verdict is not None and verdict[0] != "allow":
            found.append((verdict[0], f"patch of {t}: {verdict[1]}"))
    return found


GIT_DIR = "it is inside the git directory, where only git and aidd commands write. Run the git or aidd command that changes it"
OPAQUE = "this command runs code the guard cannot read; use the Edit or Write tool, or split the command"
# A command substitution or backticks where a command starts: what runs is known only when the shell runs it.
_SUBSTITUTED_PROGRAM = re.compile(r"(?:^|[;&|\n(]|\b(?:then|do|else)\b)\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*\"?(?:\$\(|`)")
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_RUNS_COMMANDS = frozenset({"xargs", "parallel"})
_FIND_RUNS = frozenset({"-exec", "-execdir", "-ok", "-okdir"})
_BRACES = re.compile(r"\{[^{}]*(?:,|\.\.)[^{}]*\}")
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


def _in_git_dir(here: Path, target: str) -> bool:
    """Whether `target`, written from `here`, names a path inside a git directory (`.git/refs/...`, after `cd .git`)."""
    path = Path(target) if os.path.isabs(target) else here / target
    return any(part.casefold() == ".git" for part in path.parts)


def _opaque(sc: shell_parser.SimpleCommand, argv: list[str]) -> bool:
    """Whether a simple command runs a command string the parser never sees (the closed list in the module docstring):
    a shell fed by stdin (a here-string, a here-document, an input file, or a pipe), `trap` with a command, `source` or
    `.`, `xargs`, `parallel`, and `find -exec`. `exec`, `command`, and `builtin` are followed as wrappers."""
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
    if name in _RUNS_COMMANDS:
        return True
    return name == "find" and bool(_FIND_RUNS & set(args))


def _substitutes_a_program(command: str) -> bool:
    """A command substitution or backticks in the program position. Here-document bodies and the text inside quotes
    are not commands: a quoted word keeps only its first two characters, so `"$(cmd)" -c ...` is still seen."""
    stripped, _ = shell_parser.split_heredocs(command)
    masked = _QUOTED.sub(lambda m: m.group(0)[:3] + m.group(0)[-1] if m.group(0)[0] == '"' else "''", stripped)
    return bool(_SUBSTITUTED_PROGRAM.search(masked))


def _target_verdicts(
    sc: shell_parser.SimpleCommand, argv: list[str], folders: tuple[Path, Path], root: str | None, event: dict, held: bool, known: dict[str, str]
) -> list[verdicts.Verdict]:
    """The denials for the write targets of one simple command run from `folders`: the folder the check reads, and
    the one the line's own assignments suggest (`shell_writes`)."""
    here, guessed = folders
    found: list[verdicts.Verdict] = []
    targets, unknown = _write_targets(sc, here)
    name_only = set(targets[len(sc.out) :]) if argv and shell_parser.program_name(argv[0]) in _NAME_ONLY else set()
    for u in unknown if held else []:
        found.append(("deny", f"{u}; save the patch to a file and apply that file, so its targets can be checked"))
    for t in targets:
        if t in _IGNORED_TARGETS or t.startswith("/dev/"):
            continue
        if root and (_in_git_dir(here, t) or _in_git_dir(guessed, _expanded(t, known))):
            # Only git and aidd commands write in the git directory: a ref, HEAD, a hook, or the config written by hand
            # could record a person's decision or switch to a branch where the guard holds nothing.
            found.append(("deny", f"shell write to {t}: {GIT_DIR}"))
            continue
        if "$" in t or "`" in t or any(c in t for c in "*?[") or _BRACES.search(t):
            if not held:
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
