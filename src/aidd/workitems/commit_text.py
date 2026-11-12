"""What a commit message says about the work: the work item ids it names and its `Assisted-by` values.

`aidd status <path or id>` and `aidd eval work` both read commits through these rules, so they never disagree about which commit
belongs to which item or which agent wrote it. One harness has one spelling, `<harness id>/<model>`, with the ids the
harness table owns (`config.HARNESSES`), so `aidd eval work` never counts `Claude Code` apart from `claude-code`, and
`aidd validate` warns about another spelling.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

from aidd import config
from aidd.kernel import documents, git

ASSISTED_BY = re.compile(r"^assisted-by:([^\n]*)", re.IGNORECASE | re.MULTILINE)  # linear; the value is stripped in Python
ID_IN_TEXT = re.compile(r"(?<![A-Za-z0-9-])([A-Za-z][A-Za-z0-9]*-[0-9]+)(?![0-9A-Za-z])")
MAX_ASSISTED_BY = 5
# The most commits of a branch `aidd validate` reads for their `Assisted-by` spelling.
MAX_BRANCH_COMMITS = 200
_WORD = re.compile(r"[a-z0-9]+")


def work_ids_in(text: str, known: set[str]) -> list[str]:
    """The ids in `known` that `text` names, each once, in the order the text names them."""
    return [i for i in dict.fromkeys(ID_IN_TEXT.findall(text)) if i in known]


def assisted_by_values(text: str) -> list[str]:
    """The `Assisted-by` values on lines of `text` that start with that key (any case), each once and cut to one line."""
    return list(dict.fromkeys(v for m in ASSISTED_BY.findall(text) if (v := documents.one_line(m.strip(), 200))))[:MAX_ASSISTED_BY]


def _squashed(text: str) -> str:
    return "".join(_WORD.findall(text.casefold()))


@functools.cache
def _harness_ids() -> dict[str, str]:
    """Each known harness id, keyed by its id and by its name with case, spaces, and punctuation removed."""
    ids = {_squashed(key): key for key in config.HARNESSES}
    for key, harness in config.HARNESSES.items():
        ids.setdefault(_squashed(harness.label), key)
    return ids


def assisted_by_spelling(value: str) -> str:
    """`value` spelled as `<harness id>/<model>`: a known harness by its id whatever its case or spacing (`Claude Code`
    is `claude-code`), any other harness in lowercase words joined by hyphens, and the model in lowercase with no
    spaces. A part the value lacks stays empty, as in `claude-code/`. The value is repository text, so each control or
    bidi character in it becomes a space first (`documents.one_line`), and a space a hyphen."""
    harness, _, model = documents.one_line(value, 200).strip().removeprefix("agent:").partition("/")
    harness_id = _harness_ids().get(_squashed(harness)) or "-".join(_WORD.findall(harness.casefold()))
    return f"{harness_id}/{'-'.join(model.casefold().split())}"


def _known_within(harness: str) -> list[str]:
    """The known ids that a written id holds or is part of, with case and punctuation removed: `claude` and `codex-cli`
    are `claude-code` and `codex`. Another id, such as `aider`, names a harness aidd does not know."""
    written = _squashed(harness)
    return [k for k in config.HARNESSES if written and (_squashed(k) in written or written in _squashed(k))]


def assisted_by_fix(value: str) -> str | None:
    """The spelling to write for an `Assisted-by` value that is not `<harness id>/<model>`: a known harness's id for a
    written id that holds it or is part of it, and `<harness id>` or `<model>` where no part fits. None when the value
    is spelled right, exactly (a space or a stray `agent:` is a wrong spelling too). A harness aidd does not know keeps
    its own id, because there is no rewrite to ask for."""
    harness, _, model = assisted_by_spelling(value).partition("/")
    if harness and harness not in config.HARNESSES:
        within = _known_within(harness)
        harness = within[0] if len(within) == 1 else "" if within else harness
    if harness and model and f"{harness}/{model}" == value:
        return None
    return f"{harness or '<harness id>'}/{model or '<model>'}"


def harness_ids_note(value: str) -> str:
    """The sentence that names the harness ids aidd knows, when the fix for `value` has no harness id to give; "" otherwise."""
    fix = assisted_by_fix(value)
    return f" The harness ids aidd knows are {', '.join(config.HARNESSES)}." if fix and fix.startswith("<harness id>/") else ""


def branch_assisted_by_warnings(root: Path) -> list[str]:
    """`aidd validate` warnings for the `Assisted-by` values on this branch's own commits (from its merge-base with the
    default branch, the newest MAX_BRANCH_COMMITS) that are not `<harness id>/<model>`. A commit the default branch
    holds is left alone, because its message no longer changes. Outside git it says nothing."""
    cwd = str(root)
    try:
        base = git.branch_base(cwd)
        rows = git.log_fields([f"-{MAX_BRANCH_COMMITS}", f"{base}..HEAD"], ["%H"], cwd, check=False) if base != "HEAD" else []
        bodies = git.messages([r[0] for r in rows], cwd)
    except (git.GitError, OSError, ValueError):
        return []
    wrong: dict[str, list[str]] = {}
    for (sha,) in rows:
        for value in assisted_by_values(bodies.get(sha, "")):  # each value is one clean line already
            if assisted_by_fix(value):
                wrong.setdefault(value, []).append(sha[:12])
    out = []
    for value, shas in wrong.items():
        listed = ", ".join(shas[:3]) + (", and more" if len(shas) > 3 else "")
        out.append(
            f"Assisted-by `{value}` on {len(shas)} commit{'' if len(shas) == 1 else 's'} of this branch ({listed}) is not "
            f"`<harness id>/<model>`, so `aidd eval work` counts it apart. Write `Assisted-by: {assisted_by_fix(value)}`.{harness_ids_note(value)} "
            "Reword each commit: `git commit --amend` rewords the newest one. Pushing rewritten commits is the `git.push.force` ask"
        )
    return out
