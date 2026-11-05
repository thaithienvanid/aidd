"""The check's own test runs, with no remote to read: `aidd test` on the exact head, in a fresh worktree it removes, so
nothing a session left in its own worktree, such as `.aidd/evidence/`, counts."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from aidd import config, testing, workitems
from aidd.kernel import documents, git, globs, retired_names


def specs_dir(cfg: config.Config | None) -> str:
    """The folder a config holds the Specs in: the tip's config, whose values decide, and `specs` with none."""
    return cfg.specs_dir if cfg else "specs"


def run_on_head(cwd: str, head: str, base: str, spec: str | None = None, *, old_shape: bool = False) -> tuple[dict | None, str]:
    """The evidence of `aidd test` on `head` against `base`, run in a fresh `git worktree add --detach`, and "" or why it
    could not run. With `spec`, it runs that Spec's tests, red on the base too. With `old_shape`, `head` is a commit the change
    does not control (the one an approval covers), so its config and Specs read in today's shape."""
    folder = tempfile.mkdtemp(prefix="aidd-delegate-")
    try:
        git.run(["worktree", "add", "--quiet", "--detach", "--force", folder, head], cwd)
        evidence, _notes = testing.run_tests(
            repo=folder, base=base, spec=spec, out_dir=str(Path(folder) / config.EVIDENCE_DIR), require_green=True, read_old_shape=old_shape
        )
        return evidence, ""
    except (OSError, RuntimeError, ValueError, git.GitError, documents.DocumentError, config.ConfigError) as exc:
        return None, documents.one_line(str(exc), 300)
    finally:
        git.run(["worktree", "remove", "--force", folder], cwd, check=False)
        shutil.rmtree(folder, ignore_errors=True)
        git.run(["worktree", "prune"], cwd, check=False)


def moved_problem(evidence: dict) -> str:
    """Why a run that used the fork point's values proves too little, or "": the target moved since the branch forked and
    changed what decides the run (`target_moved`), so the head was not held to the target's newest tests."""
    moved = evidence.get("target_moved")
    if not moved:
        return ""
    changes = "; ".join(str(c) for c in (moved.get("changes") or [])[:3])
    return f"the target moved to {str(moved.get('tip', ''))[:12]} and changed what decides this run ({changes}): update the branch from it, then check again"


def suite_problem(evidence: dict | None, why: str) -> str:
    """Why a local merge's suite run fails it, or "": it did not run, ran no test, or a result is bad."""
    if evidence is None:
        return f"aidd test could not run on the head: {why}"
    if testing.ran_nothing(evidence):
        return "no test ran on the head, so nothing shows the change works"
    if moved := moved_problem(evidence):
        return moved
    if evidence.get("untested"):
        return "no test applied to this change, so nothing shows it works: add a command with no `when_changed`, such as a lint, or a person decides"
    if evidence.get("before_implement") or testing.exit_code(evidence):
        bad = [r["name"] for r in evidence["results"] if testing.result_mark(r, before_implement=False) == "!!"]
        if evidence.get("before_implement") and not bad:
            return "aidd test excused a failing test as expected before Implement, and a merge excuses nothing"
        return "aidd test failed on the head: " + (", ".join(bad[:5]) or "the tree was not clean")
    return ""


def red_problem(evidence: dict | None, why: str) -> str:
    """Why a Spec's run shows no red on the base, or "": every new test failed there for a real reason."""
    if evidence is None:
        return f"the Spec's tests could not run: {why}"
    if moved := moved_problem(evidence):
        return moved
    red = [r for r in evidence.get("results", []) if r.get("red_green") == "red"]
    if not red:
        return "no new-behavior test ran on the base"
    weak = [r["name"] for r in red if not testing.red_ok(r)]
    return f"these tests did not fail on the base for a real reason: {', '.join(weak[:5])}" if weak else ""


def frozen_problem(cwd: str, head: str, specs_dir: str, change: tuple[str, dict], approval: str) -> str:
    """Why the files a Spec's approval froze differ at the head, or "": each is byte-identical to the commit the
    approval covers, by its blob, so a rename, a removal, or a new file under a frozen glob counts. The list is the
    approved Spec's and the head's together, so a head that drops a file from `tests.files` still has it compared."""
    spec_path, spec = change
    try:
        spec = workitems.todays_shape(spec)  # both sides in today's shape, so an upgrade alone is no change of the Spec
    except retired_names.Refused as exc:  # as unreadable: what the approval froze cannot be compared with a guess
        return f"{spec_path} cannot be read in today's shape ({exc}): make that change by hand, as `aidd upgrade` says, then check again"
    found = spec_by_id(cwd, approval, specs_dir, str(spec.get("id", "")))
    if found is None or found[3]:
        return f"the approved commit {approval[:12]} holds no Spec {spec.get('id')} that parses"
    if found[0] != spec_path:
        return f"{spec.get('id')} moved from {found[0]} to {spec_path} after its approval"
    approved = found[1]
    if approved.get("tests") != spec.get("tests"):
        return f"{spec.get('id')}'s `tests` block differs from the approved commit {approval[:12]}: a changed test command is `spec.revise`"
    said = [workitems.acceptance_ids(git.show(ref, spec_path, cwd) or "") for ref in (approval, head)]
    if said[0] != said[1]:
        return f"{spec.get('id')}'s Acceptance ids differ from the approved commit {approval[:12]}"
    frozen = list(dict.fromkeys([*workitems.frozen_files(approved), *workitems.frozen_files(spec)]))
    then, now = (_matching(git.ls_tree(ref, cwd), frozen) for ref in (approval, head))
    moved = sorted(p for p in set(then) | set(now) if then.get(p) != now.get(p))
    # A frozen section (`pyproject.toml#tool.pytest`) is its value, not its manifest's bytes: the reading `aidd test` makes too.
    moved = [p for p in moved if any(workitems.frozen_change(s, p, lambda q: (git.show(approval, q, cwd), git.show(head, q, cwd))) for s in (approved, spec))]
    return f"{', '.join(moved[:5])} differ from the approved commit {approval[:12]}" if moved else ""


def _files(cwd: str, ref: str, specs_dir: str, spec_id: str) -> Iterator[tuple[str, str]]:
    """The Markdown files under `specs_dir` at `ref` that may be the work item, as (path, text): the file named for the id first,
    then every other in path order, and never a saved request."""
    paths = [f"{specs_dir}/{spec_id}.md", *sorted(p for p in git.ls_tree(ref, cwd, paths=[specs_dir]) if p.endswith(".md"))]
    for path in dict.fromkeys(p for p in paths if not workitems.is_saved_request(p, specs_dir.rstrip("/"))):
        text = git.show(ref, path, cwd)
        if text is not None:
            yield path, text


def _item(found: Iterator[tuple[str, str]], spec_id: str, kind: str, old_shape: bool) -> tuple[str, dict, str, list[str]] | None:
    for path, text in found:
        try:
            data, _, errs = workitems.load_object(text, path, read_old_shape=old_shape)
        except documents.DocumentError:
            continue  # a README or another file with no front matter is no work item
        if data.get("id") == spec_id and data.get("type") == kind:
            return path, data, text, errs
    return None


def spec_by_id(cwd: str, ref: str, specs_dir: str, spec_id: str, kind: str = "spec") -> tuple[str, dict, str, list[str]] | None:
    """The work item of type `kind` (a Spec, or the Intent a Spec names as its parent) with `spec_id` in `ref`'s tree
    under `specs_dir`, the one folder the config names: its path, front matter, text, and the errors its file has. The
    file named for the id comes first, then every Markdown file there in path order. Only a file whose type is `kind`
    counts, and never a saved request, whatever its text says. None when no item there has the id, so a file outside the
    folder is never the item. `ref` is a commit the change does not control (the tip, an approval's commit), which may be from
    before an upgrade, so its earlier shape reads as today's (`workitems.todays_shape`): an upgrade alone is no difference."""
    return _item(_files(cwd, ref, specs_dir, spec_id), spec_id, kind, True)


def head_spec_by_id(cwd: str, head: str, specs_dir: str, spec_id: str) -> tuple[str, dict, str, list[str]] | None:
    """`spec_by_id` for the head, which is read as it is: a retired name there is an error, and `aidd upgrade --yes` the step."""
    return _item(_files(cwd, head, specs_dir, spec_id), spec_id, "spec", False)


def _matching(tree: dict[str, str], patterns: list[str]) -> dict[str, str]:
    return {p: oid for p, oid in tree.items() if globs.match_any(patterns, p)}
