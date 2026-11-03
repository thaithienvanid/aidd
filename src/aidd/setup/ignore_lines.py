"""What a test run or a build leaves in the tree, and the .gitignore lines that keep it out of git.

`aidd test` counts an untracked file git does not ignore as a dirty tree, and the gate takes no evidence from one. So
`aidd init` and `aidd upgrade` append the outputs of each stack `detection` finds, and the files macOS and Windows leave
in any folder (OS_FILES), each under its own mark, and uninstall takes back those blocks alone. The lines follow GitHub's gitignore templates. An output git already ignores is
never added, nor one that would hide a file the project commits, such as a `bin/` of scripts.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from aidd.kernel import git

TEST_OUTPUTS_MARK = "# aidd: what tests and builds leave stays out of git, so `aidd test` runs in a clean tree"
# The block aidd 1.0 wrote for Python alone: still aidd's to take back, and still a sign its lines are there.
BYTECODE_MARK = "# aidd: Python bytecode stays out of git, so `aidd test` runs in a clean tree"
BYTECODE_LINES = ("__pycache__/", "*.pyc")

# Each stack `detection` names, with what its tests and builds leave. No `dist/`: a test run rarely writes it, and
# some projects commit it, such as a GitHub Action.
OUTPUTS: dict[str, tuple[str, ...]] = {
    "Python": (*BYTECODE_LINES, ".pytest_cache/", ".coverage", "htmlcov/", ".mypy_cache/", ".ruff_cache/"),
    "JavaScript/TypeScript": ("node_modules/", "coverage/", ".nyc_output/", "test-results/", "playwright-report/"),
    "Rust": ("target/",),
    "Go": ("coverage.out", "*.test"),
    "Java (Maven)": ("target/",),
    "JVM (Gradle)": ("build/", ".gradle/"),
    ".NET": ("bin/", "obj/", "TestResults/"),
    "C/C++ (CMake)": ("build/", "CMakeFiles/", "CMakeCache.txt", "*.gcda", "*.gcno"),
    "Dart/Flutter": (".dart_tool/", "build/"),
}
# What macOS and Windows leave in a folder a person opens, in any project, as GitHub's macOS and Windows templates list:
# a person's own global excludes file often holds them, but a teammate's clone and CI never read it.
OS_FILES = (".DS_Store", "Thumbs.db", "desktop.ini")
OS_FILES_MARK = "# aidd: what macOS and Windows leave stays out of git, so `aidd test` runs in a clean tree"
KNOWN = frozenset([*(line for lines in OUTPUTS.values() for line in lines), *OS_FILES])


def _sample(line: str) -> str:
    """A path at the top that `line` ignores: a file in the folder it names, or a file its pattern names."""
    return line.rstrip("/") + "/aidd-sample" if line.endswith("/") else line.replace("*", "aidd-sample")


def _ignored_by_lines(lines: list[str], sample: str) -> bool:
    """Outside git: whether a .gitignore line ignores `sample`'s first part by name, as `__pycache__/` or `*.py[cod]` does."""
    name = sample.split("/")[0]
    for line in lines:
        pattern = line.strip().removeprefix("**/").removeprefix("/").rstrip("/")
        if pattern and not pattern.startswith(("#", "!")) and "/" not in pattern and fnmatch.fnmatchcase(name, pattern):
            return True
    return False


def _in_git(root: Path) -> bool:
    return (root / ".git").exists() and bool(git.toplevel(str(root)))


def _ignored_by_git(root: Path, samples: list[str]) -> set[str]:
    """The samples the repository's own .gitignore files ignore. The person's global excludes file and the clone's
    `.git/info/exclude` are left out, because a teammate's clone and CI never read them. With `-v`, git names the file
    whose line decides each sample, the match of highest precedence, so a sample only info/exclude covers names it."""
    args = ["-c", f"core.excludesFile={os.devnull}", "check-ignore", "-v", "--no-index", "--stdin", "-z"]
    fields = git.run(args, str(root), check=False, input="\0".join(samples) + "\0").split("\0")
    matches = zip(fields[0::4], fields[2::4], fields[3::4], strict=False)  # (source, pattern, path); the line number is unused
    return {path for source, pattern, path in matches if path and PurePosixPath(source).name == ".gitignore" and not pattern.startswith("!")}


def _hides_a_tracked_file(root: Path, line: str) -> bool:
    """Whether `line` matches a file git tracks: the project commits what is there, so it is no test output."""
    return bool(git.run(["ls-files", "-z", "--cached", "--ignored", f"--exclude={line}"], str(root), check=False).strip("\0"))


def python_project(root: Path) -> bool:
    """A pyproject.toml or setup.py at the top, or a tracked `.py` file (outside git, one in the top two folders)."""
    if any((root / name).is_file() for name in ("pyproject.toml", "setup.py")):
        return True
    if _in_git(root):
        return bool(git.run(["ls-files", "-z", "--", "*.py"], str(root), check=False).strip("\0"))
    return next(root.glob("*.py"), None) is not None or next(root.glob("*/*.py"), None) is not None


def missing_ignore_lines(root: Path, gitignore_text: str, stacks: Iterable[str]) -> list[str]:
    """The blocks a .gitignore lacks: TEST_OUTPUTS_MARK and each output of these stacks, then OS_FILES_MARK and each of
    OS_FILES, each line one git does not already ignore and the project does not commit. A block already there adds
    nothing, so a line a person deleted from it stays deleted; the two are apart, so a stack found later still adds its
    own."""
    lines = gitignore_text.splitlines()
    names = set(stacks) | ({"Python"} if python_project(root) else set())
    outputs = [] if TEST_OUTPUTS_MARK in lines else list(dict.fromkeys(line for stack, out in OUTPUTS.items() if stack in names for line in out))
    wanted = outputs + ([] if OS_FILES_MARK in lines else list(OS_FILES))
    if _in_git(root):
        ignored = _ignored_by_git(root, [_sample(line) for line in wanted]) if wanted else set()
        add = [line for line in wanted if _sample(line) not in ignored and not _hides_a_tracked_file(root, line)]
    else:
        add = [line for line in wanted if not _ignored_by_lines(lines, _sample(line))]
    stack_lines, os_lines = [x for x in add if x in outputs], [x for x in add if x not in outputs]
    return ([TEST_OUTPUTS_MARK, *stack_lines] if stack_lines else []) + ([OS_FILES_MARK, *os_lines] if os_lines else [])


def ignore_lines_reason(block: list[str]) -> str:
    """The one sentence init and upgrade print for the block they add."""
    shown = [f"`{line}`" for line in block if line not in (TEST_OUTPUTS_MARK, OS_FILES_MARK)]
    listed = " and ".join(shown) if len(shown) <= 2 else ", ".join(shown[:-1]) + f", and {shown[-1]}"
    return f"what tests, builds, and your computer leave stays out of git, because `aidd test` counts an untracked file as a dirty tree: {listed}"


def without_blocks(lines: list[str]) -> list[str]:
    """`lines` without aidd's blocks: each mark, and the output lines right under it. A person's own line stays,
    and so does any line past the first one aidd never writes."""
    out: list[str] = []
    inside = False
    for line in lines:
        if line in (TEST_OUTPUTS_MARK, BYTECODE_MARK, OS_FILES_MARK):
            inside = True
            continue
        if inside and line in KNOWN:
            continue
        inside = False
        out.append(line)
    return out
