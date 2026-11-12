"""The files a simple command writes, and the level of editing each: a redirection's target (`> f`, `>> f`, `>| f`, `&> f`,
`2> f`, `>& f`, and `<> f`, which opens for reading and writing), and the file a writer names. The writers are the programs in `code.edit`'s `file_writes` in
schemas/risks.json, each with the rule for which of its words is written (`every_file`, `destination`, `move`, `in_place`,
`of_operand`, `remove`).

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
import tempfile
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace

from aidd import config
from aidd.kernel import command_names, documents, git, globs
from aidd.risk.routes import planned_paths
from aidd.risk.rules import LEVEL_RANK, Rule, RuleSet, areas_in, areas_of, edit_level_in
from aidd.risk.shell import SETTING, Word, shell_words

_REDIRECTIONS = (">", ">>", ">|", "<>")
# The flags of an in-place editor that take a script as their value, in a run of short flags (`-ne`, `-pie`), by program.
_SCRIPT_FLAGS = {"sed": "ef", "perl": "eE"}
_SCRIPT_OPTIONS = ("--expression", "--file")
# Every long option of the GNU writers, whole. A GNU program takes a long option by any prefix that only one of its options starts
# (`--in-pl` is `--in-place`) and refuses a prefix that several start. perl has no long option that matters here, so it has no row.
_LONG_OPTIONS = {
    "sed": (
        "binary debug expression file follow-symlinks help in-place line-length null-data posix quiet regexp-extended sandbox separate silent unbuffered version zero-terminated"
    ).split(),
    "cp": (
        "archive attributes-only backup context copy-contents debug dereference force help interactive keep-directory-symlink link no-clobber no-dereference no-preserve no-target-directory one-file-system parents preserve recursive reflink remove-destination sparse strip-trailing-slashes suffix symbolic-link target-directory update verbose version"
    ).split(),
    "mv": (
        "backup context debug exchange force help interactive no-clobber no-copy no-target-directory strip-trailing-slashes suffix target-directory update verbose version"
    ).split(),
    "install": (
        "backup compare context debug directory group help mode no-target-directory owner preserve-context preserve-timestamps strip strip-program suffix target-directory verbose version"
    ).split(),
    "rm": "dir force help interactive no-preserve-root one-file-system preserve-root recursive verbose version".split(),
    "ln": (
        "backup directory force help interactive logical no-dereference no-target-directory physical relative suffix symbolic target-directory verbose version"
    ).split(),
}
# The short flags whose value is the rest of the word (`perl -MList::Util`), so no flag follows them in the run.
_ATTACHED_VALUE = "MmIdDVxF"
_TARGET_DIRECTORY = "--target-directory"
# The short flags of `cp`, `mv`, `install`, and `ln` that take a value, which is the rest of their word (`-Ssuffix`, `-m644`, `-o root`).
_VALUE_FLAGS = "Smog"
# The short flags of a copy that take a folder whole (`-r`, `-R`, `-a`).
_RECURSIVE = "rRa"
# aidd's own output folders: the files in them that git ignores are no edit (`aidd init` writes the ignore line).
_OUTPUT_FOLDERS = config.OUTPUT_IGNORE.strip("/") + "**"


@dataclass(frozen=True)
class Edit:
    """A written path whose edit is not `allow`: the path as the repository names it (`shown`, or in full outside it, with a
    trailing `/` for a folder written into), with the level of editing it and the rule that decided it. `deleted` is set when a
    removal (`rm`, `unlink`) names the path, so the note says what a removal does."""

    shown: str
    level: str
    rule: Rule | None
    folder: bool = False
    deleted: bool = False


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


def _split_options(args: list[Word]) -> tuple[list[Word], list[Word]]:
    """The words of `args` that are options, and those that are not: `--` ends the options, and a bare `-` is no option."""
    options: list[Word] = []
    positional: list[Word] = []
    done = False
    for word in args:
        if done or word == "-" or not word.startswith("-"):
            positional.append(word)
        elif word == "--":
            done = True
        else:
            options.append(word)
    return options, positional


def _named(word: str) -> str:
    """The last name of a path: what a copy of that file is called inside a folder."""
    return word.rstrip("/").rsplit("/", 1)[-1] or word


def _inside(folder: Word, names: list[Word]) -> list[Word]:
    """The files `names` become inside `folder`: a name the shell expands stands for `*`, which every area glob for the folder reads."""
    return [Word(f"{folder.rstrip('/')}/{'*' if n.expands else _named(n)}", folder.expands) for n in names]


def _long_option(program: str, word: str) -> str:
    """The whole long option that `word` (`--in-pl`, `--target-directory=DIR`) spells for `program`, without a value: an exact
    name, else the one option that the name is a prefix of. A name that several options start, or none, is returned as typed."""
    name = word.partition("=")[0]
    names = [f"--{n}" for n in _LONG_OPTIONS.get(program, ())]
    starts = [n for n in names if n.startswith(name)] if len(name) > 2 and name not in names else [name]
    return starts[0] if len(starts) == 1 else name


def _target_directory(program: str, args: list[Word]) -> tuple[Word | None, bool]:
    """The folder `-t DIR`, `-tDIR`, `--target-directory DIR`, or `--target-directory=DIR` names, as `cp`, `mv`, `install`, and `ln` take it,
    and whether it is sure. The `-t` may stand in a run of short flags (`-rt DIR`, `-Dt DIR`), up to a flag that takes a value. It is
    sure when it opens its word or is the long option, and not when it follows another letter: the BSD `install` takes `-B.dist`
    whole, so that `t` is part of a suffix."""
    for i, word in enumerate(args):
        if word == "--":
            return None, False
        if word.startswith("--") and _long_option(program, word) == _TARGET_DIRECTORY:
            if "=" in word:
                return Word(word.partition("=")[2], word.expands), True
            return (args[i + 1] if i + 1 < len(args) else None), True
        if word.startswith("-") and not word.startswith("--"):
            for pos, char in enumerate(word[1:], 1):
                if char == "t":  # the rest of the word is the folder, or the next word when nothing follows
                    rest = word[pos + 1 :]
                    if rest:
                        return Word(rest, word.expands), pos == 1
                    return (args[i + 1] if i + 1 < len(args) else None), pos == 1
                if char in _VALUE_FLAGS:
                    break  # the rest of the word is this flag's value, so no flag follows it
    return None, False


def _in_place_files(program: str, args: list[Word]) -> list[Word]:
    """The files an in-place editor (`sed -i`, `perl -i`) edits, or none without the option. The first word that is no option is its
    script, unless an option gives the script (`-e`, `-f`). A bare `-i` followed by an empty word is the backup suffix of the BSD form."""
    script_flags = _SCRIPT_FLAGS.get(program, "")
    in_place, scripted = False, False
    kept: list[Word] = []
    queue = deque(args)
    while queue:
        word = queue.popleft()
        if word == "--":
            kept += queue
            break
        if word == "-" or not word.startswith("-"):
            kept.append(word)
        elif word.startswith("--"):
            name = _long_option(program, word)
            in_place = in_place or name == "--in-place"
            if name in _SCRIPT_OPTIONS:
                scripted = True
                if "=" not in word and queue:
                    queue.popleft()  # the script or its file
        else:
            for pos, char in enumerate(word[1:], 1):
                if char in _ATTACHED_VALUE:
                    break
                if char == "i":
                    in_place = True
                    if word == "-i" and queue and queue[0] == "":
                        queue.popleft()
                    break
                if char in script_flags:
                    scripted = True
                    if pos == len(word) - 1 and queue:
                        queue.popleft()
                    break
    return kept if in_place and scripted else kept[1:] if in_place else []


def _recursive(program: str, options: list[Word]) -> bool:
    """Whether a copy's options take a folder whole: `-r`, `-R`, `-a`, in a run of short flags too, or `--recursive`, `--archive`."""
    return any(
        _long_option(program, w) in ("--recursive", "--archive") if w.startswith("--") else not w.startswith("-t") and any(c in _RECURSIVE for c in w[1:])
        for w in options
    )


def _destinations(program: str, args: list[Word], is_folder: Callable[[Word], bool]) -> list[tuple[list[Word], Word | None, bool]]:
    """Each way to read the sources of a copy or a move, its destination (the folder `-t` names, else the last word), and whether the
    destination is a folder that the sources land in: `-t`, a word that ends in `/`, or a folder that exists. A `-t` that is not sure
    (`_target_directory`) is read both ways, so the last word is a destination too."""
    positional = _split_options(args)[1]
    folder, sure = _target_directory(program, args)
    readings: list[tuple[list[Word], Word | None, bool]] = []
    if folder is not None:
        readings.append((positional, folder, True))
    if folder is None or not sure:
        if len(positional) < 2:
            readings.append((positional, None, False))
        else:
            dest = positional[-1]
            readings.append((positional[:-1], dest, dest.endswith("/") or is_folder(dest)))
    return readings


def _written_by(program: str, how: str, args: list[Word], is_folder: Callable[[Word], bool]) -> tuple[list[Word], list[Word]]:
    """The words of a writer's command that name a file it writes, and those that name a folder it writes into, by its rule in
    `file_writes` (the schema says what each means). `is_folder` tells whether a word names a folder that exists. A folder
    written into is read whole, since the names that land in it are not known: a copy of a folder (`-r`, `-R`, `-a`, a source that
    is a folder or that the shell expands) and a move of one."""
    if how == "of_operand":
        return [Word(w[3:], w.expands) for w in args if w.startswith("of=")], []
    if how == "in_place":
        return _in_place_files(program, args), []
    if how == "every_file":
        return _split_options(args)[1], []
    if how == "remove":
        # Every operand is deleted. With a recursive option each also stands for the folder it may be, since a folder that is deleted
        # takes every file under it, and a name the shell expands is left to the files list, which says it is unchecked.
        options, operands = _split_options(args)
        return operands, [w for w in operands if not w.expands] if _recursive(program, options) else []
    recursive = how == "destination" and _recursive(program, _split_options(args)[0])
    files: list[Word] = []
    trees: list[Word] = []
    for sources, dest, into in _destinations(program, args, is_folder):
        if dest is None:
            files += sources if how == "move" else []
            continue
        files += _inside(dest, sources) if into else [dest]
        for source in sources:
            if source.expands or recursive or is_folder(source):
                # A folder copied into a folder lands in it by its own name. A name that ends in `/` (the BSD `cp`) or that the shell expands may land its contents.
                lands_by_name = into and not source.expands and not source.endswith("/")
                trees.append(Word(f"{dest.rstrip('/')}/{_named(source)}", dest.expands) if lands_by_name else dest)
        if how == "move":
            files += sources
            trees += [s for s in sources if not s.expands and is_folder(s)]
    return list(dict.fromkeys(files)), list(dict.fromkeys(trees))


def _writers(rs: RuleSet) -> dict[str, str]:
    return (rs.actions.get("code.edit", {}).get("file_writes") or {}).get("writers") or {}


def _written_words(rs: RuleSet, call: str, is_folder: Callable[[Word], bool]) -> tuple[list[Word], list[Word], set[str]]:
    """Every word of a simple command that names a file it writes (a redirection's target, and what a writer program names), each
    that names a folder it writes into, and the words a removal (`rm`, `unlink`) deletes."""
    rest, targets = _parse(call)
    files: list[Word] = [*targets]
    folders: list[Word] = []
    deleted: set[str] = set()
    program = str(rest[0]).rsplit("/", 1)[-1] if rest else ""
    if how := _writers(rs).get(program):
        more, folders = _written_by(program, how, rest[1:], is_folder)
        files += more
        if how == "remove":
            deleted = {str(w) for w in [*more, *folders]} - {str(t) for t in targets}
    return list(dict.fromkeys(files)), list(dict.fromkeys(folders)), deleted


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
        shown = documents.one_line(simple, 300)
        notes = [
            f"`{shown}` {'removes' if gone else 'writes to'} {documents.one_line(word, 120)}, which the shell expands, so aidd cannot tell the file and does not check it"
            for word, gone in unread
        ]
        edits: list[Edit] = []
        for e in found:
            label = e.rule.label() if e.rule else None
            path = documents.one_line(e.shown, 200)
            if e.deleted:
                verb, what = "removes", f"{path} and everything under it" if e.folder else path
            else:
                verb, what = "writes", f"everything that lands in {path}" if e.folder else path
            quoted = command_names.quoted(e.shown) or "<path>"
            notes.append(f"`{shown}` {verb} {what}, so it is an edit of that file ({label}); `aidd risk --paths {quoted}` gives the same level")
            edits.append(e)
        for word, guess, hint, gone in guessed:
            verb = "removes" if gone else "writes"
            name = documents.one_line(word, 120)
            if guess is not None:
                label = guess.rule.label() if guess.rule else None
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

    def _edits(self, call: str) -> tuple[list[Edit], list[tuple[str, bool]], list[tuple[str, Edit | None, Edit | None, bool]]]:
        """What one simple command writes: the writes that are edits above `allow`, each written word the shell expands (which aidd
        cannot read), and each relative word read by its name alone because the folder is not known, with the file it could be."""

        def is_folder(word: Word) -> bool:
            return not word.expands and os.path.isdir(self._lexical(word, self.start))

        files, folders, deleted = _written_words(self.rs, call, is_folder)
        found: list[Edit] = []
        unread: list[tuple[str, bool]] = []
        guessed: list[tuple[str, Edit | None, Edit | None, bool]] = []
        for words, whole in ((files, False), (folders, True)):
            for word in words:
                if "\0" in word:
                    continue  # no file has a name with a NUL
                if word.expands:
                    unread.append((str(word), str(word) in deleted))
                    continue
                relative = not os.path.isabs(os.path.expanduser(word))
                readings = []
                for base in [self.start]:
                    lexical = self._lexical(word, base)
                    if not lexical.startswith("/dev/"):  # a device, and `..` cannot lead out of it: the path is already normal
                        readings += [e for p in dict.fromkeys((lexical, os.path.realpath(lexical))) if (e := self._edit_of(p, whole)) is not None]
                if readings:
                    found.append(replace(max(readings, key=lambda e: LEVEL_RANK[e.level]), deleted=str(word) in deleted))
                if relative and not self.known:
                    guess, hint = (replace(e, deleted=str(word) in deleted) if e else None for e in self._named_like(str(word), whole))
                    guessed.append((str(word), guess, hint, str(word) in deleted))
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
    def _one_guess_each_word(guessed: list[tuple[str, Edit | None, Edit | None, bool]]) -> list[tuple[str, Edit | None, Edit | None, bool]]:
        """A word read as a file and as a folder gives one note: the reading that raises, else the one that hints, else the first."""

        def strength(entry: tuple[str, Edit | None, Edit | None, bool]) -> tuple[int, int]:
            _, guess, hint, _ = entry
            return (LEVEL_RANK[guess.level] + 1 if guess else 0, LEVEL_RANK[hint.level] + 1 if hint else 0)

        best: dict[str, tuple[str, Edit | None, Edit | None, bool]] = {}
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

    def _edit_of(self, absolute: str, whole: bool) -> Edit | None:
        """The edit a write to the absolute path is, or None when it is no edit or one that asks nothing (`allow`). `whole` reads the
        folder as `aidd risk --paths` does: its own path and every tracked file under it."""
        inside = absolute == self.root or absolute.startswith(self.root.rstrip("/") + "/")
        rel = os.path.relpath(absolute, self.root).replace(os.sep, "/") if inside else absolute
        if not inside and _temporary(absolute):
            return None
        rs = self.rs if inside else _absolute_areas(self.rs)
        if whole and inside:
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
        return Edit(rel + "/" if whole and inside else rel, level, rule, whole and inside)

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
