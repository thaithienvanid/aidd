"""Build the repository an eval case seeds, offline, and read what today's aidd says of it: the helper behind
test_eval_fixtures_plugin and test_eval_fixtures_team_*. A fixture is a `fixture.sh` that `claude plugin eval --scaffold` runs
in the case's workspace, with no model and no agent, so building one here is the case's own start.

Building and reading a case takes about half a second, so the cases are shared out over several test files, each inside the time
budget of a test file. A case goes to a file by a checksum of its name, so adding a case never moves another one.
"""

import functools
import os
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from helpers import ROOT, aidd_here

from aidd.evals import worlds
from aidd.setup import migrating

EVALS = ROOT / "evals"
# A fixture that is stale on purpose, by `suite/case`: the reason, and the error `aidd validate` gives it. A case listed here that
# becomes valid fails its test, so the list cannot go stale itself. No fixture may hold a retired name, listed or not: what
# `aidd upgrade` would migrate must be empty in every one.
STALE_BY_DESIGN: dict[str, tuple[str, str]] = {
    "plugin/unrelated-request": ("a few Python files and no aidd: the case shows a request that has nothing to do with aidd", "no .aidd/config.yaml"),
    "team/design-review-without-a-spec": (
        "a changed screen in a project that has not adopted aidd: the case has no Spec and no config",
        "no .aidd/config.yaml",
    ),
    "team/onboard-stays-read-only": ("a project aidd has not been set up in: onboarding must map it and write nothing", "no .aidd/config.yaml"),
    "team/onboard-starts-the-security-engineer-on-deep-auth": (
        "a service with no aidd config: onboarding starts the roles that read it",
        "no .aidd/config.yaml",
    ),
    "team/performance-measures-first": ("one slow page and a query counter, with no aidd: the case measures before it changes", "no .aidd/config.yaml"),
    "team/prototype-fidelity-before-done": (
        "a bare prototype and no Spec or config: the designer's fidelity pass reads its screenshots",
        "no .aidd/config.yaml",
    ),
    "team/mvp-skeleton-runs-the-lightest-specify": (
        "SPEC-1 is mid-Specify: its tests hold TODO and it has no observe block, which the Specify the case runs writes",
        "missing required field 'observe'",
    ),
    "team/refine-proposes-never-applies": ("thin drafts on purpose: the backlog the refine pass reads, as the fixture says", "missing required field 'goal'"),
}


def case_folders(suite: str, shard: int = 0, shards: int = 1) -> list[Path]:
    """The cases of a suite ("plugin" or "team") that seed a workspace with their own `fixture.sh`, sorted, in shard `shard` of `shards`.
    The trigger cases of the team suite are written from data and share one minimal fixture, which the team's first file builds once."""
    return sorted(p.parent for p in (EVALS / suite).glob("*/fixture.sh") if zlib.crc32(p.parent.name.encode()) % shards == shard)


def build(fixture: Path, into: Path) -> None:
    """Run a fixture in the empty folder `into`, as the eval runner does in the case's workspace, then make it a git repository if the case
    leaves it none, because `aidd validate` works in one and the agent would run `git init` itself."""
    env = {**os.environ, "HOME": str(into), "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    subprocess.run(["bash", str(fixture)], cwd=into, env=env, check=True, capture_output=True, text=True, timeout=60)
    if not (into / ".git").exists():
        subprocess.run(["git", "init", "-q", "."], cwd=into, env=env, check=True, capture_output=True, text=True, timeout=60)


def languages_held(tree: Path, file: dict) -> set[str]:
    """The languages of `worlds.json` whose marker a file of the project has, by its suffix or its name. A folder that starts with a dot
    (git, aidd, and the harnesses' files), a bare repository, and `bin/` (the stand-in programs a case logs its calls with) hold no
    project file."""
    names: set[str] = set()
    for top, folders, found in os.walk(tree):
        folders[:] = [f for f in folders if not f.startswith(".") and not f.endswith(".git") and not (f == "bin" and Path(top) == tree)]
        names |= set(found)
    return {
        language
        for language, entry in file["languages"].items()
        for name in names
        if any(name == marker or (marker.startswith(".") and Path(name).suffix == marker) for marker in entry["markers"])
    }


def language_problem(name: str, world: str, held: set[str], file: dict) -> str | None:
    """Why the project a case builds is not the world it names, or None when it holds that world's language and no other."""
    want = file["worlds"][world]["language"]
    if held != ({want} - {worlds.NO_LANGUAGE}):
        return f"{name} names the world {world}, whose language is {want}, but its fixture holds {', '.join(sorted(held)) or 'no source file'}"
    return None


@functools.cache
def live_worlds() -> dict[str, str]:
    """The world each live case names, by `suite/case`."""
    return {f"{row['suite']}/{row['id']}": worlds.one_world(row) for row in worlds.case_worlds(ROOT)}


def check(test: unittest.TestCase, name: str, fixture: Path) -> None:
    """Build a case in a new folder and hold it to three rules. What `aidd upgrade` would migrate is empty, listed or not: that is every
    retired name and shape (`migrating.plan` is the part of the upgrade that reads work items and the config, and its other parts write
    files an eval workspace never holds). `aidd validate` passes, unless the case is stale by design: then it must fail as listed. The
    project holds the language of the world the case names."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        build(fixture, work)
        out_of_date = [f"{kind}: {line}" for kind, line in migrating.plan(work).lines if kind in ("migrate", "manual")]
        checked = aidd_here("validate", cwd=work)
        file = worlds.worlds_file(ROOT)
        world = live_worlds().get(name)
        held = languages_held(work, file)
    if world in file["worlds"]:
        test.assertIsNone(language_problem(name, world, held, file))
    said = checked.stdout + checked.stderr
    test.assertEqual(out_of_date, [], f"{name} holds a name or shape `aidd upgrade --yes` would migrate: change its fixture, samples, and graders")
    if name in STALE_BY_DESIGN:
        reason, error = STALE_BY_DESIGN[name]
        test.assertNotEqual(checked.returncode, 0, f"{name} is valid now: remove it from STALE_BY_DESIGN ({reason})")
        test.assertIn(error, said, f"{name} fails for another reason than the listed one")
    else:
        test.assertEqual(checked.returncode, 0, f"{name} is no valid aidd repository in today's shape:\n{said}")


def check_suite(test: unittest.TestCase, suite: str, shard: int = 0, shards: int = 1) -> None:
    for folder in case_folders(suite, shard, shards):
        with test.subTest(case=f"{suite}/{folder.name}"):
            check(test, f"{suite}/{folder.name}", folder / "fixture.sh")


def listed_cases_exist(test: unittest.TestCase, suite: str) -> None:
    """Every case `STALE_BY_DESIGN` names for a suite is a case of it."""
    names = {f"{suite}/{p.name}" for p in case_folders(suite)}
    test.assertEqual({n for n in STALE_BY_DESIGN if n.startswith(f"{suite}/")} - names, set())
