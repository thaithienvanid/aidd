"""Maintainers: build `aidd.pyz`, the whole CLI as one zipapp (PEP 441) that any Python 3.11+ runs with no install.

    python -m aidd.pyz dist-pyz/aidd.pyz      # from a source checkout, with src/ on PYTHONPATH

It holds the `aidd` package and, under aidd/_data, the same data the wheel carries (resources._LAYOUT): the
schemas, the skill, the CI templates, the aidd-team plugin, and the standards library and stacks. From a git checkout it
packs only the files git tracks. At run time `resources.data_dir` extracts that folder once into the user's cache. Standard library only: `zipapp` writes the archive. With SOURCE_DATE_EPOCH set
(the release sets it from the tag commit), every entry carries that time and the build is reproducible.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

from aidd.kernel import git, resources

INTERPRETER = "/usr/bin/env python3"
# The archive's entry point. zipapp's own `main=` template drops the return value, so the exit code would be lost.
MAIN = """import sys

if sys.version_info < (3, 11):
    sys.exit("aidd needs Python 3.11 or later; this is " + sys.version.split()[0])

from aidd.cli import main

sys.exit(main())
"""
# Never bundled: bytecode, and the local `results/` folders plugin evals write (ignored by git, and possibly large or private).
_SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store", "results", "node_modules")


def tracked_files(root: Path) -> list[str] | None:
    """The files git tracks in the checkout at `root`, as paths from it, so a build packs no file git ignores, such as
    a local `.env`, as the wheel packs none. None when `root` is no git checkout, such as an unpacked sdist: the build
    then walks the tree."""
    if not (root / ".git").exists():
        return None
    return sorted(p for p in git.run(["ls-files", "-z"], str(root)).split("\0") if p)


def build(out: Path, root: Path | None = None) -> Path:
    """Write the zipapp to `out` from the source checkout at `root` (default: the one this aidd runs from)."""
    root = root or resources.repo_root()
    if root is None:
        raise RuntimeError("aidd.pyz builds from a source checkout of aidd; this aidd is installed")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        places = {"src/aidd": stage / "aidd", **{rel: stage / "aidd" / "_data" / name for name, rel in resources._LAYOUT.items()}}
        tracked = tracked_files(root)
        for rel, dest in places.items():
            if tracked is None:
                shutil.copytree(root / rel, dest, ignore=_SKIP)
                continue
            for file in tracked:
                inside = file.removeprefix(rel + "/")
                if inside != file and (root / file).is_file() and not set(_SKIP(rel, inside.split("/"))):
                    (dest / inside).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / file, dest / inside)
        (stage / "__main__.py").write_text(MAIN, encoding="utf-8")
        epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if epoch:
            stamp = max(int(epoch), 315532800)  # zip timestamps start in 1980
            # Not through a link where the OS can (Windows cannot, and copytree left no links to follow).
            nofollow = os.utime in os.supports_follow_symlinks
            for path in [stage, *stage.rglob("*")]:
                os.utime(path, (stamp, stamp), follow_symlinks=not nofollow)
        out.parent.mkdir(parents=True, exist_ok=True)
        zipapp.create_archive(stage, out, interpreter=INTERPRETER, compressed=True)
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m aidd.pyz OUT.pyz", file=sys.stderr)
        return 2
    print(build(Path(args[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
