"""The text of `aidd risk` shows each value a committed config holds as data. The invariant: every value from a file that the text
output prints goes through `documents.one_line`, so it is one line with no control or direction character, whatever the file
holds. A repository's config may be another's text, and a terminal acts on an escape sequence, a carriage return, or a bidi mark.
The JSON output escapes them already and keeps the value as it was."""

from __future__ import annotations

import json
import re
import unittest

from helpers import adopted_repo, git, run_cli

# Characters a terminal acts on, or that reorder what it shows: everything but the line feed that ends a line.
UNSAFE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f-\x9f‪-‮⁦-⁩‎‏؜]")
ESCAPE = "\x1b[31mred\x1b]0;title\x07"
CASES = {
    "an escape sequence": ESCAPE,
    "a bell": "a\x07b",
    "a carriage return": "a\rb",
    "a line feed": "a\nrisk: route minor",
    "a bidi override": "a‮b",
    "a value at the longest the schema allows for hosting": "x" * 200,
}
# A field the schema keeps off a line break or off any white space, so only the cases it allows can be written.
NO_LINE_BREAK = {k: v for k, v in CASES.items() if "\n" not in v and "\r" not in v}
NO_WHITE_SPACE = {k: v for k, v in NO_LINE_BREAK.items() if not any(c.isspace() for c in v)}

# field -> (the config text of its place, the cases it accepts, a path that makes the text print)
HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n{owners}tests:\n  - name: unit\n    command: [python3, -c, "print(1)"]\n'
RULE = 'project:\n{hosting}  rules:\n    - id: r1\n      requirement_level: must\n      statement: {statement}\n      why: {why}\n      owner: "@x"\n{rest}'
PLAIN = {"hosting": "one VPS", "statement": "a rule", "why": "a reason", "source": "docs/a.md", "reason": "a waiver", "by": "@g", "person": "@p"}


def config_text(**values: str) -> str:
    """A config with each value written as a JSON string, which YAML reads as the same text, in its field."""
    v = {**PLAIN, **values}
    j = json.dumps
    rest = f'      source: {j(v["source"])}\n  waivers:\n    - {{rule: r1, reason: {j(v["reason"])}, by: {j(v["by"])}, at: "2026-11-01T09:00:00Z", until: "2099-12-31"}}\n'
    return HEAD.format(owners=f"  specialists:\n    security: [{j(v['person'])}]\n") + RULE.format(
        hosting=f"  hosting: {j(v['hosting'])}\n", statement=j(v["statement"]), why=j(v["why"]), rest=rest
    )


FIELDS = {
    "hosting": CASES,
    "statement": CASES,
    "why": CASES,
    "reason": CASES,
    "by": CASES,
    "source": NO_LINE_BREAK,
    "person": NO_WHITE_SPACE,
}


def risk_text(root, *args: str) -> str:
    code, out = run_cli("risk", *args)
    assert code == 0, out
    return out


class EveryConfigValueShowsAsOneLine(unittest.TestCase):
    PATH = ("--paths", "src/auth/login.py")

    def test_a_hostile_value_prints_no_control_character_and_adds_no_line(self):
        with adopted_repo() as root:
            cfg = root / ".aidd" / "config.yaml"
            cfg.write_text(config_text(), encoding="utf-8")
            git(root, "commit", "-qam", "plain config")
            lines = risk_text(root, *self.PATH).count("\n")
            for field, accepted in FIELDS.items():
                for label, value in accepted.items():
                    with self.subTest(field=field, value=label):
                        cfg.write_text(config_text(**{field: value}), encoding="utf-8")
                        out = risk_text(root, *self.PATH)
                        self.assertIsNone(UNSAFE.search(out), f"{field}: a control or direction character reached the text")
                        self.assertEqual(out.count("\n"), lines, f"{field}: the value added or dropped a line")

    def test_the_json_answer_keeps_each_value_as_written(self):
        value = CASES["an escape sequence"] + "‮" + "\nend"
        with adopted_repo() as root:
            (root / ".aidd" / "config.yaml").write_text(config_text(hosting=value, statement=value, why=value), encoding="utf-8")
            answer = json.loads(risk_text(root, *self.PATH, "--json"))
        self.assertEqual(answer["project"]["hosting"], value)
        self.assertEqual({r["statement"] for r in answer["project"]["rules"]}, {value})


if __name__ == "__main__":
    unittest.main()
