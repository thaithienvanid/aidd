"""aidd replaces and removes only the text between its own marks. Every line outside them survives `aidd upgrade` and
`aidd uninstall` byte for byte, in each layout a file can take."""

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # puts src on the path

from aidd import config
from aidd.setup import adoption, marked_sections, team_install, uninstalling, upgrading

MINE, AIDD = "mine", "aidd"


class Layouts(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.section = adoption.agents_snippet(self.root, True)  # closed, with its end mark
        self.team = team_install.team_section([], False)
        self.stale_section = self.section.replace("This repository uses aidd.", "Run `aidd gate` first. This repository uses aidd.")
        self.stale_team = self.team.replace("| Role |", "| `aidd-retired` | x | y |\n| Role |", 1)
        self.unclosed = self.section.replace("\n<!-- /aidd -->\n", "\n").rstrip("\n") + "\n"  # the end mark is missing
        self.layouts = {
            "closed sections, text above, between, and below": [
                (MINE, "# Agents\n\nOur rule.\n\n"),
                (AIDD, self.stale_section),
                (MINE, "\n## Ours\n\n### A note\n\nkeep this.\n\n"),
                (AIDD, self.stale_team),
                (MINE, "\nThe last words, with no heading.\n"),
            ],
            "text right after an end mark": [(MINE, "# Agents\n"), (AIDD, self.stale_section), (MINE, "Right after the end mark.\n")],
            "a section with no end mark, then a heading of the person's": [
                (MINE, "# Agents\n\nAbove.\n\n"),
                (AIDD, self.unclosed),
                (MINE, "\n## Ours\n\nkeep me\n"),
            ],
            "a section with no end mark before a closed one": [
                (MINE, "# Agents\n\n"),
                (AIDD, self.unclosed),
                (MINE, "\n## Ours\n\nkeep me, and my other notes.\n\n### More\n\nof mine.\n\n"),
                (AIDD, self.stale_section),
                (MINE, "Tail.\n"),
            ],
            "a team section with no end mark before a closed one": [
                (MINE, "# Agents\n\n"),
                (AIDD, self.team.replace("\n<!-- /aidd-team -->\n", "\n").rstrip("\n") + "\n"),
                (MINE, "\n## Ours\n\nkeep me\n\n"),
                (AIDD, self.stale_team),
            ],
            "a mark in a code sample": [
                (MINE, "# Agents\n\n```md\n<!-- aidd -->\n## Sample\n\nrun `aidd gate`\n<!-- /aidd -->\n```\n\n"),
                (AIDD, self.stale_section),
            ],
        }

    @staticmethod
    def build(segments):
        return "".join(text for _, text in segments)

    def assert_mine_survives(self, text, segments, what, tidy=False):
        """Each of the person's segments is in `text`, in order. `tidy` ignores the blank lines at a segment's edges, which
        an uninstall joins with one blank line."""
        at = 0
        for kind, seg in segments:
            if kind == MINE:
                seg = seg.strip("\n") if tidy else seg
                found = text.find(seg, at)
                self.assertNotEqual(found, -1, f"{what}: {seg!r} was lost")
                at = found + len(seg)

    def test_every_line_outside_the_marks_survives_an_upgrade_byte_for_byte(self):
        for name, segments in self.layouts.items():
            with self.subTest(name):
                (self.root / "AGENTS.md").write_text(self.build(segments), encoding="utf-8")
                changed, _ = upgrading.refreshed_instruction_files(self.root, self.team)
                new = changed.get(self.root / "AGENTS.md", self.build(segments))
                self.assert_mine_survives(new, segments, "upgrade")

    def test_every_line_outside_the_marks_survives_an_uninstall_byte_for_byte(self):
        for name, segments in self.layouts.items():
            with self.subTest(name):
                text = self.build(segments)
                stripped = upgrading.strip_marked_section(upgrading.strip_marked_section(text, config.TEAM_MARK), adoption.AGENTS_MARK)
                self.assert_mine_survives(stripped, segments, "uninstall", tidy=True)
                (self.root / "AGENTS.md").write_text(text, encoding="utf-8")
                uninstalling.uninstall(self.root, yes=True)
                after = (self.root / "AGENTS.md").read_text(encoding="utf-8") if (self.root / "AGENTS.md").exists() else ""
                self.assert_mine_survives(after, [s for s in segments if s[0] == MINE and s[1].strip() != "# Agents"], "uninstall --yes", tidy=True)

    def test_an_end_mark_closes_only_the_section_before_the_next_opening_mark(self):
        text = "# Agents\n\n<!-- aidd -->\n## Change control\n\nold\n\n## Ours\n\nkeep me\n\n<!-- aidd -->\n## Copy\n\nbody\n<!-- /aidd -->\n"
        first, second = marked_sections.sections(text, adoption.AGENTS_MARK)
        self.assertFalse(first.closed)
        self.assertTrue(second.closed)
        self.assertNotIn("keep me", text[first.start : first.end] + text[second.start : second.end])
        self.assertIn("keep me", upgrading.strip_marked_section(text, adoption.AGENTS_MARK))

    def test_a_section_with_no_end_mark_is_reported_and_left_alone(self):
        for tail in ("", "Our line.\n"):
            with self.subTest(tail=tail):
                (self.root / "AGENTS.md").write_text(f"# Agents\n\n{self.unclosed}\n{tail}", encoding="utf-8")
                changed, left = upgrading.refreshed_instruction_files(self.root, self.team)
                self.assertNotIn(self.root / "AGENTS.md", changed)
                self.assertTrue(any("delete that section and run `aidd init`" in x for x in left), left)

    def test_the_note_for_a_team_section_names_init_with_team(self):
        (self.root / "AGENTS.md").write_text("# Agents\n\n<!-- aidd-team -->\n## Team roles (aidd-team)\n\nmy own words\n", encoding="utf-8")
        _, left = upgrading.refreshed_instruction_files(self.root, self.team)
        self.assertTrue(any("run `aidd init --aidd-team`" in x for x in left), left)


if __name__ == "__main__":
    unittest.main()
