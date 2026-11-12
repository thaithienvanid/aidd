"""Every rule of the plain-language skill is held by a check that fails when the rule breaks, or shown by a before-and-after
row in `references/examples.md`, and the skill passes the rules it sets.

LEDGER names the proof of each rule, by the words the rule starts with. A new rule with no entry fails, and so does an entry
that points at an example or a test that is gone. The helpers are plain functions, so each test also runs on a sample that
breaks it, and on a second sample that does not.
"""

from __future__ import annotations

import importlib
import re
import unittest
from collections.abc import Callable

from helpers import ROOT
from test_plain_language import (
    MAX_WORDS,
    SHORT_SHARE,
    SHORT_WORDS,
    TABLE_RULE,
    VOICE_MIN_SENTENCES,
    VOICE_SHARE,
    page_findings,
    sentences,
    voice_shares,
    without_code,
)
from test_plain_language_report import INSTRUCTION_WORDS, PARAGRAPH_SENTENCES

from aidd.kernel import documents
from aidd.knowledge import team_registry

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"
FOLDER = SKILLS / "plain-language"
SKILL = FOLDER / "SKILL.md"
EXAMPLES = FOLDER / "references" / "examples.md"
# Roles that write text a person reads may load the skill: each has one of these practices, whose output is such text.
TEXT_PRACTICES = ("accessible-ui", "cli-design", "technical-writing")
# The limits table of the skill: its first cell, then who sets the limit.
ASD = "ASD-STE100"
AIDD = "aidd"
LIMIT_SETTERS = {
    "Words in an instruction": ASD,
    "Words in a description": ASD,
    "Sentences past their limit": AIDD,
    "Words in any sentence": AIDD,
    "Instructions in a sentence": ASD,
    "Sentences in a paragraph": ASD,
}

# The proof of each rule: (the words the rule starts with, the Rule cells of the example rows that show it, the tests that
# check it as "module.Class.method"). Each rule has at least one of the two. In the skill's order.
LEVELS = "test_plain_language_practice.LevelTests.test_the_three_levels_and_their_readers"
PAGES = "test_plain_language.StyleTests.test_every_page_meets_the_rule"
VOICE = "test_plain_language.VoiceTests.test_each_page_reads_in_a_natural_voice"
LINKS = "test_plain_language_proof.NameTests.test_every_name_and_link_of_the_skill_resolves"
LEDGER: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("What will the reader do next?", ("The next action",), ()),
    ("What is the answer?", ("The answer first", "A condition before the action"), ()),
    ("What has the reader not seen?", ("No label the reader never saw",), ()),
    ("`instruction` |", (), (LEVELS,)),
    ("`plain` |", ("The reader's words",), (LEVELS,)),
    ("`controlled` |", (), (LEVELS,)),
    ("Words in an instruction |", ("Words in an instruction",), ()),
    ("Words in a description |", (), (PAGES,)),
    ("Sentences past their limit |", (), (PAGES,)),
    ("Words in any sentence |", (), (PAGES,)),
    ("Instructions in a sentence |", ("One instruction in each sentence",), ()),
    ("Sentences in a paragraph |", ("A paragraph on one topic",), ()),
    ("Use the active voice", ("The active voice, with who acts",), ()),
    ("Use the project's GLOSSARY.md terms", ("One term for one thing", "A term spelled out at first use"), ()),
    ("Give the fact, then its reason", ("The reason with the rule", "Clauses joined by a word"), (VOICE,)),
    ("Name the specific thing", ("The specific thing",), ()),
    ("Say once what is unknown", ("What is unknown, said once",), ()),
    ("Never split a sentence", ("A split that keeps its qualifier",), ()),
    ("Never paraphrase code", ("An exact error, copied",), ()),
    ("Write a security or irreversible-step warning", ("A warning before an irreversible step, in full sentences",), ()),
    ("At `plain`, apply", ("The reader's words",), ()),
    ("is steps, an order, or a priority", ("One instruction in each sentence",), ()),
    ("is items with no order", ("Items with no order, in one stated order",), ()),
    ("compares things", ("A table when each row answers the same questions",), ()),
    ("gives a reason, a condition", ("Prose when the text gives a reason",), ()),
    ("holds a number", ("A number with its unit",), ()),
    ("is a message or an error", ("An error says what happened and the next step",), ()),
    ("is words on a screen", (), (LINKS,)),
    ("is read by an agent", ("The exact command and the reason", "Closed values", "A case and its answer"), ()),
    ("is read by a program", ("Data a program reads",), ()),
    ("Before a rewrite or a cut", ("A cut keeps every fact",), ()),
    ("After, check that each one kept", ("A rewrite keeps a commitment",), ()),
)


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def subsection(text: str, heading: str) -> str:
    """The body of the `### ` subsection of the Implement section whose heading starts with `heading`."""
    found = re.search(rf"^### {re.escape(heading)}.*?\n(.*?)(?=^### |\Z)", documents.raw_section(text, "Implement"), re.S | re.M)
    return found.group(1) if found else ""


def tables(text: str) -> list[list[list[str]]]:
    """Each Markdown table outside code and comments, as rows of cells, its rule row dropped. The header is the first row."""
    out: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in [*without_code(text).splitlines(), ""]:
        s = line.strip()
        if s.startswith("|"):
            if not TABLE_RULE.fullmatch(s):
                current.append([c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))])
        elif current:
            out.append(current)
            current = []
    return out


def rule_items(implement: str) -> list[str]:
    """The rules of the Implement section: each list item without its marker, and each data row of a table as its cells
    joined by " | ", the first cell leading."""
    items = []
    for line in without_code(implement).splitlines():
        if m := re.match(r"^\s*(?:[-*]|\d+\.)\s+(.*)", line):
            items.append(m.group(1).strip())
    for table in tables(implement):
        items += [" | ".join(row) + " |" for row in table[1:]]
    return items


def number(cell: str) -> int:
    """The first whole number in a table cell."""
    return int(re.search(r"\d+", cell).group(0))


def limit_problems(rows: dict[str, list[str]]) -> list[str]:
    """How the skill's limits table differs from the measure: each number, and who sets each limit."""
    problems = []
    expected = {
        "Words in an instruction": INSTRUCTION_WORDS,
        "Words in a description": SHORT_WORDS,
        "Sentences past their limit": round((1 - SHORT_SHARE) * 100),
        "Words in any sentence": MAX_WORDS,
        "Sentences in a paragraph": PARAGRAPH_SENTENCES,
    }
    for name, setter in LIMIT_SETTERS.items():
        row = rows.get(name)
        if row is None:
            problems.append(f"no row for {name!r}")
            continue
        if name in expected and number(row[1]) != expected[name]:
            problems.append(f"{name!r} says {number(row[1])}, and the measure holds {expected[name]}")
        if row[2] != setter:
            problems.append(f"{name!r} is set by {row[2]!r}, not {setter!r}")
    return problems


def name_problems(text: str, folder, exists: Callable[[object], bool]) -> list[str]:
    """Each `aidd-team:<skill>` the text names that is no skill, and each relative link that leads nowhere."""
    problems = [f"no skill {n!r}" for n in re.findall(r"`aidd-team:([a-z0-9-]+)`", text) if not exists(SKILLS / n / "SKILL.md")]
    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", text):
        if not target.startswith(("http:", "https:", "mailto:")) and not exists(folder / target):
            problems.append(f"no file {target!r}")
    return problems


def example_rows(text: str) -> list[dict[str, str]]:
    """Each row of each table whose header starts with Rule, Before, and After, by its header."""
    out = []
    for table in tables(text):
        head = table[0]
        if head[:2] == ["Rule", "Before"] and head[-1] == "After":
            out += [dict(zip(head, (row + [""] * len(head))[: len(head)], strict=True)) for row in table[1:]]
    return out


def example_problems(text: str) -> list[str]:
    """Why the examples are not each a pair that shows a rule: a blank cell, a Before and an After that are the same, a rule
    shown twice, or After text that breaks the measure the skill sets."""
    rows = example_rows(text)
    problems = []
    seen: set[str] = set()
    for row in rows:
        rule = row["Rule"]
        if not all(row.values()):
            problems.append(f"{rule!r} has a blank cell")
        if row["Before"] == row["After"]:
            problems.append(f"{rule!r} has the same Before and After")
        if rule in seen:
            problems.append(f"{rule!r} is shown twice")
        seen.add(rule)
        problems += [f"{rule!r}: split each After sentence over {MAX_WORDS} words" for n, _ in sentences(row["After"]) if n > MAX_WORDS]
    after = "\n\n".join(row["After"] for row in rows)
    problems += [f"After text: {f}" for f in page_findings(after) if f != "the measure found no prose"]
    if len(sentences(after)) >= VOICE_MIN_SENTENCES:
        colons, parens = voice_shares(after)
        problems += [f"After text: {share:.0%} of sentences join clauses with a colon or hold parentheses" for share in (colons, parens) if share > VOICE_SHARE]
    return problems


def ledger_problems(items: list[str], ledger, labels: set[str], resolves: Callable[[str], bool]) -> list[str]:
    """Where a rule has no proof, an entry matches no rule or two, an example row is gone, or a test is gone."""
    problems = []
    for prefix, examples, checks in ledger:
        hits = [i for i in items if i.startswith(prefix)]
        if len(hits) != 1:
            problems.append(f"{prefix!r} starts {len(hits)} rules, not one")
        if not examples and not checks:
            problems.append(f"{prefix!r} has no proof")
        problems += [f"{prefix!r}: no example row {e!r}" for e in examples if e not in labels]
        problems += [f"{prefix!r}: no test {c}" for c in checks if not resolves(c)]
    problems += [f"no proof for the rule {i[:50]!r}" for i in items if not any(i.startswith(p) for p, _, _ in ledger)]
    return problems


def resolves(name: str) -> bool:
    """Whether "module.Class.method" names a test that exists."""
    module, cls, method = name.split(".")
    try:
        return callable(getattr(getattr(importlib.import_module(module), cls), method))
    except (ImportError, AttributeError):
        return False


LIMITS_TABLE = {
    "Words in an instruction": ["Words in an instruction", "20 or fewer", ASD, "review"],
    "Words in a description": ["Words in a description", "25 or fewer", ASD, "review"],
    "Sentences past their limit": ["Sentences past their limit", "10% at most", AIDD, "review"],
    "Words in any sentence": ["Words in any sentence", "35 at most", AIDD, "Vale"],
    "Instructions in a sentence": ["Instructions in a sentence", "one", ASD, "review"],
    "Sentences in a paragraph": ["Sentences in a paragraph", "6 at most", ASD, "review"],
}


class LimitsTests(unittest.TestCase):
    def test_the_limits_table_states_the_measure(self):
        (table,) = tables(subsection(read(SKILL), "3."))
        self.assertEqual(limit_problems({row[0]: row for row in table[1:]}), [])

    def test_a_wrong_number_or_owner_is_found(self):
        self.assertEqual(limit_problems(LIMITS_TABLE), [])
        wrong = {
            "a number off by one": ("Words in any sentence", ["Words in any sentence", "36 at most", AIDD, "Vale"]),
            "a share off": ("Sentences past their limit", ["Sentences past their limit", "20% at most", AIDD, "review"]),
            "a limit credited to the standard": ("Words in any sentence", ["Words in any sentence", "35 at most", ASD, "Vale"]),
            "a limit credited to aidd": ("Words in an instruction", ["Words in an instruction", "20 or fewer", AIDD, "review"]),
        }
        for name, (key, row) in wrong.items():
            with self.subTest(name):
                self.assertEqual(len(limit_problems({**LIMITS_TABLE, key: row})), 1)
        self.assertEqual(len(limit_problems({k: v for k, v in LIMITS_TABLE.items() if k != "Words in any sentence"})), 1)

    def test_the_vale_row_holds_the_measures_numbers(self):
        row = next(r for r in documents.raw_section(read(SKILL), "Test commands").splitlines() if r.startswith("| Sentence length"))
        found = re.search(r"`max:` (\d+) for `instruction` and `plain`, (\d+) for `controlled`", row)
        self.assertIsNotNone(found, row)
        self.assertEqual((int(found.group(1)), int(found.group(2))), (MAX_WORDS, SHORT_WORDS))


class NameTests(unittest.TestCase):
    def test_every_name_and_link_of_the_skill_resolves(self):
        for path in (SKILL, *sorted((FOLDER / "references").glob("*.md"))):
            with self.subTest(page=path.name):
                self.assertEqual(name_problems(read(path), path.parent, lambda p: p.exists()), [])

    def test_a_missing_skill_or_file_is_found(self):
        text = "See `aidd-team:naming` and `aidd-team:no-such-skill`, [one](a.md), [two](b.md#x), and [three](https://example.com/c)."
        found = name_problems(text, FOLDER, lambda p: p.name in ("SKILL.md", "a.md") and "no-such-skill" not in str(p))
        self.assertEqual(found, ["no skill 'no-such-skill'", "no file 'b.md'"])
        self.assertEqual(name_problems("No names, no links.", FOLDER, lambda p: False), [])


class FolderTests(unittest.TestCase):
    def test_the_skills_own_folder_keeps_the_voice(self):
        """The skill teaches the voice rule, so each of its pages keeps it, which the pages test skips under plugins/."""
        pages = sorted(FOLDER.rglob("*.md"))
        self.assertEqual([p.name for p in pages], ["SKILL.md", "examples.md", "ux-copy.md", "voice.md"])
        for path in pages:
            with self.subTest(page=path.name):
                colons, parens = voice_shares(read(path))
                self.assertLessEqual(colons, VOICE_SHARE, f"{path.name}: {colons:.0%} of sentences join clauses with a colon")
                self.assertLessEqual(parens, VOICE_SHARE, f"{path.name}: {parens:.0%} of sentences hold parentheses")


class ExampleTests(unittest.TestCase):
    PAIR = "| Rule | Before | After |\n| --- | --- | --- |\n"

    def test_every_example_is_a_pair_that_meets_the_measure(self):
        text = read(EXAMPLES)
        self.assertGreater(len(example_rows(text)), 25, "the checker found almost no example")
        self.assertEqual(example_problems(text), [])

    def test_a_broken_example_is_found(self):
        long = " ".join(["word"] * 36) + "."
        cases = {
            "a blank cell": ("| One | Before text. |  |\n", "a blank cell"),
            "the same Before and After": ("| One | Same text. | Same text. |\n", "the same Before and After"),
            "a rule shown twice": ("| One | A. | B. |\n| One | C. | D. |\n", "shown twice"),
            "After over the cap": (f"| One | Before text. | {long} |\n", "over 35 words"),
        }
        for name, (rows, problem) in cases.items():
            with self.subTest(name):
                found = example_problems(self.PAIR + rows)
                self.assertTrue(any(problem in f for f in found), found)
        self.assertEqual(example_problems(self.PAIR + "| One | Before text. | After text. |\n| Two | Old way. | New way. |\n"), [])
        self.assertEqual(example_rows("| A | B |\n| --- | --- |\n| 1 | 2 |\n"), [])


class LedgerTests(unittest.TestCase):
    def test_every_rule_has_a_proof(self):
        items = rule_items(documents.raw_section(read(SKILL), "Implement"))
        labels = {row["Rule"] for row in example_rows(read(EXAMPLES))}
        self.assertGreater(len(items), 25, "the checker found almost no rule")
        self.assertEqual(ledger_problems(items, LEDGER, labels, resolves), [])

    def test_a_rule_without_proof_is_found(self):
        items = ["Use the thing.", "Do the other thing.", "gives a case |"]
        ledger = (("Use the", ("Row one",), ()), ("Do the other", (), ("test_plain_language_proof.LedgerTests.test_a_rule_without_proof_is_found",)))
        labels = {"Row one"}
        self.assertEqual(len(ledger_problems(items, ledger, labels, resolves)), 1)
        self.assertEqual(ledger_problems(items[:2], ledger, labels, resolves), [])
        broken = {
            "a stale entry": (items[:2], (*ledger, ("Gone", ("Row one",), ())), labels),
            "an example row that is gone": (items[:2], ledger, set()),
            "no proof named": (items[:2], (("Use the", (), ()), ledger[1]), labels),
            "a test that is gone": (items[:2], (ledger[0], ("Do the other", (), ("test_plain_language_proof.Nope.nope",))), labels),
            "an entry that starts two rules": (["Use it.", "Use that."], (("Use", ("Row one",), ()),), labels),
        }
        for name, (its, led, lab) in broken.items():
            with self.subTest(name):
                self.assertEqual(len(ledger_problems(its, led, lab, resolves)), 1, ledger_problems(its, led, lab, resolves))

    def test_the_items_are_read_from_lists_and_tables(self):
        text = "- A bullet\n1. A step\n\n| Head | Two |\n| --- | --- |\n| One | Two |\n```\n- not a rule\n```\n"
        self.assertEqual(sorted(rule_items(text)), ["A bullet", "A step", "One | Two |"])


class RoleTests(unittest.TestCase):
    @staticmethod
    def without_it(roles: dict) -> list[str]:
        return [k for k, r in roles.items() if set(r["practices"]) & set(TEXT_PRACTICES) and "plain-language" not in r["practices"]]

    def test_a_role_that_writes_text_may_load_the_skill(self):
        self.assertEqual(self.without_it(team_registry.roles()["roles"]), [])

    def test_a_role_without_it_is_found(self):
        roles = {
            "a": {"practices": ["cli-design"]},
            "b": {"practices": ["cli-design", "plain-language"]},
            "c": {"practices": ["debugging"]},
            "d": {"practices": []},
        }
        self.assertEqual(self.without_it(roles), ["a"])


if __name__ == "__main__":
    unittest.main()
