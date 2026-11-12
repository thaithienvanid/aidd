"""Shared fixtures for the `aidd init` plan tests: a repository, its files and folders, and the plan of one run."""

import contextlib
import io
import os
from pathlib import Path

from helpers import git

from aidd import setup
from aidd.cli import parser
from aidd.cli.commands import setup as setup_commands

# Each case is the flags of one run. Together they set every flag that changes what init writes.
FLAGS = [
    [],
    ["--profile", "team", "--approvers", "@a", "--approvers", "@b", "--specialist", "security=@s", "--delegate", "--harness", "claude-code"],
    ["--ci", "gitlab", "--environment", "production=main", "--environment", "production=refs/tags/v*", "--own-environment", "dev=dev"],
    ["--ci", "github", "--security-ci", "--compliance-target", "soc2", "--compliance-target", "gdpr", "--claude-plugins", "--ref", "v1.0.0"],
    ["--environment", "none", "--devcontainer", "--link", ".cursor/skills"],
    ["--harness", "codex", "--harness", "opencode", "--harness", "copilot", "--aidd-team"],
    ["--no-skill", "--harness", "none", "--test", "make check"],
]


def repo(parent: str, name: str = "r") -> Path:
    """A repository with a Python file and a GitHub remote, so detection, CI, and the identity are the same in every copy."""
    root = Path(parent).resolve() / name
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Maya Lee")
    git(root, "config", "user.email", "maya@users.noreply.github.com")
    git(root, "remote", "add", "origin", "https://github.com/o/r.git")
    (root / "app.py").write_text("print(1)\n", encoding="utf-8")
    return root


def files_of(root: Path) -> dict[str, str]:
    """Every file under `root` but `.git`, by its path, with its text; a link as `-> target`."""
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel == ".git" or rel.startswith(".git/"):
            continue
        if path.is_symlink():
            out[rel] = "-> " + os.readlink(path)
        elif path.is_file():
            out[rel] = path.read_text(encoding="utf-8", errors="replace")
    return out


def folders_of(root: Path) -> set[str]:
    """Every folder under `root` but `.git`, by its path."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_dir() and not p.is_symlink() and ".git" not in p.relative_to(root).parts}


def plan_of(root: Path, flags: list[str]):
    """The plan `aidd init <flags>` makes in `root`, through the same options the command builds."""
    args = parser.build_parser().parse_args(["init", "--dry-run", *flags])
    with contextlib.chdir(root), contextlib.redirect_stdout(io.StringIO()):
        options, _ = setup_commands._init_options(args, root, setup.detect(root))
        return setup.plan_init(root, options), options
