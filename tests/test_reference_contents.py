"""A long reference an agent loads opens with its contents, as the Agent Skills guidance asks of a file over 100
lines: the agent sees what the file holds before it reads it all. The list is generated (`<!-- aidd:gen toc -->`)."""

from __future__ import annotations

import unittest

from helpers import ROOT

from aidd.docsgen import generate

LONG = 100
MARK = "<!-- aidd:gen toc -->"


class ReferenceContentsTests(unittest.TestCase):
    def test_every_long_reference_carries_its_contents(self):
        refs = sorted([*(ROOT / ".agents" / "skills").glob("*/references/*.md"), *(ROOT / "plugins").glob("*/skills/*/references/*.md")])
        self.assertTrue(refs)
        missing = [str(p.relative_to(ROOT)) for p in refs if p.read_text(encoding="utf-8").count("\n") > LONG and MARK not in p.read_text(encoding="utf-8")]
        self.assertEqual(missing, [], "add `**Contents**` and the toc block after the first paragraph")

    def test_the_list_links_each_section_heading(self):
        text = "# T\n\nIntro.\n\n## First `one`\n\nx\n\n```md\n## not a heading\n```\n\n## Second, part\n\n## First `one`\n"
        self.assertEqual(generate.contents(text), "- [First `one`](#first-one)\n- [Second, part](#second-part)\n- [First `one`](#first-one-1)")


if __name__ == "__main__":
    unittest.main()
