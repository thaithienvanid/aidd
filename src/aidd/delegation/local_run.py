"""The check's own test runs, with no remote to read: `aidd test` on the exact head, in a fresh worktree it removes, so
nothing a session left in its own worktree, such as `.aidd/evidence/`, counts."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from aidd import config, testing, workitems
from aidd.kernel import documents, git, globs


def run_on_head(cwd: str, head: str, base: str, spec: str | None = None) -> tuple[dict | None, str]:
    """The evidence of `aidd test` on `head` against `base`, run in a fresh `git worktree add --detach`, and "" or why it
    could not run. With `spec`, it runs that Spec's tests, red on the base too."""
    folder = tempfile.mkdtemp(prefix="aidd-delegate-")
    try:
        git.run(["worktree", "add", "--quiet", "--detach", "--force", folder, head], cwd)
        evidence, _notes = testing.run_tests(repo=folder, base=base, spec=spec, out_dir=str(Path(folder) / config.EVIDENCE_DIR))
        return evidence, ""
    except (OSError, RuntimeError, ValueError, git.GitError, documents.DocumentError, config.ConfigError) as exc:
        return None, documents.one_line(str(exc), 300)
    finally:
        git.run(["worktree", "remove", "--force", folder], cwd, check=False)
        shutil.rmtree(folder, ignore_errors=True)
        git.run(["worktree", "prune"], cwd, check=False)


def suite_problem(evidence: dict | None, why: str) -> str:
    """Why a local merge's suite run fails it, or "": it did not run, ran no test, or a result is bad."""
    if evidence is None:
        return f"aidd test could not run on the head: {why}"
    if not evidence.get("results"):
        return "no test ran on the head, so nothing shows the change works"
    if evidence.get("before_implement") or testing.exit_code(evidence):
        bad = [r["name"] for r in evidence["results"] if testing.result_mark(r, before_implement=False) == "!!"]
        return "aidd test failed on the head: " + (", ".join(bad[:5]) or "the tree was not clean")
    return ""


def red_problem(evidence: dict | None, why: str) -> str:
    """Why a Spec's run shows no red on the base, or "": every new test failed there for a real reason."""
    if evidence is None:
        return f"the Spec's tests could not run: {why}"
    red = [r for r in evidence.get("results", []) if r.get("red_green") == "red"]
    if not red:
        return "no new-behavior test ran on the base"
    weak = [r["name"] for r in red if not testing.red_ok(r)]
    return f"these tests did not fail on the base for a real reason: {', '.join(weak[:5])}" if weak else ""


def frozen_problem(cwd: str, head: str, spec_path: str, spec: dict, approval: str) -> str:
    """Why the files a Spec's approval froze differ at the head, or "": each is byte-identical to the commit the
    approval covers, by its blob, so a rename, a removal, or a new file under a frozen glob counts. The list is the
    approved Spec's and the head's together, so a head that drops a file from `tests.files` still has it compared."""
    found = spec_in(cwd, approval, spec_path.split("/")[0], str(spec.get("id", "")))
    if found is None or found[1] is None:
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
    return f"{', '.join(moved[:5])} differ from the approved commit {approval[:12]}" if moved else ""


def spec_in(cwd: str, ref: str, folder: str, spec_id: str) -> tuple[str, dict | None] | None:
    """The Spec with `spec_id` in `ref`'s tree under `folder`, found by its id: its path, and its front matter, or None
    when it does not parse. None when no Spec there has the id."""
    for path in sorted(p for p in git.ls_tree(ref, cwd, paths=[folder]) if p.endswith(".md")):
        data, _, errs = workitems.load_object(git.show(ref, path, cwd) or "", path)
        if data.get("id") == spec_id:
            return path, None if errs else data
    return None


def _matching(tree: dict[str, str], patterns: list[str]) -> dict[str, str]:
    return {p: oid for p, oid in tree.items() if globs.match_any(patterns, p)}
