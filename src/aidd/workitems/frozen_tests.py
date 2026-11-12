"""The acceptance tests a harness ask rule guards: the `tests.files` of every Spec that Spec approval froze and that is
not finished. The rules are written from the Spec files, so a Spec's tests stop being guarded when it is done, rolled
back, cancelled, or revised to a draft (`spec.revise`), at the next `aidd upgrade --yes`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aidd import config
from aidd.workitems import status, work_list

# At or past Spec approval, and not finished: the span in which a Spec's tests are frozen.
FROZEN_STATUSES = status.IN_FLIGHT
# The most test files and globs one run guards. A Spec file is data, so Specs that list more cannot grow a harness's settings
# without bound. Past it a caller keeps the asks it wrote, and the rest have no ask.
MAX_FROZEN = 500


@dataclass(frozen=True)
class FrozenTests:
    """The frozen tests an ask rule guards: the test files and globs (at most MAX_FROZEN), the Spec files that did not parse, and
    the Spec that lists the most of them when together they pass the cap (None when they do not)."""

    paths: list[str] = field(default_factory=list)
    unreadable: list[dict] = field(default_factory=list)
    over_cap: str | None = None


def _repo_glob(path: object) -> str | None:
    """`path` as a repository-relative glob (the schema's `glob`: not absolute, no `..` segment), or None. A test section
    of a manifest (`pyproject.toml#tool.pytest`) is left out: a rule on the manifest would ask at every dependency
    bump, so no ask guards that section."""
    if not isinstance(path, str) or "#" in path:
        return None
    path = path.removeprefix("./")
    return path if path and not path.startswith("/") and ".." not in path.split("/") else None


def frozen_test_files(root: Path, cfg: config.Config | None) -> FrozenTests:
    """The test files and globs of every Spec past approval and not finished, each once, in the order of the Specs, and the
    Spec files that do not parse. While one does not, what is approved is unknown, so a caller keeps the rules it wrote."""
    found, bad = work_list.read_work(root, cfg)
    proposals = f"{(cfg or config.EMPTY).proposals_dir}/"
    unreadable = [b for b in bad if not str(b["path"]).startswith(proposals) and not str(b["error"]).startswith("type ")]
    paths: dict[str, None] = {}
    per_spec: dict[str, int] = {}
    for path, data in found:
        tests = data.get("tests")
        files = tests.get("files") if isinstance(tests, dict) else None
        if data.get("type") == "spec" and status.spec_status(data) in FROZEN_STATUSES and isinstance(files, list):
            globs = list(filter(None, map(_repo_glob, files)))
            per_spec[path] = len(globs)
            paths.update(dict.fromkeys(globs))
    biggest = max(per_spec, key=lambda k: per_spec[k]) if len(paths) > MAX_FROZEN else None
    return FrozenTests(list(paths)[:MAX_FROZEN], unreadable, biggest)
