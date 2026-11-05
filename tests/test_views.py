"""The views: a page rendered as one self-contained HTML file. A page is for a person reading; it never approves,
and no module that computes advice reads it."""

import ast
import base64
import hashlib
import html
import re
import unittest

from helpers import modules_under, source_of

from aidd.views import markdown_html
from aidd.views import html_parts

HOSTILE = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'

DOC = """# Refund flow {title}

```mermaid
graph TD
  A[Refund {title}] --> B{{Over 500?}}
```

| Step | Who |
| --- | --- |
| hold | `system` {title} |
"""

# One PNG pixel: a real image, so the page can embed it.
_EXTERNAL = re.compile(r"""(?:src|href|action)\s*=\s*["']?\s*(?:[a-z][a-z0-9+.-]*:|//)""", re.I)
_CSP = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">')


def _pinned(csp: str, directive: str, blocks: list[str]) -> bool:
    """Whether the policy's `directive` names each block by its hash and allows nothing inline."""
    sources = csp.split(directive, 1)[-1].split(";", 1)[0]
    digests = {"'sha256-" + base64.b64encode(hashlib.sha256(b.encode("utf-8")).digest()).decode() + "'" for b in blocks}
    return "'unsafe-inline'" not in sources and all(d in sources.split() for d in digests)


def page_problems(page: str) -> list[str]:
    """What a view must never hold: a hostile string unescaped, a style or a script the policy does not pin by hash, a
    style attribute, an external load, a form, a remote stylesheet, or a missing Content-Security-Policy."""
    problems = []
    if "<script>alert" in page or "<img src=x" in page:
        problems.append("hostile markup unescaped")
    m = _CSP.search(page)
    if not m:
        problems.append("no Content-Security-Policy meta")
    else:
        csp = html.unescape(m.group(1))
        for want in ("default-src 'none'", "img-src data:", "form-action 'none'", "base-uri 'none'"):
            if want not in csp:
                problems.append(f"CSP lacks {want}")
        if not _pinned(csp, "style-src", re.findall(r"<style>(.*?)</style\s*>", page, re.S | re.I)):
            problems.append("a style the CSP does not pin, or styles allowed inline")
        if not _pinned(csp, "script-src", re.findall(r"<script>(.*?)</script\s*>", page, re.S | re.I)):
            problems.append("a script the CSP does not pin, or scripts allowed inline")
    if re.search(r"<[a-z][^>]*\sstyle=", page, re.I):
        problems.append("a style attribute, which the policy would block")
    for tag in ("script", "style"):  # a block with attributes, such as src or media, escapes the hashes above
        if len(re.findall(rf"<{tag}\b", page, re.I)) != len(re.findall(rf"<{tag}>", page, re.I)):
            problems.append(f"a {tag} with attributes")
    if _EXTERNAL.search(page.replace("data:image/", "")):
        problems.append("an external URL in src, href, or action")
    for bad in ("<form", "<iframe", "<object", "<embed", "<link", "@import", "<base"):
        if bad in page.lower():
            problems.append(f"{bad} present")
    for button in re.findall(r"<button\b[^>]*>", page):
        if 'type="button"' not in button:
            problems.append("a button that could submit")
    return problems


class RendererTests(unittest.TestCase):
    def test_the_page_is_self_contained_accessible_and_deterministic(self):
        sections = [
            html_parts.Section("one", "First", html_parts.el("p", HOSTILE)),
            html_parts.Section("two", "Second", markdown_html.md(DOC.format(title=HOSTILE))),
        ]
        page = html_parts.page(HOSTILE, sections, lead=HOSTILE)
        self.assertEqual(page_problems(page), [])
        self.assertEqual(page, html_parts.page(HOSTILE, sections, lead=HOSTILE))
        for want in ('<html lang="en">', "<main", 'aria-label="On this page"', 'href="#main"', "prefers-color-scheme: dark", ":focus-visible"):
            self.assertIn(want, page)
        self.assertIn('<a class="link" href="#two">Second</a>', page)
        self.assertIn(html_parts.page_style(""), page, "the design system's CSS, the status page's own")

    def test_the_lint_fails_a_style_or_a_script_the_policy_does_not_pin(self):
        page = html_parts.page("Title", [html_parts.Section("one", "First", html_parts.el("p", "x"))])
        self.assertEqual(page_problems(page), [])
        for extra in ('<style media="print">p{color:red}</style>', "<style>p{color:red}</style>", '<script src="x.js"></script>'):
            with self.subTest(extra=extra):
                self.assertNotEqual(page_problems(page.replace("</body>", extra + "</body>")), [])

    def test_markdown_escapes_and_shows_mermaid_as_its_source(self):
        out = markdown_html.md(DOC.format(title=HOSTILE))
        self.assertNotIn("<script>alert", out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", out)
        self.assertIn('class="diagram"', out)
        self.assertIn("graph TD", out)
        self.assertIn("<table", out)
        self.assertIn("<code>system</code>", out)

    def test_a_markdown_link_never_becomes_a_link(self):
        out = markdown_html.md("see [the docs](javascript:alert(1)) and [site](https://example.com)")
        self.assertNotIn("href", out)
        self.assertIn("the docs", out)

    def test_a_page_carries_its_note_its_style_its_counts_and_runs_no_script(self):
        sections = [html_parts.Section("one", "First", html_parts.el("p", "x"), count=3)]
        page = html_parts.page(HOSTILE, sections, note=HOSTILE, style=".mine{color:red}")
        self.assertEqual(page_problems(page), [])
        self.assertIn('<p class="muted prose">&lt;script&gt;', page)
        self.assertIn(".mine{color:red}</style>", page)
        self.assertEqual(page.count('<span class="count">3</span>'), 2, "the count shows in the table of contents and the heading")
        self.assertNotIn("<script", page, "the page only reads")
        self.assertIn("script-src 'none'", html.unescape(_CSP.search(page).group(1)))  # type: ignore[union-attr]


class AdviceTests(unittest.TestCase):
    def test_no_advice_module_reads_a_view(self):
        """No module that computes advice (risk, testing, config) imports the renderer, and nothing there reads an .html file."""
        for name in (*modules_under("aidd.risk"), *modules_under("aidd.testing"), "aidd.config", "aidd.workitems.spec_file"):
            source = source_of(name)
            tree = ast.parse(source)
            imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names} | {
                a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
            }
            imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertFalse({m for m in imported if m == "views" or m.startswith("aidd.views")}, name)
            self.assertNotIn(".html", source, name)


if __name__ == "__main__":
    unittest.main()


class WriteTests(unittest.TestCase):
    def test_a_page_is_never_written_through_a_link(self):
        """A committed link at the page or a folder on its way would aim the write at a file outside the repository."""
        import contextlib
        import os
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
            Path("outside").mkdir()
            Path("victim").write_text("mine", encoding="utf-8")
            Path(".aidd/views").mkdir(parents=True)
            try:
                os.symlink(os.path.abspath("victim"), ".aidd/views/status-work.html")
                os.symlink(os.path.abspath("outside"), ".aidd/linked")
            except OSError:
                self.skipTest("no symlinks here")
            html_parts.write(".aidd/views/status-work.html", "<p>page</p>")
            self.assertEqual(Path("victim").read_text(encoding="utf-8"), "mine")  # the link was replaced, not followed
            self.assertFalse(Path(".aidd/views/status-work.html").is_symlink())
            with self.assertRaisesRegex(ValueError, r"\.aidd/linked is a link"):
                html_parts.write(".aidd/linked/page.html", "<p>page</p>")
            self.assertEqual(list(Path("outside").iterdir()), [])
