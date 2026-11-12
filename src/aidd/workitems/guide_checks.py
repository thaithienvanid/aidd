"""Warnings that keep a project's guide (`AGENTS.md`) true after it is filled in: a command or a path it names that the repository
no longer has. A guide rots when a script is renamed or a folder moves, and an agent then runs a command that fails.

Each check reads only the repository's files, gives the same answer for the same files, and says nothing when it cannot tell:

- A path is checked when it has a folder in it and its first folder (or file) is in the repository, so `dist/` before a build,
  an example such as `application/json`, a glob, a placeholder, and a path that git ignores are never named.
- A command is checked when the repository can answer for it: a `make` target (from the Makefiles), a `npm`, `pnpm`,
  `yarn`, or `bun` script (from the package.json files), or a program given by its path. A tool on the PATH, such as `git`,
  and a shell builtin, such as `cd`, are never checked. A repository with no Makefile or no package.json says nothing
  about `make` or a script.
- aidd's own sections, between its marks, are aidd's and are skipped, like every comment and every line still holding a placeholder.

The guide and the manifests are untrusted text, so every read goes through the safe reader with a size cap, no pattern repeats over
repository text (a line is split with `str` methods, and a long line is skipped), and a path from the guide is probed only when it
stays inside the repository with no link on the way. A file this cannot read, a path it may not probe, and a manifest that does not
parse mean "cannot tell", and no warning.

The guide at the top and each tracked guide below it are read. A nested guide's paths resolve from its own folder first.
The two codes below are the findings' names, for a registry that lists them.
"""

from __future__ import annotations

import functools
import json
import os
import posixpath
import re
import shlex
from collections.abc import Iterator
from pathlib import Path

from aidd.kernel import command_names, git, regular_files
from aidd.workitems import objects, placeholders

PATH_MISSING = "guide_path_missing"
COMMAND_MISSING = "guide_command_missing"
GUIDE = "AGENTS.md"
MAX_MANIFESTS = 200
MAX_MANIFEST_BYTES = 256 * 1024
MAX_LINE = 2000  # a longer line of a guide or a Makefile is skipped: no sentence, target, or command is that long
MAX_COMMAND = 300

_UNSURE = re.compile(r"[\s<>*?\[\]{}$|;&\"'\\()=,~^!\x00]")
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_SEGMENT_MARKS = re.compile(r"&&|\|\||;|\|")
_ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
_MAKEFILES = ("Makefile", "makefile", "GNUmakefile")
_RUNNERS = ("npm", "pnpm", "yarn", "bun")
_MARKED = (("<!-- aidd -->", "<!-- /aidd -->"), ("<!-- aidd-team -->", "<!-- /aidd-team -->"))


def _blank_between(text: str, opening: str, closing: str, *, to_end: bool = False) -> str:
    """`text` with each span from `opening` to `closing` as blank lines, so the lines after it keep their numbers. A span that never
    closes stays, or with `to_end` runs to the end. One pass: each search starts where the last one stopped."""
    out, pos = [], 0
    while (start := text.find(opening, pos)) != -1:
        close = text.find(closing, start + len(opening))
        if close == -1 and not to_end:
            break
        end = len(text) if close == -1 else close + len(closing)
        out += [text[pos:start], "\n" * text.count("\n", start, end)]
        pos = end
    return "".join(out) + text[pos:]


def _own_text(text: str) -> str:
    """The guide without aidd's sections and its comments, the line numbers kept."""
    for opening, closing in _MARKED:
        text = _blank_between(text, opening, closing)
    return _blank_between(text, "<!--", "-->", to_end=True)


def _spans(line: str) -> tuple[list[str], str]:
    """The code spans of a line, and the line without them. An odd backtick at the end opens no span."""
    parts = line.split("`")
    closed = len(parts) - len(parts) % 2  # parts[1], parts[3], ... are inside a pair
    return [p.strip() for p in parts[1:closed:2]], "".join(parts[0:closed:2]) + "".join(parts[closed:])


def _links(line: str) -> Iterator[str]:
    """The target of each `[text](target)` in a line, in one pass. A target is at most 200 characters with no space."""
    bracket = -1
    for i, ch in enumerate(line):
        if ch == "[":
            bracket = i
        elif ch == "]" and bracket != -1:
            bracket = -1
            if line[i + 1 : i + 2] == "(":
                target = line[i + 2 : i + 203]
                end = target.find(")")
                if end > 0 and not any(c.isspace() for c in target[:end]):
                    yield target[:end]


def _claims(text: str) -> Iterator[tuple[int, str, str]]:
    """(line, kind, text) for each thing the guide names: a code span, a line of a code block (`command`), a Markdown link."""
    fence = False
    for n, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if placeholders.WORD in line or len(line) > MAX_LINE:
            continue  # a line still waiting to be written (the placeholder warning names it), or too long to be a sentence
        if stripped.startswith(("```", "~~~")):
            fence = not fence
        elif fence:
            command = stripped.removeprefix("$ ").strip()
            if command and not command.startswith("#"):
                yield n, "command", command
        else:
            spans, rest = _spans(line)
            for span in spans:
                yield n, "span", span
            for target in _links(rest):
                yield n, "link", target


def _path_claim(text: str) -> tuple[str, bool] | None:
    """The repository path a code span or a command's first word names, and whether it starts with `./`; None when it is no path
    to check: it has no folder in it, or it is a glob, a placeholder, a URL, a flag, or an absolute path."""
    if not text or len(text) > 200 or _UNSURE.search(text) or "://" in text or "..." in text or text.startswith(("-", "/", "@", "#")):
        return None
    text = re.sub(r"#.*$|:\d+(?::\d+)?$", "", text)
    explicit = text.startswith("./")
    text = text.removeprefix("./")
    return (text, explicit) if text and ("/" in text or explicit) and not text.startswith("../") else None


def make_targets_of(text: str) -> set[str] | None:
    """The targets a Makefile's text names, or None when it cannot be told: an `include`, or a target built from a variable. A line is
    cut at its first colon with `str.partition`, and a line over MAX_LINE is no target. A recipe (indented), a comment, a special
    target (`.PHONY`), a variable assignment (`=`, `:=`, `::=`), and a pattern rule (`%`) name no target."""
    found: set[str] = set()
    for line in text.split("\n"):
        if len(line) > MAX_LINE or not line or line[0] in " \t#.":
            continue
        if line.split(None, 1)[0] in ("include", "-include", "sinclude"):
            return None
        head, colon, rest = line.partition(":")
        if not colon or "=" in head or rest.startswith(("=", ":=")):
            continue
        names = head.split()
        if "$" in head or "%" in names:
            return None
        if any(c in head for c in "(),"):
            continue
        found.update(name for name in names if "%" not in name)
    return found


class Repo:
    """What the repository holds that a guide can name: which paths exist, and which `make` targets and package scripts."""

    def __init__(self, root: Path, guide: str) -> None:
        self.root = root
        self.folder = Path(guide).parent.as_posix()

    @functools.cached_property
    def tracked(self) -> list[str]:
        out = git.run(["ls-files", "-z"], str(self.root), check=False) if (self.root / ".git").exists() else ""
        return [p for p in out.split("\0") if p]

    def named(self, names: tuple[str, ...]) -> list[str]:
        """The tracked files with one of `names`, or the one at the top when none is listed."""
        found = [p for p in self.tracked if p.rsplit("/", 1)[-1] in names and "node_modules/" not in p]
        return found[:MAX_MANIFESTS] or [n for n in names if (self.root / n).is_file()]

    def read(self, rel: str) -> str | None:
        """A manifest's text through the safe reader, or None when it is missing, a link, too large, or not readable."""
        return regular_files.named_text(self.root, rel, MAX_MANIFEST_BYTES)[0]

    def probe(self, rel: str, base: str) -> bool | None:
        """Whether `rel`, read from the folder `base`, exists: None when aidd may not look, because the path is absolute, leaves the
        repository, holds a NUL or a backslash, or has a link on the way."""
        if "\0" in rel or "\\" in rel or regular_files.is_outside(rel):
            return None
        full = posixpath.join(base, rel) if base != "." else rel
        if regular_files.link_on_the_way(self.root, full):
            return None
        return os.path.lexists(self.root / full)

    def seen(self, rel: str, bases: tuple[str, ...] | None = None) -> bool | None:
        """True when `rel` exists from one of the folders (the guide's, then the top), False when it is in none, None when aidd may not look."""
        answers = [self.probe(rel, base) for base in bases or tuple(dict.fromkeys((self.folder, ".")))]
        return True if True in answers else None if None in answers else False

    def anchored(self, rel: str, explicit: bool) -> bool:
        """Whether a path begins somewhere the repository has, so a miss means it moved and not that it is an example."""
        return explicit or self.seen(rel.split("/", 1)[0]) is True

    def ignored(self, rel: str) -> bool:
        """Whether git ignores the path, as a build output is. Without git it cannot tell, so the path counts as ignored."""
        if not (self.root / ".git").exists():
            return True
        try:
            return git.attempt(["check-ignore", "-q", "--", rel], str(self.root))[0] != 1
        except (OSError, ValueError, git.GitError):
            return True

    def missing_path(self, rel: str, explicit: bool) -> bool:
        return self.anchored(rel, explicit) and self.seen(rel) is False and not self.ignored(rel)

    @functools.cached_property
    def make_targets(self) -> set[str] | None:
        """Every target the Makefiles name, or None when there is none or one that this cannot read fully."""
        found: set[str] = set()
        files = self.named(_MAKEFILES)
        for rel in files:
            text = self.read(rel)
            names = None if text is None else make_targets_of(text)
            if names is None:
                return None
            found |= names
        return found if files else None

    @functools.cached_property
    def scripts(self) -> set[str] | None:
        """Every script the package.json files name, or None when there is none or one that does not parse."""
        found: set[str] = set()
        files = self.named(("package.json",))
        for rel in files:
            try:
                scripts = json.loads(self.read(rel) or "").get("scripts") or {}
            except (ValueError, AttributeError, RecursionError):
                return None
            found.update(scripts if isinstance(scripts, dict) else ())
        return found if files else None


def _make_target(tokens: list[str]) -> list[str]:
    """The targets a `make` command names: its words that are no option, no option's value, and no VAR=value."""
    out, skip = [], False
    for word in tokens[1:]:
        if skip:
            skip = False
        elif word in ("-C", "-f", "-I", "-j", "-o", "-W"):
            skip = True
        elif not word.startswith("-") and "=" not in word:
            out.append(word)
    return out


def _script(tokens: list[str]) -> str | None:
    """The package script a `npm run x`, `pnpm test`, or `yarn run x` command runs, or None when it runs none or cannot be told.
    `bun test` is bun's own runner, not a script."""
    words = [w for w in tokens[1:] if not w.startswith("-")]
    if words[:1] in (["test"], ["t"]):
        return None if tokens[0] == "bun" else "test"
    return next((words[i + 1] for i, w in enumerate(words[:-1]) if w in ("run", "run-script")), None)


def _shown(*words: str) -> str:
    """A command a doc names, as a message shows it: in backticks when each word is a plain name (kernel.command_names), else
    its words as one quoted text, so no command holds the doc's text."""
    plain = [command_names.quoted(w) or "" for w in words]
    return f"`{' '.join(plain)}`" if all(plain) else f"the command {' '.join(words)!r}"


def _segment_problem(tokens: list[str], repo: Repo) -> tuple[str, str] | None:
    """(code, what is wrong) when one command (a program and its words) names something the repository lacks, or None."""
    first = tokens[0]
    if first in ("make", "gmake") and repo.make_targets is not None:
        return next(
            ((COMMAND_MISSING, f"{_shown('make', t)} names a target that no Makefile has") for t in _make_target(tokens) if t not in repo.make_targets), None
        )
    if first in _RUNNERS and repo.scripts is not None:
        script = _script(tokens)
        if script is not None and script not in repo.scripts:
            return COMMAND_MISSING, f"{_shown(first, *(['test'] if script == 'test' else ['run', script]))} names a script that no package.json has"
        return None
    if (claim := _path_claim(first)) and repo.missing_path(*claim):
        return PATH_MISSING, f"`{first}` is not in the repository"
    return None


def _command_problem(command: str, repo: Repo) -> tuple[str, str] | None:
    """(code, what is wrong) when a command line names something the repository lacks, or None when it does not, or when this cannot tell."""
    if len(command) > MAX_COMMAND:
        return None
    for segment in _SEGMENT_MARKS.split(command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        while tokens and _ASSIGNMENT.match(tokens[0]):
            tokens = tokens[1:]
        if tokens and (found := _segment_problem(tokens, repo)):
            return found
    return None


def _link_problem(target: str, repo: Repo) -> tuple[str, str] | None:
    """A link leads nowhere when its file is in no place it may be read from. The link resolves from the guide's own folder."""
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or len(target) > 200 or _UNSURE.search(target) or _SCHEME.match(target) or target.startswith("/"):
        return None
    return (PATH_MISSING, f"the link to `{target}` leads nowhere") if repo.seen(target, (repo.folder,)) is False else None


def _problem(kind: str, text: str, repo: Repo) -> tuple[str, str] | None:
    """(code, what is wrong) for one thing a guide names, or None. A link must lead somewhere. A code span with no space is a path
    when it has a folder in it. A span with a space, and a line of a code block, is a command."""
    if kind == "link":
        return _link_problem(text, repo)
    if kind == "span" and " " not in text:
        claim = _path_claim(text)
        return (PATH_MISSING, f"`{text}` is not in the repository") if claim and repo.missing_path(*claim) else None
    return _command_problem(text, repo)


def _guides(root: Path) -> list[str]:
    """The guide at the top, then each tracked guide below it."""
    out = git.run(["ls-files", "-z", "--", f":(glob)**/{GUIDE}"], str(root), check=False) if (root / ".git").exists() else ""
    return [GUIDE, *sorted(p for p in out.split("\0") if p and p != GUIDE)]


def guide_findings(root: Path) -> list[tuple[str, str]]:
    """(code, finding) for each command or path in a guide that the repository does not have. A finding names the guide, the line,
    what is wrong, and what to do."""
    out: list[tuple[str, str]] = []
    for guide in _guides(root):
        text = objects.read_document(root, guide)[0]
        if text is None:
            continue
        repo, seen = Repo(root, guide), set()
        for line, kind, claim in _claims(_own_text(text)):
            if (found := _problem(kind, claim, repo)) and (line, found[1]) not in seen:
                seen.add((line, found[1]))
                out.append((found[0], f"warning: {guide}:{line}: {found[1]}; fix it, or delete the line"))
    return out


def guide_warnings(root: Path) -> list[str]:
    """The findings of `guide_findings` as the warnings `aidd validate` prints."""
    return [message for _, message in guide_findings(root)]
