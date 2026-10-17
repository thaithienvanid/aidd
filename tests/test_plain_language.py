"""Plain language on every page, so a newcomer reads each sentence once.

The rule: over the prose, without front matter, code blocks, tables, headings, HTML, and inline code, no sentence is
over 35 words, and at least 90% are 25 words or fewer. Every Markdown page in the repository meets it, and so does
`llms.txt`, except the files in NOT_OURS. So does each table column in LOCKED_COLUMNS, one paragraph a cell. A page
with no prose outside code and comments, such as a template, has nothing to measure. The other ASD-STE100 (Simplified
Technical English) sentence rules, such as one instruction per sentence and the active voice, are applied by review.

A page that fails names its long sentences: shorten them. Never add a page to NOT_OURS to make a change pass.

One exemption: QUOTED holds fixed external wording, such as the BCP 14 (RFC 8174) boilerplate, which is never
paraphrased. The measure skips a sentence only when it matches a QUOTED entry exactly.
"""

import re
import unittest

from helpers import ROOT, repo_files

# Pages the rule reads beyond the Markdown ones.
EXTRA_PAGES = ("llms.txt",)
# Tables the rule also measures, one column each: (page, column index). The prose measure skips tables, so a page
# whose content is a table, such as the glossary, needs its column named here. Never take one out.
LOCKED_COLUMNS = (("docs/GLOSSARY.md", 1),)
# Fixed external wording, never paraphrased: each entry is one sentence as `sentences()` yields it (links as their text).
# The measure skips a sentence only on an exact match, so a changed copy is measured like any other sentence.
QUOTED = (
    'The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", '
    '"NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 (RFC 2119, '
    "RFC 8174) when, and only when, they appear in all capitals, as shown here.",
)
# Not ours to rewrite: other tools' sample files that the import tests read.
NOT_OURS = ("tests/fixtures/",)
MAX_WORDS = 35
SHORT_WORDS = 25
SHORT_SHARE = 0.9

# Front matter: a `---` (YAML) or `+++` (TOML) block at the very top, skipped only when a line in it is a key (`key:` or
# `key =`), so a page that opens with a horizontal rule is still measured.
FRONT_MATTER = re.compile(r"\A(---|\+\+\+)[ \t]*\n(.*?\n)?\1[ \t]*(?:\n|\Z)", re.S)
FRONT_MATTER_KEY = re.compile(r"^[A-Za-z_][\w.-]*(?::(?:[ \t]|$)|[ \t]*=)", re.M)
LIST_ITEM = re.compile(r"^(?:[-*]|\d+\.)\s+")
WORD = re.compile(r"[A-Za-z0-9][\w'’.+/-]*")
# A code fence: three or more backticks, closed by the same run, so a longer fence can show a shorter one inside it.
FENCE = re.compile(r"(`{3,}).*?\1", re.S)
TABLE_RULE = re.compile(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?")
# A sentence ends at `.`, `!`, or `?`, with any closing quote or bracket after it, before a space; never after e.g. or i.e.
SENTENCE_END = re.compile(r"""(?<!\be\.g\.)(?<!\bi\.e\.)(?<=[.!?])\s+|(?<=[.!?]["”’')\]])\s+""")


def without_code(text: str) -> str:
    """The page without its code blocks and HTML comments."""
    text = FENCE.sub("\n\n", text)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def table_cells(text: str, column: int) -> list[str]:
    """One column of every table on a page, without the header rows and the rule rows (`| --- |`). A cell ends at
    each `|` that no backslash escapes, as in GitHub's tables."""
    lines = [ln.strip() for ln in without_code(text).splitlines()]
    cells = []
    for i, s in enumerate(lines):
        if not s.startswith("|") or TABLE_RULE.fullmatch(s) or (i + 1 < len(lines) and TABLE_RULE.fullmatch(lines[i + 1])):
            continue
        row = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if column < len(row) and row[column]:
            cells.append(row[column])
    return cells


def column_prose(text: str, column: int) -> str:
    """One column of a page's tables as prose, one paragraph a cell, for the same measure as a page."""
    return "\n\n".join(table_cells(text, column))


def prose_units(text: str) -> list[str]:
    """The prose of a Markdown page as paragraphs and list items, without its YAML or TOML front matter (metadata, not
    prose: its keys and values would join into one sentence), code blocks, comments, tables, headings, and HTML lines. A
    blockquote counts as prose, without its marker and its alert label (`[!IMPORTANT]`)."""
    front = FRONT_MATTER.match(text)
    if front and FRONT_MATTER_KEY.search(front.group(2) or ""):
        text = text[front.end() :]
    text = without_code(text)
    units: list[str] = []
    para: list[str] = []
    quoted = False

    def close() -> None:
        if para:
            units.append(" ".join(para))
            para.clear()

    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "<")):
            close()
            continue
        if s.startswith(">") != quoted:
            close()
            quoted = not quoted
        s = re.sub(r"^>\s*(?:\[![A-Z]+\]\s*)?", "", s)
        if LIST_ITEM.match(s):
            close()
            s = LIST_ITEM.sub("", s)
        if s:
            para.append(s)
    close()
    return units


def sentences(text: str) -> list[tuple[int, str]]:
    """Every prose sentence with its word count. Inline code, HTML tags, and bold or italic marks are removed, a link
    keeps its text, and a sentence ends as SENTENCE_END says."""
    out = []
    for unit in prose_units(text):
        unit = re.sub(r"`[^`]*`", " ", unit)
        unit = re.sub(r"\*+", "", unit)
        unit = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", unit)
        unit = re.sub(r"<[^>]+>", " ", unit)
        for sentence in SENTENCE_END.split(unit):
            words = WORD.findall(sentence)
            if words:
                out.append((len(words), sentence.strip()))
    return out


class MeasureTests(unittest.TestCase):
    def test_it_skips_code_tables_headings_and_inline_code(self):
        text = (
            "# A heading with many many words in it\n\n"
            "Run `aidd init --profile solo --approvers email:you@example.com` first. Then check it.\n\n"
            "| a | b |\n| --- | --- |\n| one two three | four |\n\n"
            "```sh\naidd doctor and many more words here\n```\n\n"
            "- A list item, [with a link](docs/X.md#anchor).\n"
            "> [!IMPORTANT]\n> **Pre-release.** Two words.\n"
        )
        self.assertEqual(
            sentences(text),
            [(2, "Run   first."), (3, "Then check it."), (6, "A list item, with a link."), (1, "Pre-release."), (2, "Two words.")],
        )

    def test_it_skips_a_leading_front_matter(self):
        """Front matter is data (TOML between +++ lines, YAML between --- lines), never prose; a later --- is a rule."""
        for fence in ("---", "---"):
            with self.subTest(fence=fence):
                text = f"{fence}\nkind: spec\ntitle: a title with a great many words in it\n{fence}\n\nRun the tests first.\n"
                self.assertEqual(sentences(text), [(4, "Run the tests first.")])
        self.assertEqual(sentences("Run it.\n\n---\n\nThen check it.\n"), [(2, "Run it."), (3, "Then check it.")])

    def test_a_longer_fence_hides_a_shorter_one_inside_it(self):
        text = "Before the block.\n\n````markdown\nA sample:\n\n```sh\naidd doctor\n```\n\nNot prose at all here.\n````\n\nAfter the block.\n"
        self.assertEqual(sentences(text), [(3, "Before the block."), (3, "After the block.")])

    def test_a_table_column_is_measured_cell_by_cell(self):
        text = (
            "Some prose.\n\n| Term | Meaning |\n| --- | :--- |\n| Gate | The program that decides. It posts a status. |\n"
            "| Run | One `a \\| b` pass. |\n\n```\n| Code | Not a row. |\n```\n"
        )
        self.assertEqual(table_cells(text, 1), ["The program that decides. It posts a status.", "One `a \\| b` pass."])
        self.assertEqual([n for n, _ in sentences(column_prose(text, 1))], [4, 4, 2])

    def test_a_sentence_ends_before_a_closing_quote_or_bracket(self):
        cases = {
            '."': 'Type "yes." Then wait.',
            ".)": "Run it (once.) Then wait.",
            '?"': 'Ask "why?" Then wait.',
            "!)": "Stop it (now!) Then wait.",
        }
        for end, text in cases.items():
            with self.subTest(end=end):
                self.assertEqual([s for _, s in sentences(text)], [text[: text.index(end) + 2], "Then wait."])

    def test_it_skips_the_front_matter_only_at_the_top(self):
        text = '---\ndescription: "A long description, with many words that would join the keys"\nname: x\n---\n\nRun it.\n\n---\n\nThen wait.\n'
        self.assertEqual([s for _, s in sentences(text)], ["Run it.", "Then wait."])

    def test_it_skips_toml_front_matter_too(self):
        text = '---\ntitle: "A long title, with many words that would join the keys"\ndraft: false\n---\n\nRun it.\n'
        self.assertEqual([s for _, s in sentences(text)], ["Run it."])

    def test_a_page_that_opens_with_a_horizontal_rule_is_still_measured(self):
        for rule in ("---", "---"):
            with self.subTest(rule=rule):
                text = f"{rule}\n\nRun it, then read the result.\n\n{rule}\n\nThen wait.\n"
                self.assertEqual([s for _, s in sentences(text)], ["Run it, then read the result.", "Then wait."])

    def test_e_g_and_i_e_end_no_sentence(self):
        text = "Pick a tool, e.g. this one. Pick the first, i.e. the oldest one."
        self.assertEqual([n for n, _ in sentences(text)], [6, 7])


def measured(text: str) -> list[tuple[int, str]]:
    """The sentences the rule measures: every sentence but an exact QUOTED one."""
    return [(n, s) for n, s in sentences(text) if s not in QUOTED]


def page_findings(text: str) -> list[str]:
    """Why a page does not meet the rule, or [] when it does."""
    found = measured(text)
    if not found:
        return ["the measure found no prose"]
    out = []
    long = [s for n, s in found if n > MAX_WORDS]
    if long:
        out.append(f"split each sentence over {MAX_WORDS} words: {long}")
    short = sum(1 for n, _ in found if n <= SHORT_WORDS)
    if short / len(found) < SHORT_SHARE:
        out.append(f"{short} of {len(found)} sentences are {SHORT_WORDS} words or fewer; the longest: {sorted(found, reverse=True)[:5]}")
    return out


def pages() -> list[str]:
    """Every page the rule reads: the Markdown pages and EXTRA_PAGES, outside NOT_OURS."""
    return [f for f in repo_files() if (f.endswith(".md") or f in EXTRA_PAGES) and not f.startswith(NOT_OURS)]


class RuleTests(unittest.TestCase):
    def test_a_page_meets_the_rule_or_says_why_not(self):
        short = "Run the tests first. " * 9
        self.assertEqual(page_findings(short), [])
        self.assertEqual(page_findings("```sh\nonly code\n```\n"), ["the measure found no prose"])
        (finding,) = page_findings(short + " ".join(["word"] * 36) + ".")
        self.assertTrue(finding.startswith(f"split each sentence over {MAX_WORDS} words"), finding)
        (finding,) = page_findings(short + (" ".join(["word"] * 30) + ". ") * 2)
        self.assertTrue(finding.startswith("9 of 11 sentences are 25 words or fewer"), finding)


class QuotedTests(unittest.TestCase):
    def test_the_measure_skips_only_an_exact_quoted_sentence(self):
        short = "Run the tests first. " * 9
        (quote,) = QUOTED
        self.assertEqual(page_findings(short + quote), [])
        for changed in (
            quote.replace("as shown here", "as you see here"),
            quote.replace("The key words", "Note that the key words"),
            quote[:-1] + " and nowhere else.",
        ):
            with self.subTest(changed=changed[:40]):
                (finding,) = page_findings(short + changed)
                self.assertTrue(finding.startswith(f"split each sentence over {MAX_WORDS} words"), finding)

    def test_every_quoted_sentence_is_on_a_page(self):
        """An entry no page quotes is stale: take it out, so the exemption never grows."""
        pages = [(ROOT / rel).read_text(encoding="utf-8", errors="replace") for rel in repo_files() if rel.endswith(".md")]
        for quote in QUOTED:
            with self.subTest(quote=quote[:40]):
                self.assertTrue(any(quote in [s for _, s in sentences(p)] for p in pages), quote)


class StyleTests(unittest.TestCase):
    def test_the_measure_finds_the_prose(self):
        for rel in ("README.md", "docs/INSTALL.md", "CHANGELOG.md"):
            with self.subTest(page=rel):
                self.assertGreater(len(sentences((ROOT / rel).read_text(encoding="utf-8"))), 40, "the measure found almost no prose")

    def test_every_page_meets_the_rule(self):
        found = pages()
        self.assertIn("docs/METHOD.md", found)
        self.assertIn("llms.txt", found)
        for rel in found:
            with self.subTest(page=rel):
                findings = page_findings((ROOT / rel).read_text(encoding="utf-8", errors="replace"))
                self.assertEqual([f for f in findings if f != "the measure found no prose"], [], rel)

    def test_every_locked_column_meets_the_rule(self):
        for rel, column in LOCKED_COLUMNS:
            with self.subTest(page=rel, column=column):
                prose = column_prose((ROOT / rel).read_text(encoding="utf-8"), column)
                self.assertGreater(len(sentences(prose)), 40, "the measure found almost no cells")
                self.assertEqual(page_findings(prose), [], f"{rel}, column {column}")


if __name__ == "__main__":
    unittest.main()
