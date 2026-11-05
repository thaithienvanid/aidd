"""A report, not a check: how the agent files read against rules the plain-language skill sets and no test holds yet.

Run `python3 tests/test_plain_language_report.py --report` to print it. The report counts three things in the files an
agent reads (the aidd skill and the team's commands). It never fails on what it finds, because rewriting those files is
a separate change. The tests here hold only that the counting is right, in both directions.

1. The voice shares: the sentences that join two clauses with a colon, and the sentences that hold parentheses. The
   skill's limit is 10%, which `test_plain_language.py` holds for the pages at the top and in docs/.
2. The instruction limit: ASD-STE100 allows 20 words in an instruction. A numbered step is the nearest thing a script
   can tell from a description, so each sentence of a numbered step is counted.
3. The paragraph limit: ASD-STE100 allows 6 sentences in a paragraph.
"""

import re
import sys
import unittest

from helpers import ROOT, repo_files
from test_plain_language import (
    GENERATED_BLOCK,
    VOICE_MIN_SENTENCES,
    VOICE_SHARE,
    measured,
    prose_units,
    sentences,
    voice_shares,
    without_code,
)

# The folders an agent reads: the aidd skill, and the team's commands.
AGENT_FOLDERS = (".agents/skills/aidd/", "plugins/aidd-team/commands/")
# Limits the plain-language skill takes from ASD-STE100: words in an instruction, and sentences in a paragraph.
INSTRUCTION_WORDS = 20
PARAGRAPH_SENTENCES = 6
STEP = re.compile(r"^\s*\d+\.\s+(.*)")
LIST_START = re.compile(r"^\s*(?:[-*]|\d+\.)\s")


def agent_pages() -> list[str]:
    """The Markdown pages in AGENT_FOLDERS."""
    return [f for f in repo_files() if f.endswith(".md") and f.startswith(AGENT_FOLDERS)]


def long_voice(text: str) -> tuple[float, float] | None:
    """(colon share, parenthesis share) of a page when either is over the limit and the page has enough sentences to
    mean something, else None. The shares are those of `voice_shares`."""
    if len(measured(GENERATED_BLOCK.sub("", text))) < VOICE_MIN_SENTENCES:
        return None
    colons, parens = voice_shares(text)
    return (colons, parens) if max(colons, parens) > VOICE_SHARE else None


def numbered_steps(text: str) -> list[str]:
    """The text of each numbered list item outside code blocks and comments, its continuation lines joined."""
    steps: list[str] = []
    for line in without_code(text).splitlines():
        if (m := STEP.match(line)) is not None:
            steps.append(m.group(1).strip())
        elif steps and line.strip() and line.startswith((" ", "\t")) and not LIST_START.match(line) and not line.lstrip().startswith(("|", "#")):
            steps[-1] += " " + line.strip()
    return steps


def long_instructions(text: str) -> list[tuple[int, str]]:
    """Each sentence of a numbered step that has more than INSTRUCTION_WORDS words, with its count."""
    return [(n, s) for step in numbered_steps(GENERATED_BLOCK.sub("", text)) for n, s in sentences(step) if n > INSTRUCTION_WORDS]


def long_paragraphs(text: str) -> int:
    """How many paragraphs have more than PARAGRAPH_SENTENCES sentences. A list item is a paragraph of its own."""
    return sum(1 for unit in prose_units(GENERATED_BLOCK.sub("", text)) if len(sentences(unit)) > PARAGRAPH_SENTENCES)


def report() -> list[str]:
    """The three counts over the agent files, as lines to print."""
    voice, steps, paragraphs = {}, {}, {}
    pages = agent_pages()
    for rel in pages:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if (shares := long_voice(text)) is not None:
            voice[rel] = shares
        if found := long_instructions(text):
            steps[rel] = found
        if count := long_paragraphs(text):
            paragraphs[rel] = count
    lines = [f"{len(pages)} agent pages: {', '.join(AGENT_FOLDERS)}", ""]
    lines.append(f"Voice: {len(voice)} pages join clauses with a colon, or hold parentheses, in more than {VOICE_SHARE:.0%} of their sentences.")
    lines += [f"  {rel}: colon {c:.0%}, parentheses {p:.0%}" for rel, (c, p) in sorted(voice.items(), key=lambda kv: -max(kv[1]))]
    total = sum(len(v) for v in steps.values())
    lines.append(f"Instructions: {total} sentences in numbered steps are over {INSTRUCTION_WORDS} words, in {len(steps)} pages. The longest:")
    worst = sorted(((n, rel, s) for rel, found in steps.items() for n, s in found), reverse=True)[:5]
    lines += [f"  {rel}, {n} words: {s[:100]}" for n, rel, s in worst]
    lines.append(f"Paragraphs: {sum(paragraphs.values())} are over {PARAGRAPH_SENTENCES} sentences, in {len(paragraphs)} pages.")
    return lines


class CountTests(unittest.TestCase):
    def test_a_step_is_counted_over_the_instruction_limit(self):
        def words(n: int) -> str:
            return " ".join(["word"] * n) + "."

        cases = (
            ("one over", f"1. {words(21)}\n", 1),
            ("at the limit", f"1. {words(20)}\n", 0),
            ("the second sentence is over", f"1. {words(5)} {words(22)}\n", 1),
            ("two steps, both over", f"1. {words(25)}\n2. {words(30)}\n", 2),
            ("a continuation line joins the step", "1. " + " ".join(["word"] * 12) + "\n   " + words(12) + "\n", 1),
            ("a bullet is not a step", f"- {words(30)}\n", 0),
            ("prose is not a step", f"{words(30)}\n", 0),
            ("a step in a code block", f"```\n1. {words(30)}\n```\n", 0),
            ("a step in a comment", f"<!--\n1. {words(30)}\n-->\n", 0),
            ("a step in a generated block", f"<!-- aidd:gen x -->\n1. {words(30)}\n<!-- aidd:end -->\n", 0),
            ("no step", "", 0),
        )
        for name, text, expected in cases:
            with self.subTest(name):
                self.assertEqual(len(long_instructions(text)), expected)

    def test_a_paragraph_is_counted_over_the_sentence_limit(self):
        cases = (
            ("seven sentences", "Run it. " * 7, 1),
            ("six sentences", "Run it. " * 6, 0),
            ("two paragraphs, one over", "Run it. " * 7 + "\n\n" + "Run it. " * 2, 1),
            ("a list of seven items", "".join(f"- Run it {i}.\n" for i in range(7)), 0),
            ("no prose", "```\nRun it. Run it. Run it. Run it. Run it. Run it. Run it.\n```\n", 0),
        )
        for name, text, expected in cases:
            with self.subTest(name):
                self.assertEqual(long_paragraphs(text), expected)

    def test_a_page_is_listed_for_its_voice_only_over_the_share(self):
        colon = "Say it: it lands. " * 5
        calm = "Run the tests first. " * 15
        cases = (
            ("a quarter join with a colon", colon + calm, True),
            ("a quarter hold parentheses", "Run it (once). " * 5 + calm, True),
            ("none does", calm + calm, False),
            ("too few sentences to mean anything", "Say it: it lands. " * 5, False),
        )
        for name, text, listed in cases:
            with self.subTest(name):
                self.assertEqual(long_voice(text) is not None, listed)
        self.assertEqual(long_voice(colon + calm), (0.25, 0.0))

    def test_the_report_runs_on_the_agent_files(self):
        """It finds the agent files, counts without error, and fails on no finding. Run this file with --report to read it."""
        self.assertGreater(len(agent_pages()), 30, "the report found almost no agent page")
        lines = report()
        for heading in ("Voice:", "Instructions:", "Paragraphs:"):
            self.assertEqual(sum(1 for ln in lines if ln.startswith(heading)), 1, heading)


if __name__ == "__main__":
    if "--report" in sys.argv:
        print("\n".join(report()))
    else:
        unittest.main()
