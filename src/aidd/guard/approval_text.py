"""Where a command line's text carries an approval: `/aidd approve`, `aidd approve`, `aidd land`, and the decision
records (`refs/aidd/decisions`, the ref aidd used before 1.0, `refs/aidd/approvals`, and `Aidd-Merge-Approval`), and
where such text only describes or documents, so it records and posts nothing: a search, a commit message or a pull
request's description, or a file's text.
"""

from __future__ import annotations

import re

from aidd import workitems
from aidd.guard import shell_parser
from aidd.guard.publish_commands import GH_VALUE_FLAGS

_AIDD_APPROVE = re.compile(r"/aidd\s+approve", re.I)
# What reads as an approval, not a mention of one: the command, then a work item id and a hash or commit.
_APPROVAL_LINE = re.compile(r"/aidd\s+approve(?:-spec|-merge)?\s+[A-Za-z][\w-]*-\d+\s+\S+", re.I)
_APPROVAL_RECORD = re.compile(r"refs/aidd/(?:decisions|approvals)|Aidd-Merge-Approval", re.I)
_MERGE_TRAILER_TEXT = re.compile(r"Aidd-Merge-Approval", re.I)


def only_reads(argv: list[str]) -> bool:
    """A search or a view, which may name `/aidd approve` without posting it: `grep -rn '/aidd approve' docs/`."""
    if not argv:
        return True
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if name == "sed":
        return not any(a == "-i" or a.startswith(("-i", "--in-place")) for a in args)
    if name == "git":
        return shell_parser.positional_words(args, {"-C", "-c"})[:1] in [[w] for w in _GIT_READS]
    return name in shell_parser.SEARCHERS


# A here-document's opener and its delimiter word, never a here-string (`<<<`).
_HEREDOC_OPENER = re.compile(r"(?<!<)<<-?(?!<)\s*(\S+)")


def without_file_text(command: str) -> str:
    """`command` without its here-document bodies when each only becomes a file's text: every program on the line
    is `cat` or `tee` writing files (`cat >> notes.md <<'EOF'`), or one that only reads. A body a shell, an
    interpreter, git, or any other program reads stays in, and so does every word outside the bodies. With an unquoted delimiter (`<<EOF`) bash expands the
    body, so a `$(...)` or a backtick anywhere on the line keeps it in: that may run something."""
    stripped, _ = shell_parser.split_heredocs(command)
    quoted = all(m.group(1)[:1] in ("'", '"', "\\") for m in _HEREDOC_OPENER.finditer(command))
    if stripped == command or (not quoted and ("`" in command or "$(" in command)):
        return command
    broken: list[str] = []
    for sc in shell_parser.simple_commands(stripped, broken=broken):
        argv = shell_parser.program_argv(sc.argv)
        name = shell_parser.program_name(argv[0]) if argv else ""
        if sc.after == "|" and name != "tee":
            return command  # a pipe hands the text on to a program
        if (name == "cat" and sc.out and not argv[1:]) or name == "tee" or only_reads(argv):
            continue
        return command
    return command if broken else stripped


# git commands that only read, refs and objects included: `git for-each-ref refs/aidd/decisions` lists, never records.
_GIT_READS = ("grep", "log", "show", "diff", "blame", "for-each-ref", "show-ref", "rev-parse", "rev-list", "cat-file", "shortlog")


def _describes_only(argv: list[str]) -> bool:
    """A command whose text goes where the gate never reads an approval: a commit message, or a pull or merge request's
    title and description (the gate reads approval lines from comments alone). It may mention `/aidd approve`."""
    if not argv:
        return True
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    words = shell_parser.positional_words(args, {"-C", "-c", *GH_VALUE_FLAGS, "-m", "--message", "-t", "--title", "-d", "--description"})
    if name == "git":
        return words[:1] == ["commit"]
    if name == "gh":
        return words[:2] in (["pr", "create"], ["pr", "edit"])
    if name == "glab":
        return words[:2] in (["mr", "create"], ["mr", "update"])
    return False


# Text that approves when a person's terminal runs it: `aidd approve`, `aidd land`, `aidd publish` (also as `python -m aidd.cli`), a
# proposal's `decide` and `sign-off`, `/aidd approve`, and the decision records.
APPROVAL_TEXT = re.compile(
    r"\baidd(?:\.cli|\.__main__)?\s+(?:approve|land|publish)\b|\baidd(?:\.cli|\.__main__)?\s+proposal\b[^\n;&|]*?\b(?:decide|sign-off)\b"
    r"|/aidd\s+approve|refs/aidd/(?:decisions|approvals)|Aidd-Merge-Approval",
    re.I,
)
# Each describing program's flags whose value is a message or a title: text the gate never reads as a record, the one
# place a command that only describes may name the decision records' ref.
_MESSAGE_FLAGS = {"git": ("-m", "--message"), "gh": ("-b", "--body", "-t", "--title"), "glab": ("-d", "--description", "-t", "--title")}


def _brace_variants(text: str, limit: int = 64) -> tuple[list[str], bool]:
    """`text` as bash's brace expansion may turn it into words (`approval{s,}`): each variant, at most `limit`, and
    whether that was all of them. A quoted brace bash leaves alone is expanded here too, so the reading fails closed."""
    todo, done = [text], list[str]()
    while todo and len(done) + len(todo) <= limit:
        t = todo.pop()
        m = re.search(r"\{([^{}]*,[^{}]*)\}", t)
        if m is None:
            done.append(t)
            continue
        todo.extend(t[: m.start()] + part + t[m.end() :] for part in m.group(1).split(","))
    return done + todo, not todo


def _as_git_reads(text: str) -> str:
    """Text as git may receive it: each brace variant bash could make, with each run of slashes as one, the way git
    reads a ref name (`refs/aidd//decisions` is the decision records' ref). The match on it ignores case: on a case-insensitive
    disk, an upper-case spelling names the same file. Braces with more variants than the guard reads read as the
    decision records' ref itself, failing closed: the variants the guard did not read could spell any name."""
    variants, complete = _brace_variants(text)
    read = " ".join(re.sub(r"/{2,}", "/", v) for v in variants)
    return read if complete else f"{read} {workitems.DECISIONS_REF}"


def _outside_messages(sc: shell_parser.SimpleCommand) -> str:
    """A simple command's text without its message values: environment assignments, wrapper words, and every other
    argument stay, and only the described program's own message flags are skipped."""
    argv = shell_parser.program_argv(sc.argv)
    lead = sc.argv[: len(sc.argv) - len(argv)]  # assignments and wrappers before the program
    flags = _MESSAGE_FLAGS.get(shell_parser.program_name(argv[0]), ()) if argv else ()
    out, skip = list(lead) + argv[:1], False
    for a in argv[1:]:
        if skip:
            skip = False
        elif a in flags:
            skip = True
        elif not a.startswith(tuple(f"{f}=" for f in flags if f.startswith("--"))):
            out.append(a)
    return " ".join(out)


_DOCUMENT_WRITERS = frozenset({"echo", "printf", "cat", "tee"})
_UNREAD_PATH = re.compile(r"[$`*?\[{~]")


def _writes_documents(sc: shell_parser.SimpleCommand, root: str) -> bool:
    """Whether `sc` only puts text into files of the repository at `root`: `echo`, `printf`, `cat`, or `tee`, named
    plainly, whose every target (a redirect, tee's files) is a plain path under `root`, outside each git directory, and
    no device: the text lands there as the Write tool would put it, and reaches no program that posts or records."""
    import os
    from pathlib import Path

    argv = shell_parser.program_argv(sc.argv)
    if not argv or argv != sc.argv or shell_parser.program_name(argv[0]) not in _DOCUMENT_WRITERS:
        return False
    targets = list(sc.out) + (shell_parser.positional_words(argv[1:], {"--output-error"}) if shell_parser.program_name(argv[0]) == "tee" else [])
    top = Path(os.path.realpath(root))
    for t in targets:
        if t == "/dev/null":
            continue
        real = Path(os.path.realpath(t if os.path.isabs(t) else top / t))
        if not t or _UNREAD_PATH.search(t) or ".." in Path(t).parts or not real.is_relative_to(top):
            return False
        if any(p.casefold() == ".git" for p in real.relative_to(top).parts) or (real.exists() and not real.is_file()):
            return False
    return True


def approval_text_denial(text: str, simple: list[shell_parser.SimpleCommand], root: str | None) -> str | None:
    """Why the simple commands of `text`, a line that does more than read, carry an approval, or None. Text that only
    lands in the repository's files (_writes_documents), as a doc or a test that mentions an approval does, carries
    none, the same as an edit with the Write tool. A commit message
    or a PR/MR description may mention the approval command, yet never hold a line that reads as one. A command that
    only describes may name the decision records' ref inside its message: that writes no record. Anywhere else (an option, an
    editor or hook a `-c` names, an environment value) it may run one. A merge approval's trailer stays denied
    anywhere: text that reads as a record is never an agent's. The names are read as bash passes them on, too: quoting
    splits a name in the raw text (`approval"s"`), and bash joins it again."""
    if root and all(only_reads(shell_parser.program_argv(sc.argv)) or _writes_documents(sc, root) for sc in simple):
        return None
    describes = not _APPROVAL_LINE.search(text) and all(
        only_reads(shell_parser.program_argv(sc.argv)) or _describes_only(shell_parser.program_argv(sc.argv)) for sc in simple
    )
    if _AIDD_APPROVE.search(text) and not describes:
        return "the command carries `/aidd approve`: an approval is a human's to post, never an agent's. Leave the line out, and ask the author or an Approver to post it"
    named_outside = any(_APPROVAL_RECORD.search(_as_git_reads(_outside_messages(sc))) for sc in simple)
    named = _APPROVAL_RECORD.search(text) or named_outside
    if named and not (describes and not named_outside and not _MERGE_TRAILER_TEXT.search(text)):
        return (
            f"the command names {workitems.DECISIONS_REF} or {workitems.MERGE_TRAILER}, where local approvals are recorded. An approval is a "
            "person's: they type `approve <ID>` at the prompt, and aidd records it. An agent only reads those approvals"
        )
    return None
