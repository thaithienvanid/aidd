"""The plugin eval suites (`claude plugin eval`): every case is well formed before anyone spends a model run on it.

A case is a folder with `prompt.md` (YAML front matter, then the prompt) and `graders/*.md` (front matter naming the
grader `type`). Claude Code parses the front matter as YAML; these tests hold it to the strict block subset the
cases use, so a stray `: ` or `#` in a value cannot turn into a different value there.
"""

import atexit
import os
import functools
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.evals import trigger_cases

TEAM_SUITE = ROOT / "evals" / "team"
SUITES = (ROOT / "evals" / "plugin", TEAM_SUITE)
GRADER_TYPES = {"file_exists", "llm", "regex", "tool_used", "tool_order"}
_KEY = re.compile(r"^([a-z_]+):(?: (.*))?$")
_ITEM = re.compile(r"^  - (.+)$")
_SUB = re.compile(r"^  ([a-z_]+): (.+)$")
_PLAIN_INDICATORS = tuple("-?:,[]{}#&*!|>'\"%@`")


def _scalar(raw: str, where: str) -> str | int | bool:
    if raw.startswith("'"):
        if not raw.endswith("'") or len(raw) < 2 or re.search(r"(?<!')'(?!')", raw[1:-1]):
            raise ValueError(f"{where}: unbalanced single-quoted scalar {raw!r}")
        return raw[1:-1].replace("''", "'")
    if raw.startswith('"'):
        if not raw.endswith('"') or len(raw) < 2:
            raise ValueError(f"{where}: unbalanced double-quoted scalar {raw!r}")
        return raw[1:-1]
    if ": " in raw or " #" in raw or raw.startswith(_PLAIN_INDICATORS):
        raise ValueError(f"{where}: plain scalar {raw!r} would not parse as the string it looks like; quote it")
    if raw in ("true", "false"):  # YAML reads these as booleans, so `exists: false` must not stay a truthy string
        return raw == "true"
    return int(raw) if raw.isdigit() else raw


def _block(lines: list[str], path, first: int) -> dict:
    """The strict block subset: `key: scalar`, or `key:` then `  - item` lines (a list) or `  sub: scalar` lines (a
    mapping, as a `tool_order` grader's `before` and `after` or a case.yaml's `context`)."""
    data: dict = {}
    current = None
    for n, line in enumerate(lines, first):
        where = f"{path}:{n}"
        if current is not None and (m := _ITEM.match(line)):
            data[current] = [] if data[current] is None else data[current]
            if not isinstance(data[current], list):
                raise ValueError(f"{where}: {current} mixes a mapping and a list")
            data[current].append(_scalar(m.group(1), where))
        elif current is not None and (m := _SUB.match(line)):
            data[current] = {} if data[current] is None else data[current]
            if not isinstance(data[current], dict) or m.group(1) in data[current]:
                raise ValueError(f"{where}: {current}.{m.group(1)} is repeated or mixes a list and a mapping")
            data[current][m.group(1)] = _scalar(m.group(2), where)
        elif m := _KEY.match(line):
            key, value = m.groups()
            if key in data:
                raise ValueError(f"{where}: {key} twice")
            if value is None:
                data[key], current = None, key
            else:
                data[key], current = _scalar(value, where), None
        else:
            raise ValueError(f"{where}: not a block mapping line: {line!r}")
    return {k: [] if v is None else v for k, v in data.items()}


def front_matter(path) -> tuple[dict, str]:
    """(front matter, body) of a case file, in the strict block subset (`_block`)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[3:]:
        raise ValueError(f"{path}: no front matter between --- lines")
    head, body = text[4:].split("\n---\n", 1)
    return _block(head.splitlines(), path, 2), body


def case_yaml(path) -> dict:
    """A case's case.yaml, in the same strict subset."""
    return _block(path.read_text(encoding="utf-8").splitlines(), path, 1)


@functools.cache
def written_triggers() -> Path:
    """The team suite's trigger cases, written once into a temporary folder from triggers.json, as
    `python3 -m aidd.evals.trigger_cases` writes them into evals/team/ before a run. No commit holds them."""
    folder = Path(tempfile.mkdtemp(prefix="aidd-trigger-cases-"))
    atexit.register(shutil.rmtree, folder, True)
    trigger_cases.write_cases(folder, trigger_cases.load_triggers(ROOT))
    return folder


def suite_cases(suite: Path) -> list[Path]:
    """A suite's case folders, sorted by name. The team suite's trigger cases come from `written_triggers`, never from the
    folders a run left in evals/team/, so a checkout with or without them tests the same cases. `results/` is what
    `claude plugin eval` writes after a run (ignored), not a case."""
    team = suite == TEAM_SUITE
    own = [p for p in suite.iterdir() if p.is_dir() and p.name != "results" and not (team and p.name.startswith(trigger_cases.PREFIXES))]
    written = [p for p in written_triggers().iterdir() if p.is_dir()] if team else []
    return sorted(own + written, key=lambda p: p.name)


def run_folder(case: Path) -> Path:
    """Where a case runs: its own folder, or evals/team/<case> for a written trigger case. Its plugins load relative to it."""
    return TEAM_SUITE / case.name if case.is_relative_to(written_triggers()) else case


def cases():
    return [p for suite in SUITES for p in suite_cases(suite)]


class PluginEvalCaseTests(unittest.TestCase):
    def test_the_suites_have_cases(self):
        for suite in SUITES:
            self.assertTrue(suite_cases(suite), suite)

    def test_every_prompt_has_strict_front_matter_and_a_prompt(self):
        for case in cases():
            with self.subTest(case=case.name):
                data, body = front_matter(case / "prompt.md")
                self.assertIsInstance(data.get("description"), str)
                self.assertTrue(body.strip(), "the prompt is empty")
                self.assertIsInstance(data.get("max_turns"), int)
                for tool in data.get("allowed_tools", []):
                    self.assertRegex(tool, r"^[A-Z]\w+$")
                for plugin in data.get("plugins", []):  # plugins load relative to the case folder
                    self.assertTrue(Path(os.path.normpath(run_folder(case) / plugin / ".claude-plugin" / "plugin.json")).is_file(), plugin)

    def test_every_case_has_graders_with_a_known_type(self):
        for case in cases():
            with self.subTest(case=case.name):
                graders = sorted((case / "graders").glob("*.md"))
                self.assertTrue(graders, "a case with no grader passes whatever the agent does")
                for g in graders:
                    data, body = front_matter(g)
                    self.assertIn(data.get("type"), GRADER_TYPES, g.name)
                    if data["type"] == "llm":
                        self.assertIn("PASS if", body, g.name)
                        self.assertIn("FAIL if", body, g.name)
                    elif data["type"] == "regex":
                        re.compile(data["pattern"])
                        if isinstance(data.get("target"), dict):  # the contents of one workspace file after the run
                            self.assertEqual(set(data["target"]), {"source", "path"}, g.name)
                            self.assertEqual(data["target"]["source"], "file", g.name)
                    elif data["type"] == "file_exists":
                        self.assertIsInstance(data.get("path"), str, g.name)
                    elif data["type"] == "tool_order":
                        # Each side is a tool name, or a mapping with `tool` and an optional `input_match`.
                        for side in ("before", "after"):
                            ref = data[side]
                            ref = ref if isinstance(ref, dict) else {"tool": ref}
                            self.assertRegex(str(ref.get("tool")), r"^[A-Z]\w+$", (g.name, side))
                            self.assertLessEqual(set(ref), {"tool", "input_match"}, (g.name, side))
                            if "input_match" in ref:
                                re.compile(ref["input_match"])
                    else:
                        self.assertRegex(str(data.get("tool")), r"^[A-Z]\w+$", g.name)
                        if "input_match" in data:
                            re.compile(data["input_match"])
                        if "min" in data or "max" in data:
                            self.assertLessEqual(data.get("min", 0), data.get("max", data.get("min", 0)), g.name)

    def test_a_case_yaml_names_its_case_and_its_scaffold(self):
        """`case.yaml` needs `schema_version: "1.1"` and `name`; its `scaffold_script` runs only under `--scaffold`."""
        found = 0
        for case in cases():
            path = case / "case.yaml"
            if not path.is_file():
                continue
            found += 1
            with self.subTest(case=case.name):
                data = case_yaml(path)
                self.assertEqual(data["schema_version"], "1.1")
                self.assertEqual(data["name"], case.name)
                script = data["context"]["scaffold_script"]
                self.assertTrue((case / script).is_file(), script)
                self.assertTrue((case / script).read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\nset -euo pipefail\n"), script)
        self.assertGreater(found, 0, "no case seeds its workspace")

    def test_the_strict_parser_rejects_what_yaml_would_read_differently(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "prompt.md"
            for bad in (
                "description: a: b",
                "description: fine # not a comment?",
                "description: 'unbalanced",
                "  - orphan",
                "tags:\n\t- x",
                "before:\n  tool: Bash\n  - x",
                "before:\n  tool: Bash\n  tool: Edit",
            ):
                p.write_text(f"---\n{bad}\n---\n\nbody\n", encoding="utf-8")
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    front_matter(p)
            p.write_text("---\ndescription: 'It''s fine: quoted'\ntags:\n  - a\n---\n\nbody\n", encoding="utf-8")
            self.assertEqual(front_matter(p)[0], {"description": "It's fine: quoted", "tags": ["a"]})
            p.write_text("---\ntype: tool_order\nbefore:\n  tool: Bash\n  input_match: 'x'\nafter: Edit\n---\n", encoding="utf-8")
            self.assertEqual(front_matter(p)[0], {"type": "tool_order", "before": {"tool": "Bash", "input_match": "x"}, "after": "Edit"})


if __name__ == "__main__":
    unittest.main()
