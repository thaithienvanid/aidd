"""Seed each kind of miss into a scratch copy of the tree, and show `python3 tests/run.py --changed` fails on it.

    python3 tests/seeded_misses.py                 # every seed: about 30 s each
    python3 tests/seeded_misses.py --only door     # the seeds whose label has `door` in it
    python3 tests/seeded_misses.py --quick         # run only the checks a seed expects, not --changed (a minute in all)

The scratch copy is a new folder in the system's temporary folder, made from the tracked files of this tree as they are now and
committed once, so it looks like a fresh worktree with no read record. It first shows `--changed` passes on the clean copy.
Each seed then edits the copy, runs the command, and puts the file back, so the next seed starts clean. The last step shows
the command passes again. Nothing is deleted: the folder stays for you to look at.

This is how WHOLE_TREE in tests/run.py was proved to cover each kind of miss that a builder's narrow run let through. It is not a
test: it starts the runner once for each seed. tests/test_runner_prereport.py holds the seed table to the table in the runner.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# A sentence of 28 words, put into two pages: a long sentence copied between pages.
COPIED = (
    "This sentence was written once for the seeded miss and then copied to a second page so that two pages now say the very same thing in the very same words."
)
LONG_SENTENCE = (
    "This single sentence runs on and on, with clause after clause that nobody asked for, so that a reader has to hold far too many "
    "words in mind before the full stop finally comes along to end it."
)

# Each seed: its label, the test files that must fail (without `test_`), and its edits. An edit is ("append", path, text),
# ("replace", path, old, new) for the first `old`, ("after", path, anchor, text) after the first `anchor`, or ("new", path, text).
SEEDS: list[tuple[str, tuple[str, ...], list[tuple[str, ...]]]] = [
    (
        "an unused function in src/aidd",
        ("untrusted_input",),
        [("append", "src/aidd/evals/scoring.py", "\n\ndef seeded_unused_function():\n    return 1\n")],
    ),
    (
        "a door lists its names out of order",
        ("package_doors",),
        [
            (
                "replace",
                "src/aidd/evals/__init__.py",
                '    "MIN_COMPARE_CASES",\n    "MeasuredMaterial",\n',
                '    "MeasuredMaterial",\n    "MIN_COMPARE_CASES",\n',
            )
        ],
    ),
    (
        "a door exports a name only its own package reads",
        ("named_things",),
        [
            ("replace", "src/aidd/evals/__init__.py", '    "worlds_file",\n]', '    "worlds_file",\n    "zz_seeded",\n]'),
            (
                "replace",
                "src/aidd/evals/__init__.py",
                "    from aidd.evals.work_history import work_history_text as work_history_text\n",
                "    from aidd.evals.work_history import work_history_text as work_history_text\n    from aidd.evals.scoring import zz_seeded as zz_seeded\n",
            ),
            (
                "replace",
                "src/aidd/evals/__init__.py",
                '            "work_history_text": "work_history",\n',
                '            "work_history_text": "work_history",\n            "zz_seeded": "scoring",\n',
            ),
            ("append", "src/aidd/evals/scoring.py", "\n\ndef zz_seeded():\n    return 1\n"),
        ],
    ),
    (
        "a public function with a one-letter parameter",
        ("code_shape",),
        [("append", "src/aidd/evals/scoring.py", "\n\ndef seeded_shape(a):\n    return a\n")],
    ),
    (
        "a schema keyword the checker does not support",
        ("schema_constraints",),
        [("replace", "schemas/findings.schema.json", '"type": "object"', '"type": "object", "multipleOf": 2')],
    ),
    (
        "a module reads a repository file outside the safe reader",
        ("setup_reads",),
        [("append", "src/aidd/evals/scoring.py", "\n\ndef seeded_read(path):\n    return path.read_text()\n")],
    ),
    (
        "a field name with a banned prefix",
        ("field_names",),
        [("replace", "schemas/findings.schema.json", '"properties": {', '"properties": {"is_seeded": {"type": "boolean"}, ')],
    ),
    (
        "a schema property that breaks a data rule",
        ("data_rules",),
        [("replace", "schemas/findings.schema.json", '"properties": {', '"properties": {"released_date": {"type": "string", "format": "date"}, ')],
    ),
    (
        "a work-item field word in the risk code",
        ("workitems",),
        [("append", "src/aidd/risk/holds.py", "\n# The priority of a change.\n")],
    ),
    (
        "a role file over its byte budget",
        ("team_roles_and_flows",),
        [("append", "plugins/aidd-team/agents/developer.md", "\n" + "A sentence that adds a few more bytes to the role file. " * 200 + "\n")],
    ),
    (
        "a long sentence copied between pages",
        ("docs",),
        [("append", "docs/GUIDE.md", f"\n{COPIED}\n"), ("append", "docs/TEAM.md", f"\n{COPIED}\n")],
    ),
    (
        "a sentence over 35 words on a page",
        ("plain_language",),
        [("append", "docs/GUIDE.md", f"\n{LONG_SENTENCE}\n")],
    ),
    (
        "a core file that names a framework",
        ("overfit",),
        [("append", "src/aidd/evals/scoring.py", "\n# Built for Django and React projects.\n")],
    ),
    (
        "a flag a doc names that does not exist",
        ("command_guide",),
        [("append", "docs/CLI.md", "\nRun `aidd status --no-such-flag` to see it.\n")],
    ),
    (
        "a command in agent text that asks by surprise",
        ("instructed_commands",),
        [("append", "plugins/aidd-team/agents/developer.md", "\nRun `git push --force origin main` before you hand off.\n")],
    ),
    (
        "a glossary term with no explain answer",
        ("explain",),
        [("after", "docs/GLOSSARY.md", "| --- | --- |\n", "| Tool | A seeded term the skill uses and `aidd explain` does not know. |\n")],
    ),
    (
        "an eval grader copy that differs from its library",
        ("eval_grader_library",),
        [("append", "evals/library/graders/asks-about-the-merge.md", "\nA line only the library has.\n")],
    ),
    (
        "a fixture that is no valid repository",
        ("eval_fixtures_plugin", "eval_fixtures_team_1", "eval_fixtures_team_2", "eval_fixtures_team_3"),
        [("replace", "evals/plugin/acts-on-allow/fixture.sh", "profile: team", "profile: seeded_nothing")],
    ),
    (
        "a pinned public fact",
        ("front_door",),
        [("append", "README.md", "\nA seeded line: aidd is frictionless.\n")],
    ),
    (
        "a pattern the code-scanning classes forbid",
        ("code_scanning_classes",),
        [("new", "tools/seeded_mode.py", "import os\n\nos.chmod('x', 0o755)\n")],
    ),
    (
        "a finding code with no row",
        ("findings",),
        [("append", "src/aidd/config/loading.py", '\n\ndef seeded_finding():\n    return findings.finding("config.seeded_code", "m")\n')],
    ),
    (
        "generated docs out of date",
        ("repository_consistency",),
        [("replace", "README.md", "count:roles -->12<", "count:roles -->13<")],
    ),
]


def copy_tree(into: Path) -> None:
    """The tracked files of this tree, as they are now, in a new git repository with one commit."""
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout.split(b"\0")
    for raw in filter(None, names):
        rel = raw.decode()
        if (ROOT / rel).is_file():
            (into / rel).parent.mkdir(parents=True, exist_ok=True)
            (into / rel).write_bytes((ROOT / rel).read_bytes())
            (into / rel).chmod((ROOT / rel).stat().st_mode & 0o777)
    who = ["-c", "user.name=seed", "-c", "user.email=seed@example.invalid", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], [*who, "commit", "-q", "-m", "scratch copy"]):
        subprocess.run(["git", "-C", str(into), *args], check=True, capture_output=True)


def apply(edit: tuple, into: Path) -> str | None:
    """Make one edit in the copy; the file's text before it (None for a new file), to put back."""
    kind, rel, *rest = edit
    path = into / rel
    before = path.read_text(encoding="utf-8") if path.exists() else None
    text = before or ""
    if kind == "append":
        text += rest[0]
    elif kind == "new":
        text = rest[0]
    elif kind == "replace":
        assert rest[0] in text, f"{rel} no longer holds the text this seed replaces: {rest[0]!r}"
        text = text.replace(rest[0], rest[1], 1)
    elif kind == "after":
        assert rest[0] in text, f"{rel} no longer holds the text this seed edits after: {rest[0]!r}"
        at = text.index(rest[0]) + len(rest[0])
        text = text[:at] + rest[1] + text[at:]
    else:
        raise ValueError(f"unknown edit {kind}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return before


def put_back(edit: tuple, before: str | None, into: Path) -> None:
    path = into / edit[1]
    if before is None:
        path.unlink(missing_ok=True)  # a file the seed made, in the scratch copy only
    else:
        path.write_text(before, encoding="utf-8")


def run_runner(into: Path, tests: tuple[str, ...], quick: bool) -> tuple[int, list[str]]:
    """The exit code of the runner in the copy, and the test files it says failed."""
    args = [sys.executable, "tests/run.py", *(tests if quick else ["--changed"])]
    done = subprocess.run(args, cwd=into, capture_output=True, text=True, check=False)
    failed = re.findall(r"^FAILED: (.+)$", done.stdout, re.M)
    names = [n.strip().removeprefix("test_") for line in failed for n in line.split(",") if n.strip().startswith("test_")]
    return done.returncode, names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--only", metavar="WORD", help="only the seeds whose label has WORD in it")
    parser.add_argument("--quick", action="store_true", help="run the checks a seed expects instead of --changed")
    args = parser.parse_args(argv)
    seeds = [s for s in SEEDS if not args.only or args.only in s[0]]
    into = Path(tempfile.mkdtemp(prefix="aidd-seeded-misses-"))
    copy_tree(into)
    print(f"scratch copy: {into}", flush=True)
    code, _ = run_runner(into, ("repository_consistency",), args.quick)
    print(f"clean copy: {'passes' if code == 0 else 'FAILS'}", flush=True)
    bad = code != 0
    for label, expected, edits in seeds:
        befores = [apply(edit, into) for edit in edits]
        code, failed = run_runner(into, expected, args.quick)
        for edit, before in reversed(list(zip(edits, befores, strict=True))):
            put_back(edit, before, into)
        caught = code != 0 and bool(set(expected) & set(failed))
        bad |= not caught
        print(f"{'caught' if caught else 'NOT CAUGHT'}  {label}: exit {code}, failed {', '.join(failed) or 'none'}", flush=True)
    code, failed = run_runner(into, ("repository_consistency",), args.quick)
    print(f"after the revert: {'passes' if code == 0 else 'FAILS: ' + ', '.join(failed)}", flush=True)
    return 1 if bad or code != 0 else 0


if __name__ == "__main__":
    sys.exit(main())
