"""The repository the migration tests start from: an adopted one with a fixture tree written over it (tests/fixtures/migration)."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, build_once, git

from aidd import setup
from aidd.kernel import documents
from aidd.setup import adoption

FIXTURES = ROOT / "tests" / "fixtures" / "migration"
CONFIG = ".aidd/config.yaml"
WRITTEN = [
    CONFIG,
    "specs/INT-1.md",
    "specs/INT-2.md",
    "specs/INT-3.md",
    "specs/SPEC-1.md",
    "specs/SPEC-2.md",
    "specs/SPEC-3.md",
    "specs/explore/pick/exploration.md",
    "proposals/PROP-1/proposal.md",
    "docs/runbooks/RB-1.md",
    "docs/postmortems/PM-1.md",
    "docs/design/app/sitemap.json",
    "docs/standards/python/ruff-lint-format.md",
]


def tree(root: Path) -> dict[str, str]:
    """Every file under `root` but git's own, by its path, as a hash of its bytes."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def parsed(root: Path, rel: str) -> dict:
    text = (root / rel).read_text(encoding="utf-8")
    if rel.endswith(".json"):
        return json.loads(text)
    return documents.split_front_matter(text, rel)[0] if rel.endswith(".md") else documents.parse_yaml(text, rel)


def commit(root: Path) -> str:
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "day 0")
    return git(root, "rev-parse", "HEAD")


class Repo(RepoTemplateCase):
    """An adopted repository (with the delivery team's files, so the files an upgrade reads the config for are there) with one
    fixture tree written over it."""

    shape = "pre"

    @classmethod
    def build_template(cls, root: Path) -> None:
        def build() -> None:
            git(root, "init", "-q", "-b", "main")
            adoption.init(
                root, adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@x"], aidd_team=True, harnesses=["claude-code"], ref="v1.0.0")
            )

        build_once(("migration", "adopted"), root, build)

    def setUp(self):
        super().setUp()
        shutil.copytree(FIXTURES / self.shape, self.root, dirs_exist_ok=True)

    def clone(self) -> Path:
        """A copy of the working tree in a folder of its own, as a new repository."""
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        target = Path(other.name) / "r"
        shutil.copytree(self.root, target, ignore=shutil.ignore_patterns(".git"))
        git(target, "init", "-q", "-b", "main")
        return target

    def upgrade(self, *, yes: bool = False) -> list[str]:
        return setup.upgrade(self.root, ref="v1.0.0", yes=yes)
