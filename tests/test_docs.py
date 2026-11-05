"""The documentation holds together: every relative link and anchor resolves, and every path a status page names exists."""

import re
import unittest

from helpers import ROOT, anchors, repo_files

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")


class LinkTests(unittest.TestCase):
    def markdown_files(self):
        # The repository's own files: a walk of the tree would also read .venv/, dist/, and node_modules/.
        return sorted(ROOT / f for f in repo_files() if f.endswith(".md") and (ROOT / f).is_file())

    def test_every_relative_link_and_anchor_resolves(self):
        broken = []
        for md in self.markdown_files():
            for target in LINK.findall(md.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path, _, fragment = target.partition("#")
                dest = (md.parent / path).resolve() if path else md
                if not dest.exists():
                    broken.append(f"{md.relative_to(ROOT)}: missing {target}")
                elif fragment and dest.suffix == ".md" and fragment not in anchors(dest):
                    broken.append(f"{md.relative_to(ROOT)}: no anchor {target}")
        self.assertEqual(broken, [])

    def test_the_review_policy_names_only_modules_that_exist(self):
        # REVIEW.md's repository notes send reviewers to the risk rules' riskiest code: a stale name sends them nowhere.
        notes = (ROOT / "REVIEW.md").read_text(encoding="utf-8").partition("## Repository notes")[2]
        named = re.findall(r"`((?:src|schemas|\.agents)/[\w./-]+)", notes)
        self.assertGreaterEqual(len(named), 8, named)
        for rel in named:
            candidates = [ROOT / rel, ROOT / "src" / "aidd" / rel]
            self.assertTrue(any(c.exists() for c in candidates), f"REVIEW.md names {rel}, which does not exist")


class TableShapeTests(unittest.TestCase):
    """Every table row has as many cells as its header, because GitHub drops the extra cells, so a row run onto another
    row's line never shows."""

    RULE = re.compile(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?")
    FENCE = re.compile(r"^\s*(`{3,}|~{3,})")

    @staticmethod
    def cells(line: str) -> int:
        # A cell ends at each `|` no backslash escapes, as in GitHub's tables, code spans included.
        return len(re.split(r"(?<!\\)\|", line.strip().strip("|")))

    def misshapen_rows(self, text: str) -> list[str]:
        lines, found, fence, width = text.splitlines(), [], None, 0
        for i, line in enumerate(lines):
            opened = self.FENCE.match(line)
            if opened and (fence is None or opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence)):
                fence = None if fence else opened.group(1)
                continue
            s = line.strip()
            if fence or not s.startswith("|"):
                width = 0
            elif i + 1 < len(lines) and self.RULE.fullmatch(lines[i + 1].strip()):
                width = self.cells(s)
            elif width and not self.RULE.fullmatch(s) and self.cells(s) != width:
                found.append(f"line {i + 1}: {self.cells(s)} cells, the header has {width}")
        return found

    def test_every_table_row_has_its_header_s_cells(self):
        bad = []
        for rel in repo_files():
            if rel.endswith(".md") and (ROOT / rel).is_file():
                bad += [f"{rel} {row}" for row in self.misshapen_rows((ROOT / rel).read_text(encoding="utf-8"))]
        self.assertEqual(bad, [], "split the row, or escape a `|` inside a cell as `\\|`")

    def test_the_check_finds_two_rows_on_one_line(self):
        table = "| a | b |\n| --- | --- |\n| 1 | 2 || 3 | 4 |\n| 5 | 6 \\| 7 |\n"
        self.assertEqual(self.misshapen_rows(table), ["line 3: 5 cells, the header has 2"])
        self.assertEqual(self.misshapen_rows("```\n| a | b |\n| --- | --- |\n| 1 |\n```\n"), [])


class DuplicationTests(unittest.TestCase):
    """One owner per topic: a long sentence copied into a second page drifts from the first, so link to it instead."""

    PAGES = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "GOVERNANCE.md", "SECURITY.md", "RELEASING.md", "REVIEW.md")
    PAGES += ("llms-install.md",)
    MIN_WORDS = 25
    # Deliberate copies, each held to one wording by a test of its own (test_release_surface: the routing sentence).
    ALLOWED = ("aidd advises the minimum from the paths it touches and the author may declare higher",)
    GENERATED = re.compile(r"<!-- aidd:gen \S+ -->.*?<!-- aidd:end -->", re.S)

    def sentences(self, text: str):
        text = re.sub(r"```.*?```", " ", self.GENERATED.sub(" ", text), flags=re.S)
        for chunk in re.split(r"\n|\|", text):
            for sentence in re.split(r"(?<=[.!?])\s+", chunk):
                words = re.findall(r"[\w'`./-]+", sentence.lower())
                if len(words) >= self.MIN_WORDS:
                    yield " ".join(w.strip("`") for w in words)

    def test_no_long_sentence_is_copied_between_pages(self):
        pages = [ROOT / p for p in self.PAGES] + sorted((ROOT / "docs").glob("*.md"))
        seen: dict[str, set[str]] = {}
        for page in pages:
            for sentence in self.sentences(page.read_text(encoding="utf-8")):
                seen.setdefault(sentence, set()).add(str(page.relative_to(ROOT)))
        copied = {s: sorted(where) for s, where in seen.items() if len(where) > 1 and not any(a in s for a in self.ALLOWED)}
        self.assertEqual(copied, {}, "the same long sentence in two pages: keep it where the topic lives and link to it")

    def test_the_check_finds_a_copy_and_skips_generated_blocks(self):
        long = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one twenty-two twenty-three twenty-four twenty-five."
        self.assertEqual(len(list(self.sentences(f"Intro. {long} Outro."))), 1)
        self.assertEqual(list(self.sentences(f"<!-- aidd:gen roles -->\n{long}\n<!-- aidd:end -->")), [])


class TeamCommandPathTests(unittest.TestCase):
    """`aidd init --team` writes each team command as `.claude/commands/aidd-<name>.md`, which Claude Code runs as
    `/aidd-<name>`; the plugin's copy runs as `/aidd-team:<name>`. No page names a folder, such as
    `.claude/commands/aidd-team/`, that init never writes."""

    def test_the_docs_name_the_command_files_init_writes(self):
        from aidd.setup import team_install

        commands = [rel for rel in team_install.team_files([], True) if rel.startswith(".claude/commands/")]
        names = sorted((ROOT / "plugins" / "aidd-team" / "commands").glob("*.md"))
        self.assertTrue(names)
        self.assertEqual(sorted(commands), [f".claude/commands/{team_install.TEAM_PREFIX}{p.name}" for p in names])
        for page in ("docs/TEAM.md",):
            text = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertIn(f"`.claude/commands/{team_install.TEAM_PREFIX}<name>.md`", text)
                self.assertIn(f"`/{team_install.TEAM_PREFIX}<name>`", text)
                self.assertIn("`/aidd-team:<name>`", text)
        stale = [f for f in repo_files() if f.endswith(".md") and ".claude/commands/aidd-team" in (ROOT / f).read_text(encoding="utf-8")]
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
