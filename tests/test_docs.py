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

    def test_the_enterprise_page_names_only_files_that_exist(self):
        text = (ROOT / "docs" / "ENTERPRISE.md").read_text(encoding="utf-8")
        for status in ("yes", "partial", "no"):
            self.assertIn(f"| {status} |", text)
        named = set(re.findall(r"`([\w./-]+/[\w.-]+\.(?:py|json|yml|toml|md))`", text)) | {t.partition("#")[0] for t in LINK.findall(text)}
        for rel in sorted(x for x in named if x and not x.startswith("http")):
            candidates = [(ROOT / "docs" / rel).resolve(), (ROOT / rel).resolve()]
            self.assertTrue(any(c.exists() for c in candidates), rel)

    def test_the_review_policy_names_only_modules_that_exist(self):
        # REVIEW.md's repository notes send reviewers to the gate's riskiest code: a stale name sends them nowhere.
        notes = (ROOT / "REVIEW.md").read_text(encoding="utf-8").partition("## Repository notes")[2]
        named = re.findall(r"`([\w./-]+\.py|[\w.-]+/)`", notes)
        self.assertGreaterEqual(len(named), 8, named)
        for rel in named:
            candidates = [ROOT / rel, ROOT / "src" / "aidd" / rel]
            self.assertTrue(any(c.exists() for c in candidates), f"REVIEW.md names {rel}, which does not exist")


class DuplicationTests(unittest.TestCase):
    """One owner per topic: a long sentence copied into a second page drifts from the first, so link to it instead."""

    PAGES = ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "GOVERNANCE.md", "SECURITY.md", "RELEASING.md", "REVIEW.md")
    PAGES += ("llms-install.md", "specs/README.md", "examples/README.md")
    MIN_WORDS = 25
    # Deliberate copies, each held to one wording by a test of its own (test_release_surface: the routing sentence).
    ALLOWED = ("aidd computes the minimum from what it touches the author may declare higher and the gate enforces the higher of the two",)
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
        for page in ("docs/INSTALL.md", "docs/TEAM.md"):
            text = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertIn(f"`.claude/commands/{team_install.TEAM_PREFIX}<name>.md`", text)
                self.assertIn(f"`/{team_install.TEAM_PREFIX}<name>`", text)
                self.assertIn("`/aidd-team:<name>`", text)
        stale = [f for f in repo_files() if f.endswith(".md") and ".claude/commands/aidd-team" in (ROOT / f).read_text(encoding="utf-8")]
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
