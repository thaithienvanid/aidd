"""The summary of the worktree's last `aidd test` run, for `aidd status` to show beside the Spec the run tested.

It is for a person to read and is never evidence: the runner's exit code on a commit is. The summary names the tested
commit, the head now, how far behind it is, the verdict `aidd test` exits on, and when the run wrote its evidence. It
belongs to each Spec the run answered to, which the run's evidence names (`specs`). A run in another worktree or in CI never
shows, because the evidence file is this worktree's own.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from aidd import config
from aidd.kernel import command_names, documents, git, resources, timestamps
from aidd.kernel.regular_files import NOT_REGULAR, link_on_the_way, regular_file_bytes
from aidd.testing import verdict

# An evidence.json names its results, never their logs; aidd reads no more than this of one.
EVIDENCE_MAX_BYTES = 4 * 1024 * 1024


# The most Specs one run's summary names; a run that answers to more shows on the first of them.
MAX_SPECS = 50

SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def note(why: str, step: str) -> str:
    """One whole sentence: why aidd shows no summary of the last test run, and the step that brings it back."""
    return f"aidd shows no summary of the last test run because {why}: {step}"


# What an id in the evidence may be: the one pattern every id has. The file is data, so any other text there is no id.
_ID = re.compile(resources.load_json("common.schema.json")["$defs"]["id"]["pattern"])


# The values a result's `status` and `red_green` may hold, as the common schema lists them. A newer aidd may add one.
_RESULT_VALUES = {
    key: frozenset(resources.load_json("common.schema.json")["$defs"][name]["enum"]) for key, name in (("status", "test_status"), ("red_green", "red_green"))
}


def _unknown_values_note(results: list[dict]) -> str:
    """The note for a result that holds a `status` or `red_green` value this aidd does not list, as a newer aidd may write one,
    or "" when none does. The summary reads such a result as failed, never passed, because a value it cannot read proves nothing."""
    unknown = list(
        dict.fromkeys(
            f"{key} {documents.one_line(r[key], 40)!r}"
            for r in results
            for key in _RESULT_VALUES
            if isinstance(r.get(key), str) and r[key] not in _RESULT_VALUES[key]
        )
    )
    if not unknown:
        return ""
    return (
        f"the last aidd test run has a result with {', '.join(unknown[:3])}, which this aidd does not know, so aidd status shows the run as failed: "
        "run `aidd self-update` if a newer aidd wrote it, or run `aidd test` again"
    )


def _untrack_step(out_dir: str) -> str:
    """The step that stops git tracking the evidence folder. The folder's name is the config's text, so it joins the command only
    as a plain name (kernel.command_names); any other name gets the step in words."""
    word = command_names.quoted(out_dir)
    if word is None:
        return f"stop tracking it by hand ({command_names.NO_COMMAND})"
    return f"run `git rm --cached -r -- ':(icase){word}'`"


def _result(evidence: dict, verdict_code: int) -> str:
    """The verdict `aidd test` exits on, in a word: a run no test applied to is never `passed`."""
    if verdict_code:
        return "failed"
    if evidence.get("partial") or evidence.get("no_red"):
        return "partial"
    return "untested" if verdict.untested(evidence) else "passed"


def _facts(evidence: dict) -> dict:
    """What the evidence says that a person reading the summary must see: a dirty tree, a suite cut to its smoke set by an
    emergency Spec, and the Specs whose frozen files the change rewrote behind a revision it wrote itself. The file is data, so
    only a value of the right type counts."""
    out: dict = {}
    if evidence.get("dirty_tree"):
        out["dirty_tree"] = True
    if evidence.get("emergency_subset") is True:
        out["emergency_subset"] = True
    revised = evidence.get("revised_frozen")
    ids = (
        [r["id"] for r in revised if isinstance(r, dict) and isinstance(r.get("id"), str) and _ID.fullmatch(r["id"])][:MAX_SPECS]
        if isinstance(revised, list)
        else []
    )
    if ids:
        out["revised_frozen"] = ids
    return out


def last_run_summary(repo: str = ".", out_dir: str = config.EVIDENCE_DIR) -> tuple[tuple[list[str], dict] | None, str]:
    """The paths of the Specs the last run tested and the run's summary, or None; and a plain note saying why the evidence was
    not used, when there is a file that cannot be (a link, too large, a commit name that is no full hex id), else "".
    None with no note means there is no evidence, the commit is gone, or the run answered to no Spec.

    A repository can commit this file, so its text is data: aidd reads only a regular file inside the repository, up to
    EVIDENCE_MAX_BYTES, and passes git only the full hex ids the runner writes, never a name that could be read as an option."""
    rel = f"{out_dir}/evidence.json"
    # Evidence the repository carries is another person's text, not this worktree's run: the runner writes it untracked, in an
    # ignored folder, through no link. Anything git tracks in that folder, in any case of its letters (a case-insensitive file
    # system serves `.aidd/EVIDENCE` for `.aidd/evidence`), or as a link or file standing for the folder or a parent, is refused,
    # and so is a link anywhere on the way. The summary is never evidence, so this is a guard for a person's eyes, never a block.
    parents = [str(Path(rel).parents[i]) for i in range(len(Path(rel).parents) - 1)]
    listed = [line.partition("\t")[2] for line in git.run(["ls-files", "-s", "--", rel, *parents], repo, check=False).splitlines()]
    tracked = [path for path in listed if path in (rel, *parents)] + git.run(["ls-files", "--", f":(icase){out_dir}"], repo, check=False).splitlines()
    if link := link_on_the_way(Path(repo), rel):
        return None, note(f"a link lies on the way to {rel}", f"remove the link {link}, then run `aidd test`.")
    if tracked:
        return None, note(f"git tracks {out_dir} or a file in it", f"{_untrack_step(out_dir)}, then run `aidd test`.")
    data, why = regular_file_bytes(Path(repo), rel, EVIDENCE_MAX_BYTES)
    if data is None:
        return None, "" if why not in (NOT_REGULAR,) else note(f"{rel} is a link or not a regular file", "remove it, then run `aidd test`.")
    if len(data) > EVIDENCE_MAX_BYTES:
        return None, note(f"{rel} is larger than {EVIDENCE_MAX_BYTES // (1024 * 1024)} MiB", "remove it, then run `aidd test`.")
    try:
        evidence = json.loads(data)
        tested, base = str(evidence["head_sha"]), str(evidence["base_sha"])
        results = evidence["results"]
        tested_specs = evidence.get("specs", [])
        at = timestamps.utc_stamp(dt.datetime.fromtimestamp((Path(repo) / out_dir / "evidence.json").stat().st_mtime, dt.UTC))
    except (OSError, ValueError, KeyError, TypeError, RecursionError):  # a file nested deeper than the parser reads is unreadable too
        return None, note(f"{rel} cannot be read", "remove it, then run `aidd test`.")
    if not SHA.fullmatch(tested) or not SHA.fullmatch(base):
        return None, note(f"{rel} names a commit that is not a full lowercase hex id", "remove it, then run `aidd test`.")
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        return None, note(f"{rel} cannot be read", "remove it, then run `aidd test`.")
    if not isinstance(tested_specs, list) or not all(isinstance(p, str) for p in tested_specs[:MAX_SPECS]):
        return None, note(f"{rel} cannot be read", "remove it, then run `aidd test`.")
    try:
        head = git.rev_parse("HEAD", repo)
        verdict_code = verdict.exit_code(evidence)
    except (git.GitError, KeyError, TypeError, RecursionError):
        return None, ""
    if not tested_specs:
        return None, ""
    summary: dict = {"commit": tested[:7], "head": head[:7]}
    if tested != head and git.ok(["merge-base", "--is-ancestor", "--end-of-options", tested, head], repo):
        summary["behind"] = int(git.run(["rev-list", "--count", "--end-of-options", f"{tested}..{head}"], repo).strip())
    summary["result"] = _result(evidence, verdict_code)
    summary.update(_facts(evidence))
    summary["at"] = at
    over = len(tested_specs) - MAX_SPECS
    capped = (
        f"the last aidd test run answered to {len(tested_specs)} Specs, so aidd status shows it beside the first {MAX_SPECS} and not the other {over}: "
        "run `aidd test` for fewer Specs at a time to see each"
        if over > 0
        else ""
    )
    return (tested_specs[:MAX_SPECS], summary), "; ".join(n for n in (capped, _unknown_values_note(results)) if n)
