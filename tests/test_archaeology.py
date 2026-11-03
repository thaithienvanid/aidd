"""No archaeology in the text a model reads: no issue or PR numbers, no dated incident stories, no session history.

A model reads the agents, the commands, the skills and their references, the domain packs, AGENTS.md, and the aidd
skill as instructions. "Fixed in #123", "on 2026-09-12, an agent deleted the tests", or "last time we" tell it a story,
not a rule. The story costs tokens on every load, and the model may follow the story instead of the rule. Write the
rule, and keep the history in git, the CHANGELOG, and the decision records.

The patterns stay narrow: a standard's citation ("UAX #9", "Issue 9, January 2025"), a hex color, and a date in front
matter or in a table's Checked column do not match.
"""

import re
import unittest

from helpers import ROOT, repo_files

# The text a model reads as instructions, as path prefixes relative to the repository root.
MODEL_READ = (
    "AGENTS.md",
    "templates/AGENTS.snippet.md",
    "templates/REVIEW.md",
    "REVIEW.md",
    "plugins/aidd-team/agents/",
    "plugins/aidd-team/commands/",
    "plugins/aidd-team/skills/",
    ".agents/skills/aidd/",
)

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

PATTERNS = {
    # "#123" only where it names an issue: "(#123)", "fixes #123", "MR !12". A bare "#1" ("the #1 cause"), a standard's
    # "UAX #9", an HTML entity, a URL fragment, and a hex color do not match.
    "an issue or PR number": re.compile(r"\(#\d+\)|\b(?:[Ff]ix(?:es|ed)?|[Cc]loses?d?|[Rr]esolve[sd]?|[Ss]ee)\s+#\d+\b|\b(?:MRs?|[Mm]erge requests?)\s+!\d+\b"),
    # "issue 123", "PR 45", "pull request #6", but not an edition such as "Issue 9, January 2025".
    "an issue or PR reference": re.compile(rf"\b(?:[Ii]ssues?|PRs?|MRs?|[Pp]ull requests?|[Mm]erge requests?|[Tt]ickets?)\s+#?\d+\b(?!,?\s+(?:{MONTHS}))"),
    # "on 2026-09-12, an agent ...": a dated story. A bare date (front matter, a Checked column) does not match.
    "a dated incident story": re.compile(r"\b[Oo]n 20\d\d-\d\d(?:-\d\d)?,? (?:an?|the|our|we|one|someone|somebody)\b"),
    # Phrases that point at an earlier session the reader never saw.
    "session history": re.compile(r"\b(?:last time|we used to|previously,? we|in (?:a|the) (?:previous|last|earlier) session|as we did before)\b", re.I),
}


def model_read_files() -> list[str]:
    return sorted(f for f in repo_files() if f.endswith(".md") and any(f == p or (p.endswith("/") and f.startswith(p)) for p in MODEL_READ))


def hits(text: str) -> list[tuple[str, int, str]]:
    out = []
    for kind, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append((kind, line, m.group(0)))
    return out


class ArchaeologyLintTests(unittest.TestCase):
    def test_model_read_text_has_no_archaeology(self):
        files = model_read_files()
        self.assertGreater(len(files), 100, "the scan found the agents, commands, skills, and references")
        for page in ("AGENTS.md", "REVIEW.md", "templates/REVIEW.md", "plugins/aidd-team/commands/review.md", ".agents/skills/aidd/SKILL.md"):
            self.assertIn(page, files)
        found = [f"{rel}:{line}: {kind}: {match!r}" for rel in files for kind, line, match in hits((ROOT / rel).read_text(encoding="utf-8"))]
        self.assertEqual(found, [], "write the rule, not its history:\n" + "\n".join(found))

    def test_the_patterns_catch_archaeology(self):
        for bad in (
            "Fixed in (#123).",
            "This fixes #123.",
            "See PR #12 and issue #12.",
            "Landed in MR !12.",
            "See issue 482 for the details.",
            "As PR #77 showed, the hook fails open.",
            "This was added in pull request 12.",
            "On 2026-09-12, an agent deleted the frozen tests.",
            "on 2026-10, we saw the gate pass a red run.",
            "Last time the reviewer missed it.",
            "We used to run the verifier after the reviewer.",
            "In the previous session the lead edited a Spec.",
        ):
            self.assertTrue(hits(bad), bad)

    def test_the_patterns_spare_citations_and_dates(self):
        for good in (
            "| S7 | Unicode Bidirectional Algorithm (UAX #9) | Revision 52 | 2026-10-02 |",
            "| ASD-STE100 | Issue 9, January 2025 | 2026-10-02 |",
            '  success: "#067647"',
            'checked: "2026-09-30"',
            "| Standard | Edition | Checked |\n| OWASP ASVS | 5.0.0 | 2026-09-28 |",
            "Read [the gate](references/gate.md#the-rules) first.",
            "&#123; is an HTML entity.",
            "A missing index is the #1 cause of a slow page.",
            "Rank #2 of 5.",
            "The tool is used to measure coverage.",
            "Run `/aidd-team:review <PR/MR number>`.",
        ):
            self.assertEqual(hits(good), [], good)


if __name__ == "__main__":
    unittest.main()
