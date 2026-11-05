"""The summary of the worktree's last `aidd test` run, for `aidd status` to show beside the Spec the run tested.

It is for a person to read and is never evidence: the runner's exit code on a commit is. The summary names the tested
commit, the head now, how far behind it is, the verdict `aidd test` exits on, and when the run wrote its evidence. It
belongs to the one Spec the run's base-to-head diff holds. A run in another worktree or in CI never shows, because the
evidence file is this worktree's own.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from aidd import config, workitems
from aidd.kernel import git
from aidd.kernel.regular_files import NOT_REGULAR, link_on_the_way, regular_file_bytes
from aidd.testing import verdict

# An evidence.json names its results, never their logs; aidd reads no more than this of one.
EVIDENCE_MAX_BYTES = 4 * 1024 * 1024


SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def note(why: str, step: str) -> str:
    """One whole sentence: why aidd shows no summary of the last test run, and the step that brings it back."""
    return f"aidd shows no summary of the last test run because {why}: {step}"


def last_run_summary(cfg: config.Config | None, repo: str = ".", out_dir: str = config.EVIDENCE_DIR) -> tuple[tuple[str, dict] | None, str]:
    """The Spec the last run tested (its path) and the run's summary, or None; and a plain note saying why the evidence was
    not used, when there is a file that cannot be (a link, too large, a commit name that is no full hex id), else "".
    None with no note means there is no evidence, the commit is gone, or the run's diff holds no Spec or more than one.

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
        return None, note(f"git tracks {out_dir} or a file in it", f"run `git rm --cached -r ':(icase){out_dir}'`, then run `aidd test`.")
    data, why = regular_file_bytes(Path(repo), rel, EVIDENCE_MAX_BYTES)
    if data is None:
        return None, "" if why not in (NOT_REGULAR,) else note(f"{rel} is a link or not a regular file", "remove it, then run `aidd test`.")
    if len(data) > EVIDENCE_MAX_BYTES:
        return None, note(f"{rel} is larger than {EVIDENCE_MAX_BYTES // (1024 * 1024)} MiB", "remove it, then run `aidd test`.")
    try:
        evidence = json.loads(data)
        tested, base = str(evidence["head_sha"]), str(evidence["base_sha"])
        results = evidence["results"]
        at = dt.datetime.fromtimestamp((Path(repo) / out_dir / "evidence.json").stat().st_mtime, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, ValueError, KeyError, TypeError, RecursionError):  # a file nested deeper than the parser reads is unreadable too
        return None, note(f"{rel} cannot be read", "remove it, then run `aidd test`.")
    if not SHA.fullmatch(tested) or not SHA.fullmatch(base):
        return None, note(f"{rel} names a commit that is not a full lowercase hex id", "remove it, then run `aidd test`.")
    if not isinstance(results, list) or not all(isinstance(r, dict) for r in results):
        return None, note(f"{rel} cannot be read", "remove it, then run `aidd test`.")
    specs_dir = cfg.specs_dir if cfg else "specs"
    try:
        head = git.rev_parse("HEAD", repo)
        files = git.numstat(base, tested, repo)
        specs = workitems.find_specs_in_diff(files, specs_dir, lambda p: git.show(tested, p, repo))
        verdict_code = verdict.exit_code(evidence)
    except (git.GitError, KeyError, TypeError, RecursionError):
        return None, ""
    if len(specs) != 1:
        return None, ""
    summary: dict = {"commit": tested[:7], "head": head[:7]}
    if tested != head and git.ok(["merge-base", "--is-ancestor", "--end-of-options", tested, head], repo):
        summary["behind"] = int(git.run(["rev-list", "--count", "--end-of-options", f"{tested}..{head}"], repo).strip())
    partial = evidence.get("partial") or evidence.get("dirty_tree")
    summary["result"] = "partial" if partial else "passed" if verdict_code == 0 else "failed"
    summary["at"] = at
    return (specs[0], summary), ""
