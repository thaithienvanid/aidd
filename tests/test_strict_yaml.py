"""The strict YAML subset aidd reads and writes (aidd.kernel.strict_yaml).

The subset must mean one thing in every YAML reader, so a person's editor, a platform's renderer, and the gate never read
the same file two ways. These tests pin what it accepts and refuses, and that writing then reading gives the same data.
The differential tests check every document aidd accepts against PyYAML, a YAML 1.1 reader. The lint job in CI installs
PyYAML hash-pinned (.github/requirements/lint.txt) and sets REQUIRE_PYYAML=1, so they cannot skip there.
"""

from __future__ import annotations

import json
import os
import random
import unittest

from helpers import ROOT, repo_files

from aidd.kernel import documents, strict_yaml

try:
    import yaml
except ImportError:  # pragma: no cover - exercised where PyYAML is not installed
    yaml = None

load, dump = strict_yaml.load, strict_yaml.dump


class AcceptsTests(unittest.TestCase):
    def test_block_mappings_sequences_and_flow_collections(self):
        text = (
            "id: SPEC-1\n"
            "title: Fix the login bug  # a comment\n"
            "route: normal\n"
            "open_questions: []\n"
            "risk:\n"
            "  dimensions: [security, data]\n"
            "  reversible: true\n"
            "tasks:\n"
            "  - id: SPEC-1-T1\n"
            '    scope: ["src/auth/**"]\n'
            "    depends_on: []\n"
            "  - id: SPEC-1-T2\n"
            "    scope:\n"
            "      - src/ui/\n"
            "tests:\n"
            "  commands:\n"
            "  - name: acceptance\n"
            "    command: [pytest, -q]\n"
            "    covers: [A1, A2]\n"
        )
        self.assertEqual(
            load(text),
            {
                "id": "SPEC-1",
                "title": "Fix the login bug",
                "route": "normal",
                "open_questions": [],
                "risk": {"dimensions": ["security", "data"], "reversible": True},
                "tasks": [
                    {"id": "SPEC-1-T1", "scope": ["src/auth/**"], "depends_on": []},
                    {"id": "SPEC-1-T2", "scope": ["src/ui/"]},
                ],
                "tests": {"commands": [{"name": "acceptance", "command": ["pytest", "-q"], "covers": ["A1", "A2"]}]},
            },
        )

    def test_scalars(self):
        self.assertEqual(
            load("a: \"x \\\"y\\\" \\u00e9\\n\"\nb: 'it''s'\nc: 42\nd: -3\ne: 1.5\nf: false\ng: agent:developer\nh: https://x.y/z\n"),
            {"a": 'x "y" é\n', "b": "it's", "c": 42, "d": -3, "e": 1.5, "f": False, "g": "agent:developer", "h": "https://x.y/z"},
        )

    def test_a_flow_collection_over_several_lines_and_a_literal_block(self):
        self.assertEqual(load("a: [x,\n  y2, # one\n  z]\nb: {k: 1,\n  m: [2]}\n"), {"a": ["x", "y2", "z"], "b": {"k": 1, "m": [2]}})
        self.assertEqual(load("a: |\n  one\n\n  two\nb: |-\n  three\n"), {"a": "one\n\ntwo\n", "b": "three"})

    def test_a_key_that_is_no_plain_name_is_double_quoted(self):
        self.assertEqual(
            load('rule_exclusions:\n  "baseline:auth": ["web/**"]\n"on": 1\nm: {"a b": 2}\nl:\n  - "k:1": v\n'),
            {"rule_exclusions": {"baseline:auth": ["web/**"]}, "on": 1, "m": {"a b": 2}, "l": [{"k:1": "v"}]},
        )
        self.assertEqual(dump({"x": {"baseline:auth": 1, "on": 2, "plain": 3}}), 'x:\n  "baseline:auth": 1\n  "on": 2\n  plain: 3\n')

    def test_empty_and_comment_only_text_is_an_empty_mapping(self):
        self.assertEqual(load(""), {})
        self.assertEqual(load("# nothing yet\n\n"), {})


class RefusesTests(unittest.TestCase):
    def refused(self, text: str, line: int, words: str) -> None:
        with self.assertRaises(strict_yaml.YamlError) as cm:
            load(text)
        self.assertEqual(cm.exception.line, line, str(cm.exception))
        self.assertIn(words, str(cm.exception))

    def test_a_value_another_reader_could_read_as_something_else(self):
        for value in ("yes", "No", "on", "OFF", "y", "null", "~", "1.0.0", "2026-10-07", "0x1f", "1e3", "01", "+1", ".5", ".inf", "12:30"):
            with self.subTest(value=value):
                self.refused(f"a: {value}\n", 1, "double quotes")

    def test_a_key_another_reader_could_read_as_a_boolean(self):
        self.refused("on: 1\n", 1, "cannot be a key")
        self.refused('a: {yes: "x"}\n', 1, "cannot be a key")

    def test_constructs_outside_the_subset(self):
        for text in ("a: &x 1\n", "a: *x\n", "a: !!str 1\n", "a: >\n  x\n", "? a\n", "a: @me\n", "a: `x`\n", "a: %x\n"):
            with self.subTest(text=text):
                self.assertRaises(strict_yaml.YamlError, load, text)
        self.refused("a: 1\n---\nb: 2\n", 2, "")
        self.refused("a:\n", 1, "has no value")
        self.refused("a: 1\na: 2\n", 2, "twice")
        self.refused("a: {b: 1, b: 2}\n", 1, "twice")

    def test_indentation(self):
        self.refused("a:\n\tb: 1\n", 2, "tab")
        self.refused("a: 1\n  b: 2\n", 2, "indented more")
        self.refused("a:\n  b: 1\n c: 2\n", 3, "indented more")
        self.refused(" a: 1\n", 1, "left margin")

    def test_characters_a_reader_breaks_a_line_at_or_refuses(self):
        for ch in ("\u2028", "\u2029", "\x85", "\x7f", "\ufeff"):
            with self.subTest(ch=hex(ord(ch))):
                self.refused(f'a: 1\nb: "x{ch}y"\n', 2, f"U+{ord(ch):04X}")
        self.refused("a: 1\r\n", 1, "carriage return")

    def test_unclosed_quotes_and_brackets(self):
        self.refused('a: "x\n', 1, "close the quote")
        self.refused("a: [x, y\nb: 1\n", 1, "not closed")
        self.refused('a: "\\x41"\n', 1, "not an escape")

    def test_nesting_has_a_limit(self):
        deep = "a: " + "[" * (strict_yaml.MAX_DEPTH + 2) + "]" * (strict_yaml.MAX_DEPTH + 2) + "\n"
        self.refused(deep, 1, "nest")


def _random_value(rnd: random.Random, depth: int = 0):
    chars = "abcXYZ019 _-./:@#'\",[]{}|>&*!%?~`\\\n\t\u00e9\u2028\x85\x7f\u200b\ufeff日"
    r = rnd.random()
    if depth > 3 or r < 0.5:
        return rnd.choice(
            [
                "".join(rnd.choice(chars) for _ in range(rnd.randint(0, 12))),
                rnd.randint(-5, 99),
                rnd.choice([True, False]),
                rnd.choice([0.5, 1.25, -3.0]),
                rnd.choice(["yes", "no", "on", "1.0.0", "2026-10-07", "null", "~", "true", "-a", "- a", "it's", "a 'b'"]),
            ]
        )
    if r < 0.75:
        return [_random_value(rnd, depth + 1) for _ in range(rnd.randint(0, 4))]
    return {rnd.choice(["a", "b", "c_d", "e-f", "g.h", "k1", "on", "a:b", "x y"]): _random_value(rnd, depth + 1) for _ in range(rnd.randint(0, 4))}


class RoundTripTests(unittest.TestCase):
    def test_what_aidd_writes_it_reads_back_unchanged(self):
        rnd = random.Random(20261012)
        for _ in range(3000):
            data = {rnd.choice("abcde"): _random_value(rnd) for _ in range(rnd.randint(1, 4))}
            text = dump(data)
            self.assertEqual(load(text), data, text)

    def test_it_writes_plain_text_where_that_reads_back_the_same(self):
        self.assertEqual(
            dump({"id": "SPEC-1", "on_date": "2026-10-07", "flag": "yes", "owner": "@me", "count": 3, "tags": ["a", "b c"]}),
            'id: SPEC-1\non_date: "2026-10-07"\nflag: "yes"\nowner: "@me"\ncount: 3\ntags: [a, b c]\n',
        )


@unittest.skipIf(yaml is None and os.environ.get("REQUIRE_PYYAML") != "1", "PyYAML is not installed")
class AnotherReaderAgreesTests(unittest.TestCase):
    """Every document aidd accepts, PyYAML reads to the same data."""

    def agrees(self, text: str) -> None:
        try:
            ours = load(text)
        except strict_yaml.YamlError:
            return
        self.assertEqual(json.dumps(yaml.safe_load(text) or {}, sort_keys=True, default=repr), json.dumps(ours, sort_keys=True), text)

    def test_what_aidd_writes(self):
        rnd = random.Random(7)
        for _ in range(2000):
            self.agrees(dump({rnd.choice("abcde"): _random_value(rnd) for _ in range(rnd.randint(1, 4))}))

    def test_every_file_aidd_ships(self):
        """The front matter of every Markdown file, and every YAML file, read the same in PyYAML when aidd accepts it."""
        checked = 0
        for rel in repo_files():
            path = ROOT / rel
            if rel.endswith(".md"):
                m = documents.FRONT_MATTER.match(path.read_text(encoding="utf-8"))
                text = m.group(1) if m else None
            elif rel.endswith((".yaml", ".yml")):
                text = path.read_text(encoding="utf-8")
            else:
                text = None
            if text is None:
                continue
            try:
                ours = load(text)
            except strict_yaml.YamlError:
                continue  # outside the subset, such as another tool's front matter: aidd never reads it as its own
            self.assertEqual(json.dumps(yaml.safe_load(text) or {}, sort_keys=True, default=repr), json.dumps(ours, sort_keys=True), rel)
            checked += 1
        self.assertGreater(checked, 300)

    def test_hand_written_text(self):
        atoms = [
            "a", "x-y", "yes", "on", "true", "True", "1", "01", "1.0", "-1", "1e3", "2026-10-07", "1.0.0", '"q"', "'s'",
            '"a\\nb"', "'it''s'", "@me", "a: b", "a #c", "a#b", "https://x.y", "agent:dev", "é", "[a, b]", "{a: 1}", "[]",
            "{}", "a b", "it's", "x 'y'", "c?d", "a,b", "-x", "-1x", "/p/q", "-q", "--fix", "-0x1f", "-.5", "-e x", "-", "- a", ".github/x", ".inf", "..", "./x", ".1x", "why, in", "C#", "x[1]", "see [1", "x # y", "100% sure", "R&D", "fix `x`",
        ]  # fmt: skip
        rnd = random.Random(11)
        for _ in range(4000):
            lines = []
            for _ in range(rnd.randint(1, 4)):
                k = rnd.choice(["a", "b", "key", "x.y", "a-b", "_c", '"on"', '"a:b"', '"x y"'])
                shape = rnd.random()
                if shape < 0.5:
                    lines.append(f"{k}: {rnd.choice(atoms)}{rnd.choice(['', ' # c'])}")
                elif shape < 0.75:
                    lines += [f"{k}:"] + [f"{rnd.choice(['', '  '])}- {rnd.choice(atoms)}" for _ in range(rnd.randint(1, 3))]
                else:
                    lines += [f"{k}:", f"  m: {rnd.choice(atoms)}", f"  n: [{', '.join(rnd.choice(atoms) for _ in range(2))}]"]
            self.agrees("\n".join(lines) + "\n")


if __name__ == "__main__":
    unittest.main()
