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


def page_problems(page: str) -> list[str]:
    """What a view must never hold: a hostile string unescaped, a script other than the pinned one, an external load,
    a form, a remote stylesheet, or a missing Content-Security-Policy."""
    problems = []
    if "<script>alert" in page or "<img src=x" in page:
        problems.append("hostile markup unescaped")
    m = _CSP.search(page)
    if not m:
        problems.append("no Content-Security-Policy meta")
    else:
        csp = html.unescape(m.group(1))
        for want in ("default-src 'none'", "style-src 'unsafe-inline'", "img-src data:", "form-action 'none'", "base-uri 'none'"):
            if want not in csp:
                problems.append(f"CSP lacks {want}")
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S | re.I)
        allowed = set(re.findall(r"'(sha256-[A-Za-z0-9+/=]+)'", csp))
        for body in scripts:
            digest = "sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
            if digest not in allowed:
                problems.append("a script the CSP does not pin")
        if "'unsafe-inline'" in csp.split("script-src", 1)[-1].split(";", 1)[0]:
            problems.append("scripts allowed inline")
    if len(re.findall(r"<script\b", page, re.I)) != len(re.findall(r"<script>", page, re.I)):
        problems.append("a script with attributes (src?)")
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
        for want in ('<html lang="en">', "<main", 'aria-label="On this page"', 'href="#main"', "prefers-color-scheme: dark", "@media print", ":focus-visible"):
            self.assertIn(want, page)
        self.assertIn('<a href="#two">Second</a>', page)

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

    def test_a_copy_button_is_progressive_and_the_text_stays_selectable(self):
        out = html_parts.copyable("line", "aidd test --spec specs/SPEC-7.md")
        self.assertIn('<pre id="line"', out)
        self.assertIn("aidd test --spec specs/SPEC-7.md", out)
        button = re.search(r"<button\b[^>]*>", out).group(0)
        for want in ('type="button"', 'data-copy="line"', " hidden"):
            self.assertIn(want, button)


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
