"""The documentation holds together: every relative link and anchor resolves, and every path a status page names exists."""

import re
import unittest

from helpers import ROOT, repo_files

LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
ANCHOR_ID = re.compile(r'<a id="([^"]+)"')


def slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return re.sub(r"\s", "-", text)


def anchors(path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {slug(h) for h in HEADING.findall(text)} | set(ANCHOR_ID.findall(text))


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


if __name__ == "__main__":
    unittest.main()
