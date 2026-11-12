"""aidd's pages do not use a word the glossary says to avoid.

The words come from docs/GLOSSARY.md itself: a word in double quotes in an *Avoid* line. So a new *Avoid* line is checked with no new
test code. The test leaves three kinds of word, each because the glossary says so:

- a word that is a glossary term itself (`Phase` and `Stage`, `Sign-off`, `Route`), since each has a meaning of its own;
- a word whose sentence says "for" or "alone", such as `"permission" and "operation" for it`, since it is wrong for one term only;
- a line's *Avoid* text, and a word shown in quotes or in code, since those name the word.

Every other use is a failure unless `ALLOWED_TERMS` or `ALLOWED_USES` excuses it with a reason, and an excuse nothing needs fails.
"""

import re
import unittest

from helpers import ROOT

# What aidd ships: the code, the file formats, the templates, the skill, the plugins, and the docs.
SHIPPED = ("src", "schemas", "templates", ".agents/skills/aidd", "plugins", "docs")
SUFFIXES = {".py", ".json", ".md", ".html", ".yaml", ".yml", ".txt", ".toml", ".sh", ".js", ".css"}
QUALIFIER = re.compile(r"\b(for|alone)\b")
QUOTED = re.compile(r'"([^"]+)"')
MENTION_MARKS = ('"', "“", "”", "`")

# A whole word that is a plain word in its own sense, as `{word: reason}`.
ALLOWED_TERMS = {
    "ship": "a plain verb (ship to a platform, ship behind a flag); the glossary means the loop step, which a word match cannot see",
}
# A phrase that holds the word in another sense, as `{phrase in lower case: reason}`. A use is excused when it sits inside the phrase.
ALLOWED_USES = {
    "time zone": "a place's clock offset, from the IANA database and the internationalization skill",
    "trust zone": "a security term: the area of a system one trust level covers, drawn in a data-flow diagram",
    "zone rule": "a time zone's rules, which change and need updating",
    "per zone": "a cloud availability zone",
    "no zone": "a time value without a time zone",
    "iana zone id": "the identifier of a time zone, from the IANA database",
    "explicit zone": "a timestamp that names its time zone",
    "approving review": "GitHub's own name for a review that approves a pull request",
    "local code graph": "what the CodeGraph extension adds, in its own words",
}


def avoided(glossary: str) -> dict[str, str]:
    """{word to avoid, in lower case: the glossary term whose *Avoid* line names it}."""
    rows = [line for line in glossary.splitlines() if line.startswith("| ")]
    terms = {row.split("|")[1].strip().strip("`").lower() for row in rows}
    found: dict[str, str] = {}
    for row in rows:
        if "*Avoid:*" not in row:
            continue
        for sentence in re.split(r"(?<=[.;])\s+", row.split("*Avoid:*", 1)[1].rstrip(" |")):
            if '"' not in sentence or QUALIFIER.search(sentence[sentence.index('"') :]):
                continue
            for word in QUOTED.findall(sentence):
                if word.lower() not in terms:
                    found[word.lower()] = row.split("|")[1].strip()
    return found


def shipped_lines():
    """Each line aidd ships as `(path, line number, text)`, without the *Avoid:* text a glossary row ends in."""
    for top in SHIPPED:
        for path in sorted((ROOT / top).rglob("*")):
            if path.suffix in SUFFIXES and path.is_file() and "__pycache__" not in path.parts:
                for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    yield path.relative_to(ROOT).as_posix(), number, line.split("*Avoid:*", 1)[0]


def uses(word: str, line: str, excuses: dict[str, str]) -> tuple[list[str], set[str]]:
    """The uses of `word` on a line that nothing excuses (their text), and the excuses that covered one."""
    lower, loose, used = line.lower(), [], set()
    for hit in re.finditer(rf"(?<![\w-]){re.escape(word)}(?![\w-])", lower):
        start, end = hit.span()
        if (start and line[start - 1] in MENTION_MARKS) and (end < len(line) and line[end] in MENTION_MARKS):
            continue  # the word shown in quotes or in code
        covering = [
            phrase for phrase in excuses for at in (m.start() for m in re.finditer(re.escape(phrase), lower)) if at <= start and end <= at + len(phrase)
        ]
        used.update(covering)
        if not covering:
            loose.append(line.strip()[:120])
    return loose, used


class AvoidWords(unittest.TestCase):
    glossary = (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8")

    @classmethod
    def setUpClass(cls):
        cls.words = avoided(cls.glossary)
        cls.lines = list(shipped_lines())

    def found(self) -> tuple[dict[str, list[str]], set[str]]:
        loose: dict[str, list[str]] = {}
        used: set[str] = set()
        for word in self.words:
            excuses = {p: r for p, r in ALLOWED_USES.items() if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", p)}
            for path, number, line in self.lines:
                if word not in line.lower():
                    continue
                bad, covered = uses(word, line, excuses)
                used |= covered
                if bad and word in ALLOWED_TERMS:
                    used.add(word)
                elif bad:
                    loose.setdefault(word, []).extend(f"{path}:{number}: {text}" for text in bad)
        return loose, used

    def test_the_glossary_names_the_words(self):
        for word in ("design approval", "protected path", "approve the plan", "zone", "user request", "implementer"):
            self.assertIn(word, self.words, f"the Avoid lines no longer name {word!r}")
        for word in ("sign-off", "phase", "permission", "operation", "route"):
            self.assertNotIn(word, self.words, f"{word!r} is a glossary term or is wrong for one term only")
        self.assertGreater(len(self.lines), 5000, "the walk must reach what aidd ships")

    def test_no_page_uses_a_word_the_glossary_says_to_avoid(self):
        loose, _ = self.found()
        self.assertEqual(loose, {}, "say the glossary's term, or excuse the use with a reason in ALLOWED_USES")

    def test_each_excuse_is_needed_and_has_a_reason(self):
        _, used = self.found()
        for excuse, reason in {**ALLOWED_TERMS, **ALLOWED_USES}.items():
            self.assertTrue(reason.strip(), f"{excuse!r} needs a reason")
            self.assertIn(excuse, used, f"{excuse!r} excuses nothing now: drop it")
        for word in ALLOWED_TERMS:
            self.assertIn(word, self.words, f"{word!r} is no avoided word now: drop the excuse")

    def test_a_use_is_found_and_a_quote_or_an_excuse_is_not(self):
        word = "protected path"
        self.assertEqual(uses(word, "Add a protected path to the config.", {})[0], ["Add a protected path to the config."])
        self.assertEqual(uses(word, 'The glossary says "protected path" is wrong.', {})[0], [])
        self.assertEqual(uses(word, "A protected pathway is fine.", {})[0], [])
        loose, used = uses("zone", "Set the time zone and a zone.", {"time zone": "x"})
        self.assertEqual((loose, used), (["Set the time zone and a zone."], {"time zone"}))


if __name__ == "__main__":
    unittest.main()
