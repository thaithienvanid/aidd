"""The files a simple command writes, and the level of editing each: a redirection's target (`> f`, `>> f`, `>| f`, `&> f`,
`2> f`, `>& f`, and `<> f`, which opens for reading and writing), and the file a writer names. The writers are the programs in `code.edit`'s `file_writes` in
schemas/risks.json, each with the rule for which of its words is written (`every_file`, `destination`, `move`, `in_place`,
`of_operand`, `remove`). A writer is a program, or `git` with its subcommand (`git rm`, `git mv`), read as `rm` and `mv` are, and
`git -C <dir>` reads its relative paths from that folder when the folder is known.

A written path has the level `aidd risk --paths` gives it (`edit_level_in`), so a shell write and the edit tool read one rule.
A relative path is read from the folder the command was typed in, and no `cd` is followed (`Writes`). From a word that may
change the folder, a relative path is read by its name alone. It is the strictest of the files and places whose name an area guards:
a tracked file that ends with it, where an area's glob names a file or a kind of file; and a place an area's glob for a kind of file
could put it. A bare name that a folder-wide area guards (`index.ts` under `src/users/`) raises nothing: the note names the file. The
repository is the one the line started in, so a `cd` out and an absolute path back in read as that file. A path that goes by links is
read as typed and where it leads, and the stricter wins.

A folder that a copy or a move writes into is read as `aidd risk --paths` reads that folder: every tracked file under it, and a
file that could land there. It never reads lower than `--paths` for the folder, because it is that reading. A folder that `rm -r` deletes is read the same way.

Three kinds of write are no edit: a device (`/dev/null`), a file under the system's temporary folder outside the repository, and a
file in one of aidd's own output folders (`.aidd/*/`) that git ignores. Any other file git ignores keeps the level its area gives.
A path outside the repository counts only when an area names it with a glob that starts with `/`. A word the shell expands
(`$LOG`, a glob, a brace) names no file aidd can read: it is left unchecked, and the answer says so (SECURITY.md).
"""

from __future__ import annotations

import os
import re
import shlex
import tempfile
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import NamedTuple

from aidd import config
from aidd.kernel import command_names, documents, git, globs
from aidd.risk.routes import planned_paths
from aidd.risk.rules import LEVEL_RANK, Rule, RuleSet, areas_in, areas_of, edit_level_in
from aidd.risk.shell import GIT_VALUE_OPTIONS, SETTING, Word, shell_words
from aidd.risk.writer_words import Pathspec, git_writer, pathspecs, under, written_by

_REDIRECTIONS = (">", ">>", ">|", "<>")
# aidd's own output folders: the files in them that git ignores are no edit (`aidd init` writes the ignore line).
_OUTPUT_FOLDERS = config.OUTPUT_IGNORE.strip("/") + "**"
# What a note says of a word aidd cannot read, after the verb and the word.
_EXPANDS = "which the shell expands, so aidd cannot tell the file and does not check it"
_PATHSPEC = "which git reads by its own pathspec rules, so aidd cannot tell the files and does not check them"


@dataclass(frozen=True)
class Edit:
    """A written path whose edit is not `allow`: the path as the repository names it (`shown`, or in full outside it, with a
    trailing `/` for a folder written into), with the level of editing it and the rule that decided it. `verb` says what the command
    does to the path (`removes`, or `stops tracking` for `git rm --cached`, which leaves the file), so the note says it. A path that
    is a `pathspec` stands for every tracked file it matches."""

    shown: str
    level: str
    rule: Rule | None
    folder: bool = False
    verb: str = "writes"
    pathspec: bool = False


def _is_write(operator: str, target: str) -> bool:
    """Whether a redirection writes `target`: `>`, `>>`, `>|`, `<>`, and `&>`, with or without a descriptor, and `>&` to a file. `>&2` and `>&-` copy or close a descriptor."""
    kind = operator.lstrip("0123456789&")
    if not target or target.startswith("("):  # a process substitution, such as `> >(cmd)`
        return False
    return kind in _REDIRECTIONS or (kind == ">&" and not (target.isdigit() or target == "-"))


def _parse(call: str) -> tuple[list[Word], list[Word]]:
    """A simple command's words, program first, and the targets of its output redirections."""
    words = deque(shell_words(call.strip().lstrip("({ ").rstrip(";) ")))
    rest: list[Word] = []
    targets: list[Word] = []
    while words:
        word, operator = words.popleft()
        if not operator:
            rest.append(word)
            continue
        target = words.popleft()[0] if words and not words[0][1] else None
        if target is not None and _is_write(word, target):
            targets.append(target)
    return rest[next((i for i, w in enumerate(rest) if not SETTING.fullmatch(w)), len(rest)) :], targets


def _writers(rs: RuleSet) -> dict[str, str]:
    return (rs.actions.get("code.edit", {}).get("file_writes") or {}).get("writers") or {}


class _Written(NamedTuple):
    """What a simple command writes: the words that name a file, the words that name a folder written into, what the command does to
    each word it removes (`removes`, `stops tracking`), and whether the folder the relative words are read from is known."""

    files: list[Word]
    folders: list[Word]
    verbs: dict[str, str]
    known: bool


def _written_words(rs: RuleSet, call: str, is_folder: Callable[[Word], bool]) -> _Written:
    """Every word of a simple command that names a file it writes (a redirection's target, and what a writer program names), each
    that names a folder it writes into, the verb of each word a removal (`rm`, `unlink`, `git rm`) deletes, and whether the folder the
    writer's relative words are read from is known (`git -C`)."""
    rest, targets = _parse(call)
    files: list[Word] = [*targets]
    folders: list[Word] = []
    verbs: dict[str, str] = {}
    known = True
    program = str(rest[0]).rsplit("/", 1)[-1] if rest else ""
    args = rest[1:]
    folder, untracks = "", False
    if program == "git":
        program, args, folder, known, untracks = git_writer(args)
    if how := _writers(rs).get(program):
        more, folders = written_by(program, how, args, lambda w: is_folder(under(folder, w)))
        if program == "git rm":  # git reads each operand as a pathspec, which a `*` lets cross a `/`
            more, folders = pathspecs(more), [w for w in pathspecs(folders) if not isinstance(w, Pathspec)]
        more, folders = [under(folder, w) for w in more], [under(folder, w) for w in folders]
        files += more
        if how == "remove":
            verbs = {str(w): "stops tracking" if untracks else "removes" for w in [*more, *folders]}
            verbs = {w: v for w, v in verbs.items() if w not in {str(t) for t in targets}}
    return _Written(list(dict.fromkeys(files)), list(dict.fromkeys(folders)), verbs, known)


def _temporary(path: str) -> bool:
    """Whether `path` is under the system's temporary folder, by its name or its resolved one."""
    folders = {f for t in (tempfile.gettempdir(), "/tmp", "/var/tmp") for f in (t, os.path.realpath(t))}
    return any(path == f or path.startswith(f.rstrip("/") + "/") for f in folders)


def _absolute_areas(rs: RuleSet) -> RuleSet:
    """The rule set with each area cut to its globs that start with `/`, the only ones that can name a file outside the
    repository: a repository's own globs (`**/users/**`) read a home folder or a clone elsewhere as a path inside."""
    cut = {name: {**area, "paths": [p for p in area.get("paths", []) if p.startswith("/")]} for name, area in rs.areas.items()}
    return replace(rs, areas=cut)


_FOLDER_PROGRAMS = {"cd", "chdir", "pushd", "popd"}
# What can stand glued to a command word: a subshell or group opens (`(cd`, `{ cd`), or a substitution (`$(cd`).
_OPENING = re.compile(r"^(?:\$\(|[({])+")
_WRAPPERS = {"env", "sudo"}
# Command words that change no folder, though the shell marks `[` as a glob and `.` names a folder: `[` and `[[` test, and `.` runs a
# script whose change of folder aidd does not see, as for `source` (SECURITY.md).
_NO_FOLDER_WORDS = {"[", "[[", "."}
# Words that make a shell change folders with no `cd` before the next command.
_FOLDER_SETTINGS = ("cdpath", "cdable", "auto_cd", "autocd")


def guards_by_name(glob: str) -> bool:
    """Whether an area's glob guards a file by its name: the last segment names a file or a kind of file (`.aidd/config.yaml`,
    `**/*.pem`, `**/login*.*`). A glob that ends in `**`, in `*`, or in a folder (`**/auth/**`, `.github/workflows/**`) guards the
    folder, and every file name in it."""
    return glob.rsplit("/", 1)[-1] not in ("", "*", "**")


def _changes_folder(call: str, start: str) -> bool:
    """Whether a command may change the folder that the rest of the line runs in, or run in another one, decided by what its words
    are and never by their arguments. A `cd`, `chdir`, `pushd`, or `popd`. A subshell or brace group needs no word of its own: it
    changes the folder only through one of these. A command word the shell expands (`$CD .aidd`), or a command word that is a folder, which zsh enters with `auto_cd`, but never `[`, `[[`, or `.`. A word that
    names `CDPATH`, `cdable_vars`, or `auto_cd`. Beside `env` or `sudo`, an option that has a `C` or a `D` (`-C`, `-iC`, `-D`) or
    that starts `--c` (`--chdir`, and its abbreviations)."""
    words = shell_words(call)
    program = next((w for w, operator in words if not operator and not SETTING.fullmatch(w)), None)
    if (
        program is not None
        and program not in _NO_FOLDER_WORDS
        and (program.expands or ("\0" not in program and os.path.isdir(os.path.join(start, os.path.expanduser(program)))))
    ):
        return True
    names = [str(w) for w, operator in words if not operator]
    wrapped = any(w.rsplit("/", 1)[-1] in _WRAPPERS for w in names)
    for w in names:
        if _OPENING.sub("", w).rsplit("/", 1)[-1] in _FOLDER_PROGRAMS:
            return True
        if any(setting in w.lower() for setting in _FOLDER_SETTINGS):
            return True
        if wrapped and w.startswith("-") and w != "-" and (w.lower().startswith("--c") if w.startswith("--") else any(c in "CD" for c in w[1:])):
            return True
    return False


class Writes:
    """The files the commands of one line write, read against one rule set for one role, from the folder the line starts in
    (`start`; None is the folder aidd runs in). It keeps what git told, for the rest of the answer.

    The folder of a write is the folder the line started in, unless a word before the write may change it (`_changes_folder`). From
    that word to the end of the line the folder is not known, and a relative path is read by its name alone (`_named_like`): as every
    file, and every place an area's glob could put one, whose path ends with it. No `cd` is followed."""

    def __init__(self, rs: RuleSet, role: str | None, start: str | None) -> None:
        self.rs = rs
        self.role = role
        self.start = os.path.abspath(start or ".")
        self.known = True
        self.git_said: dict = {}
        self._root: str | None = None

    @property
    def root(self) -> str:
        """The top of the repository the line started in, or that folder itself where none holds it."""
        if self._root is None:
            try:
                top = git.repository_top(self.start)
            except (git.GitError, OSError, ValueError):
                top = None
            self._root = os.path.realpath(top or self.start)
        return self._root

    def part(self, calls: tuple[str, ...], simple: Callable[[str], str]) -> tuple[list[dict], list[str]]:
        """The `code.edit` steps and the notes of one part of the line, `calls` being the part and then every command it runs inside
        itself (`shell.wrapped`), each by its `simple` form."""
        if any(_changes_folder(call, self.start) for call in calls):
            self.known = False
        steps: list[dict] = []
        notes: list[str] = []
        for call in calls:
            found, said = self._steps(call, simple)
            steps += found
            notes += said
        return steps, notes

    def _steps(self, call: str, simple_of: Callable[[str], str]) -> tuple[list[dict], list[str]]:
        found, unread, guessed = self._edits(call)
        simple = simple_of(call) if found or unread or guessed else ""
        shown = documents.one_line((self._typed(call) if simple else "") or simple, 300)
        notes = [f"`{shown}` {'writes to' if verb == 'writes' else verb} {documents.one_line(word, 120)}, {why}" for word, verb, why in unread]
        edits: list[Edit] = []
        for e in found:
            label = e.rule.label() if e.rule else None
            path = documents.one_line(e.shown, 200)
            if e.pathspec:  # `aidd risk --paths` reads a `*` inside one folder, so its answer for the pathspec is no check of this one
                notes.append(f"`{shown}` {e.verb} every tracked file that the pathspec {shlex.quote(path)} matches, so it is an edit of those files ({label})")
            else:
                if e.verb != "writes":
                    what = f"{path} and everything under it" if e.folder else path
                else:
                    what = f"everything that lands in {path}" if e.folder else path
                quoted = command_names.quoted(e.shown) or "<path>"
                notes.append(f"`{shown}` {e.verb} {what}, so it is an edit of that file ({label}); `aidd risk --paths {quoted}` gives the same level")
            edits.append(e)
        for word, guess, hint, verb in guessed:
            name = documents.one_line(word, 120)
            if guess is not None:
                label = guess.rule.label() if guess.rule else None
                if guess.pathspec:
                    notes.append(
                        f"`{shown}` {verb} {name} from a folder aidd did not follow, so it is read as the pathspec {shlex.quote(guess.shown)} in any folder, "
                        f"which matches a tracked file that an area rates ({label})"
                    )
                else:
                    notes.append(
                        f"`{shown}` {verb} {name} from a folder aidd did not follow, so it is read as {documents.one_line(guess.shown, 200)}, a file it could be ({label})"
                    )
                edits.append(guess)
            elif hint is not None:
                label = hint.rule.label() if hint.rule else None
                quoted = command_names.quoted(hint.shown) or "<path>"
                notes.append(
                    f"`{shown}` {verb} {name} from a folder aidd did not follow, and a file of that name is guarded by its folder at {documents.one_line(hint.shown, 200)} ({label}), "
                    f"so the command keeps its own level; `aidd risk --paths {quoted}` checks that file"
                )
            else:
                notes.append(
                    f"`{shown}` {verb} {name} from a folder aidd did not follow, and no file that an area rates is named like it, so the command keeps its own level"
                )
        steps = [
            {
                "action": "code.edit",
                "command": simple,
                "branch": None,
                "environment": None,
                "level": e.level,
                "rule": e.rule.label() if e.rule else None,
                "source": e.rule.source if e.rule else None,
            }
            for e in edits
        ]
        return steps, notes

    @staticmethod
    def _typed(call: str) -> str:
        """A git command as `normalize` sets it aside (git's options before the subcommand, such as `-c key=value`, whose value may hold a
        secret, and a setting before the program), with each word quoted as a shell reads it, and with `-C DIR` kept: the folder
        names where the words are read from. Empty for any other command, which a note shows in its `normalize`d form."""
        rest = _parse(call)[0]
        if not rest or str(rest[0]).rsplit("/", 1)[-1] != "git":
            return ""
        words, at = [Word("git")], 1
        while at < len(rest) and rest[at].startswith("-"):
            option, at = rest[at], at + 1
            if option in GIT_VALUE_OPTIONS and at < len(rest):
                words += [option, rest[at]] if option == "-C" else []
                at += 1
        words += rest[at:]
        return " ".join(w if w.expands else shlex.quote(w) for w in words)

    def _edits(self, call: str) -> tuple[list[Edit], list[tuple[str, str, str]], list[tuple[str, Edit | None, Edit | None, str]]]:
        """What one simple command writes: the writes that are edits above `allow`, each written word the shell expands (which aidd
        cannot read), and each relative word read by its name alone because the folder is not known, with the file it could be."""

        def is_folder(word: Word) -> bool:
            return not word.expands and os.path.isdir(self._lexical(word, self.start))

        files, folders, verbs, folder_known = _written_words(self.rs, call, is_folder)
        found: list[Edit] = []
        unread: list[tuple[str, str, str]] = []
        guessed: list[tuple[str, Edit | None, Edit | None, str]] = []
        for words, whole in ((files, False), (folders, True)):
            for word in words:
                if "\0" in word:
                    continue  # no file has a name with a NUL
                verb = verbs.get(str(word), "writes")
                if word.expands:
                    unread.append((str(word), verb, _EXPANDS))
                    continue
                if isinstance(word, Pathspec) and word.magic:
                    unread.append((str(word), verb, _PATHSPEC))
                    continue
                relative = not os.path.isabs(os.path.expanduser(word))
                readings = []
                try:
                    for base in [self.start]:
                        lexical = self._lexical(word, base)
                        if not lexical.startswith("/dev/"):  # a device, and `..` cannot lead out of it: the path is already normal
                            readings += [
                                e
                                for p in dict.fromkeys((lexical, os.path.realpath(lexical)))
                                if (e := self._edit_of(p, whole, isinstance(word, Pathspec))) is not None
                            ]
                    if relative and not (self.known and folder_known):
                        guess, hint = (replace(e, verb=verb) if e else None for e in self._named_like(str(word), whole))
                        if isinstance(word, Pathspec):  # a pattern may name a file in the folder aidd did not follow
                            anywhere = self._pathspec_anywhere(str(word), verb)
                            guess = self._stricter(guess, anywhere) if anywhere else guess
                        guessed.append((str(word), guess, hint, verb))
                except globs.GlobError:  # a pathspec longer than the matcher takes: unchecked, and no other word is lowered by it
                    if not isinstance(word, Pathspec):
                        raise
                    unread.append((str(word), verb, _PATHSPEC))
                    continue
                if readings:
                    found.append(replace(max(readings, key=lambda e: LEVEL_RANK[e.level]), verb=verb))
        return self._one_reading_each_path(found), unread, self._one_guess_each_word(guessed)

    def _one_reading_each_path(self, found: list[Edit]) -> list[Edit]:
        """A path read as a file and as a folder (`rm -r .claude`) gives one edit, so one note: the reading that fits what the path is
        on disk, and the other only when it is stricter."""
        groups: dict[str, list[Edit]] = {}
        for e in found:
            groups.setdefault(e.shown.rstrip("/"), []).append(e)
        kept: list[Edit] = []
        for path, edits in groups.items():
            file_edit = next((e for e in edits if not e.folder), None)
            folder_edit = next((e for e in edits if e.folder), None)
            if file_edit is None or folder_edit is None:
                kept += edits
                continue
            is_folder = os.path.isdir(os.path.join(self.root, path))
            first, second = (folder_edit, file_edit) if is_folder else (file_edit, folder_edit)
            kept += [first, second] if LEVEL_RANK[second.level] > LEVEL_RANK[first.level] else [first]
        return kept

    @staticmethod
    def _one_guess_each_word(guessed: list[tuple[str, Edit | None, Edit | None, str]]) -> list[tuple[str, Edit | None, Edit | None, str]]:
        """A word read as a file and as a folder gives one note: the reading that raises, else the one that hints, else the first."""

        def strength(entry: tuple[str, Edit | None, Edit | None, str]) -> tuple[int, int]:
            _, guess, hint, _ = entry
            return (LEVEL_RANK[guess.level] + 1 if guess else 0, LEVEL_RANK[hint.level] + 1 if hint else 0)

        best: dict[str, tuple[str, Edit | None, Edit | None, str]] = {}
        for entry in guessed:
            if entry[0] not in best or strength(entry) > strength(best[entry[0]]):
                best[entry[0]] = entry
        return list(best.values())

    def _named_like(self, word: str, whole: bool) -> tuple[Edit | None, Edit | None]:
        """What a relative path could be when the folder is not known: the file it raises to, and the file it only hints at.

        It raises to the strictest of these. A tracked file that ends with the word at a segment boundary (`config.yaml` ends
        `.aidd/config.yaml`; `x/config.yaml` does not), where an area guards that file by its name (`guards_by_name`). A place an
        area's glob for a kind of file could put it (`server.pem` for `**/*.pem`): the folders of the glob's literal part joined with
        the word, and the word alone, that the glob matches. A path of an area that the word ends with (`repo/.aidd/config.yaml`,
        after a `cd ..`). For a folder written into, a tracked file under a folder of that name, since the folder is what the word
        names. It hints at a tracked file that ends with the word and that only a folder-wide area guards (`index.ts` under
        `src/users/`): the word does not say which folder, so raising would ask for most honest writes. Case folds as the areas do.
        `..` and `.` are resolved where they can be, and a `..` that leads out is dropped."""
        target = os.path.normpath(os.path.expanduser(word)).replace(os.sep, "/")
        while target.startswith("../"):
            target = target[3:]
        if target in ("", ".", ".."):
            return None, None
        best: Edit | None = None
        hint: Edit | None = None
        folded = target.casefold()
        for name in self._tracked_under("."):
            lowered = name.casefold()
            if (f"/{lowered}".find(f"/{folded}/") >= 0) if whole else (lowered == folded or lowered.endswith("/" + folded)):
                named = [] if whole else self._guarded_by_name(name)
                areas = named or areas_of(self.rs, name)
                if not areas:
                    continue
                level, rule = edit_level_in(self.rs, areas, role=self.role)
                if named or whole:
                    best = self._stricter(best, Edit(name, level, rule))
                else:
                    hint = self._stricter(hint, Edit(name, level, rule))
        segments = target.split("/")
        if not whole:
            for i in range(1, len(segments)):  # the word may end with a path of the repository, such as `repo/.aidd/config.yaml`
                suffix = "/".join(segments[i:])
                if areas := areas_of(self.rs, suffix):
                    level, rule = edit_level_in(self.rs, areas, role=self.role)
                    best = self._stricter(best, Edit(suffix, level, rule))
            for area, glob, excludes, folders in self._glob_places():
                for folder in folders:
                    candidate = f"{folder}/{target}" if folder else target
                    if globs.match_any([glob], candidate, fold_case=True) and not globs.match_any(excludes, candidate, fold_case=True):
                        level, rule = edit_level_in(self.rs, [area], role=self.role)
                        best = self._stricter(best, Edit(candidate, level, rule))
        return best, hint

    @staticmethod
    def _stricter(best: Edit | None, new: Edit) -> Edit | None:
        """`new` if it is above `allow` and stricter than `best`, else `best`."""
        if new.level != "allow" and (best is None or LEVEL_RANK[new.level] > LEVEL_RANK[best.level]):
            return new
        return best

    def _guarded_by_name(self, name: str) -> list[str]:
        """The areas that guard the tracked file `name` by its name: those with a glob that names a file or a kind of file and matches it."""
        if "by_name" not in self.git_said:
            self.git_said["by_name"] = [
                (area, [g for g in spec.get("paths", []) if guards_by_name(g)], list(spec.get("exclude", []))) for area, spec in self.rs.areas.items()
            ]
        return [
            area
            for area, named, excludes in self.git_said["by_name"]
            if named and globs.match_any(named, name, fold_case=True) and not globs.match_any(excludes, name, fold_case=True)
        ]

    def _glob_places(self) -> list[tuple[str, str, list[str], list[str]]]:
        """Each glob of an area that names a kind of file (`**/*.pem`, `.claude/settings.json`), with its area and excludes, and the
        folders it could put the file in: the top, `x`, and each folder of its literal part, a wildcard folder as `x`. A glob that
        covers a whole folder (`.github/workflows/**`) is left out: it would match every name."""
        if "places" not in self.git_said:
            places = []
            for area, spec in self.rs.areas.items():
                for glob in spec.get("paths", []):
                    segments = glob.split("/")
                    if not guards_by_name(glob):
                        continue
                    core = ["x" if globs.is_pattern(s) else s for s in segments[:-1] if s != "**"]
                    folders = ["", "x", *("/".join(core[: i + 1]) for i in range(len(core)))]
                    places.append((area, glob, list(spec.get("exclude", [])), list(dict.fromkeys(folders))))
            self.git_said["places"] = places
        return self.git_said["places"]

    @staticmethod
    def _lexical(word: str, folder: str) -> str:
        return os.path.normpath(os.path.join(folder, os.path.expanduser(word)))

    def _edit_of(self, absolute: str, whole: bool, pathspec: bool = False) -> Edit | None:
        """The edit a write to the absolute path is, or None when it is no edit or one that asks nothing (`allow`). `whole` reads the
        folder as `aidd risk --paths` does: its own path and every tracked file under it. A `pathspec` is read as every tracked file it
        matches, with its `*` crossing a `/` as git reads it, where the matcher's `*` stays inside one folder."""
        inside = absolute == self.root or absolute.startswith(self.root.rstrip("/") + "/")
        rel = os.path.relpath(absolute, self.root).replace(os.sep, "/") if inside else absolute
        if not inside and _temporary(absolute):
            return None
        rs = self.rs if inside else _absolute_areas(self.rs)
        pathspec = pathspec and inside
        if pathspec:
            areas = list(areas_in(rs, self._pathspec_files(rel)))
        elif whole and inside:
            areas = list(areas_in(rs, planned_paths([rel + "/"], self._tracked_under(rel))))
        else:
            areas = areas_of(rs, rel)
        if not inside and not areas:
            return None  # nothing names a file outside the repository
        level, rule = edit_level_in(self.rs, areas, role=self.role)
        if level == "allow":
            return None
        if inside and self._own_output_ignored(rel + "/" if whole else rel):
            return None  # a folder is read as a file there is: git ignores it, and says so only when it tracks nothing under it
        return Edit(rel + "/" if whole and inside else rel, level, rule, whole and inside, pathspec=pathspec)

    def _pathspec_files(self, pattern: str) -> list[str]:
        """The tracked files a pathspec with a `*` matches, the `*` crossing a `/` as git reads it, where the matcher's stays in one folder."""
        return globs.matching(re.sub(r"\*+", "**", pattern), self._tracked_under("."))

    def _pathspec_anywhere(self, word: str, verb: str) -> Edit | None:
        """What a relative pathspec could be when the folder is not known: every tracked file under any folder that it matches
        (`**/` before it), read at the strictest level an area gives them, or None when no area rates one."""
        target = os.path.normpath(os.path.expanduser(word)).replace(os.sep, "/")
        while target.startswith("../"):
            target = target[3:]
        if target in ("", ".", ".."):
            return None
        areas = list(areas_in(self.rs, self._pathspec_files("**/" + target)))
        level, rule = edit_level_in(self.rs, areas, role=self.role) if areas else ("allow", None)
        return self._stricter(None, Edit(target, level, rule, verb=verb, pathspec=True))

    def _tracked_under(self, rel: str) -> list[str]:
        """The files git tracks under the folder `rel` (the whole repository for `.`), read once for each folder in one answer."""
        if ("tracked", rel) not in self.git_said:
            try:
                listing = git.run(["ls-files", "-z", "--", rel], self.root, check=False)
            except (git.GitError, OSError, ValueError):
                listing = ""
            self.git_said["tracked", rel] = [f for f in listing.split("\0") if f]
        return self.git_said["tracked", rel]

    def _own_output_ignored(self, rel: str) -> bool:
        """Whether `rel` is a file in one of aidd's own output folders that git ignores, read once for each file in one answer."""
        if not globs.match_any([_OUTPUT_FOLDERS], rel):
            return False
        if ("ignored", rel) not in self.git_said:
            try:
                self.git_said["ignored", rel] = git.attempt(["check-ignore", "-q", "--", rel], self.root)[0] == 0
            except (git.GitError, OSError, ValueError):
                self.git_said["ignored", rel] = False  # unsure reads as not ignored
        return self.git_said["ignored", rel]
