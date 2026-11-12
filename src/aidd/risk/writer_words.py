"""Which words of a writer's command name a file it writes, by the writer's rule in `file_writes` of schemas/risks.json (`every_file`,
`destination`, `move`, `in_place`, `of_operand`, `remove`): the files it writes, the folders it writes into, and what `-t`, `-r`, `--`,
`-i`, and a long option given by a prefix change. `git rm` and `git mv` are writers by their name with the subcommand, and
`git -C <dir>` names the folder their relative words are read from, and a `git rm` operand with a `*` is a pathspec (`Pathspec`). The reading of a path against the repository is in file_writes.py."""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Callable
from typing import NamedTuple, cast

from aidd.risk.shell import GIT_VALUE_OPTIONS, Word

# The flags of an in-place editor that take a script as their value, in a run of short flags (`-ne`, `-pie`), by program.
_SCRIPT_FLAGS = {"sed": "ef", "perl": "eE"}
_SCRIPT_OPTIONS = ("--expression", "--file")
# Every long option of the GNU writers, whole. A GNU program takes a long option by any prefix that only one of its options starts
# (`--in-pl` is `--in-place`) and refuses a prefix that several start. perl has no long option that matters here, so it has no row.
LONG_OPTIONS = {
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
    names = [f"--{n}" for n in LONG_OPTIONS.get(program, ())]
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


def written_by(program: str, how: str, args: list[Word], is_folder: Callable[[Word], bool]) -> tuple[list[Word], list[Word]]:
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


# The writers whose `-n` and `--dry-run` write nothing. A writer a project adds reads `-n` as its own option does.
_DRY_RUN = ("git rm", "git mv")
# What git reads in a pathspec by its own rules beyond `*`: a magic prefix, `?` and a bracket class, and a backslash.
_PATHSPEC_MAGIC = "?[\\"


class Pathspec(Word):
    """A word of `git rm` that git reads as a pathspec, not as a file name. With `magic` git reads it by rules aidd does not model (a
    `:` prefix, `?`, a bracket class, a backslash). Without it the word holds a `*`, which git lets cross a `/`."""

    magic: bool

    def __new__(cls, text: str, expands: bool = False, magic: bool = False) -> Pathspec:
        word = cast(Pathspec, super().__new__(cls, text, expands))
        word.magic = magic
        return word


def pathspecs(words: list[Word]) -> list[Word]:
    """`words` with each that git reads as a pathspec marked (`Pathspec`). A word the shell expands is left as it is."""
    marked: list[Word] = []
    for word in words:
        magic = word.startswith(":") or any(c in word for c in _PATHSPEC_MAGIC)
        marked.append(Pathspec(word, word.expands, magic) if not word.expands and (magic or "*" in word) else word)
    return marked


class GitWriter(NamedTuple):
    """`git`'s words read as a writer: its name in `file_writes`, its words, the folder they are read from, whether that folder is
    known, and whether the command stops tracking what it names and leaves the files (`git rm --cached`)."""

    program: str
    words: list[Word]
    folder: str
    known: bool
    untracks: bool


def git_writer(args: list[Word]) -> GitWriter:
    """`git`'s words after the program as the writer they may be: its name in `file_writes` (`git rm`, `git mv`), the words after the
    subcommand, the folder `-C` names (each `-C` is read from the one before it, and `~` is expanded before it is joined; empty when the
    folder is not known), and whether the folder the words are read from is known. It is not known when a `-C` value is a word the
    shell expands, or `--git-dir` or `--work-tree` points elsewhere, so a relative word is read by its name alone, as after a
    `cd`. Git's other options before the subcommand are set aside as `normalize` sets them aside. A dry run (`-n`, `--dry-run`) of
    `git rm` or `git mv` writes nothing."""
    rest = deque(args)
    folder, known = "", True
    while rest and rest[0].startswith("-"):
        option = rest.popleft()
        value = rest.popleft() if option in GIT_VALUE_OPTIONS and rest else None
        if option == "-C" and value is not None:
            known = known and not value.expands
            folder = os.path.join(folder, os.path.expanduser(value))  # an absolute value starts over, as git reads it
        elif option.partition("=")[0] in ("--git-dir", "--work-tree"):
            known = False
    program = f"git {rest.popleft()}" if rest else "git"
    words = list(rest)
    options = _split_options(words)[0]
    dry_run = program in _DRY_RUN and ("--dry-run" in options or any(not o.startswith("--") and "n" in o[1:] for o in options))
    untracks = program == "git rm" and any(len(o) > 2 and "--cached".startswith(o.partition("=")[0]) for o in options)
    return GitWriter(program, [] if dry_run else words, folder if known else "", known, untracks)


def under(folder: str, word: Word) -> Word:
    """A word read from `folder`, which `git -C` names: `~` is expanded first, and an absolute word stays as it is. A pathspec that git
    reads by its own rules is left as it is, since no folder makes it a path."""
    if not folder or (isinstance(word, Pathspec) and word.magic):
        return word
    joined = os.path.join(folder, os.path.expanduser(word))
    return Pathspec(joined, word.expands) if isinstance(word, Pathspec) else Word(joined, word.expands)
