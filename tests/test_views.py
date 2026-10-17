"""The human views: the Spec approval page, the Merge approval page, and the verification report, rendered as one
self-contained HTML page each. A page is for a person deciding; it never approves, and the gate never reads it."""

import ast
import base64
import copy
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, modules_under, run_cli, source_of

from aidd.views import merge_approval
from aidd.views import spec_approval
from aidd.views import verification
from aidd.views import markdown_html
from aidd.views import html_parts
from aidd.evals import examples
from aidd.gate import decide

HOSTILE = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'

SPEC = """---
aidd_version: "1.0.0"
kind: spec
id: SPEC-7
title: 'Refunds {title}'
owner_team: payments
type: feat
route: normal
confidence: high
open_questions: []
trace_id: spec-7
assisted_by: []
rollback: 'Revert the PR; no data changes. {title}'
residual_risk: A refund just under the limit still needs one approver.

risk:
  summary: Refunds above 500 EUR wait for a second approver.
  dimensions: [financial]
  reversible: true

tasks:
  - id: SPEC-7-T1
    title: Hold large refunds
    scope: [src/refunds/]

tests:
  files: [tests/test_refunds.py]

  commands:
    - name: refunds
      command: [pytest, -q, tests/test_refunds.py]
      new_behavior: true
      covers: [A1, A2]

docs:
  - path: specs/SPEC-7/flow.md
---

## Intent

Finance: "a single agent approved a 4,000 EUR refund last week; that must take two people." {title}

## Acceptance

Scenario: A1 a refund above 500 EUR waits for a second approver {title}
Scenario: A2 a refund of 500 EUR or less completes as today
Scenario: A3 the audit log names both approvers
"""

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
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

_EXTERNAL = re.compile(r"""(?:src|href|action)\s*=\s*["']?\s*(?:[a-z][a-z0-9+.-]*:|//)""", re.I)
_CSP = re.compile(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">')


def spec_text(title: str = "over the limit need a second approver") -> str:
    return SPEC.format(title=title)


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
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        allowed = set(re.findall(r"'(sha256-[A-Za-z0-9+/=]+)'", csp))
        for body in scripts:
            digest = "sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode()
            if digest not in allowed:
                problems.append("a script the CSP does not pin")
        if "'unsafe-inline'" in csp.split("script-src", 1)[-1].split(";", 1)[0]:
            problems.append("scripts allowed inline")
    if len(re.findall(r"<script\b", page)) != len(re.findall(r"<script>", page)):
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
        out = html_parts.copyable("line", "/aidd approve-spec SPEC-7 abc")
        self.assertIn('<pre id="line"', out)
        self.assertIn("/aidd approve-spec SPEC-7 abc", out)
        button = re.search(r"<button\b[^>]*>", out).group(0)
        for want in ('type="button"', 'data-copy="line"', " hidden"):
            self.assertIn(want, button)


class SpecPageTests(unittest.TestCase):
    def render(self, title: str = HOSTILE) -> str:
        text = spec_text(title)
        files = {"specs/SPEC-7/flow.md": DOC.format(title=title), "tests/test_refunds.py": "assert False\n"}
        route = {"route": "normal", "lane": "spec", "reasons": [f"src/refunds/{title} matches payments"], "dimensions": ["financial"], "basis": "scope"}
        since = {"commit": "c" * 40, "stat": f" tests/{title} | 2 +-", "diff": f"--- a/x\n+++ b/x\n-old {title}\n+new {title}\n"}
        return spec_approval.spec_page(
            text, "specs/SPEC-7.md", "/aidd approve-spec SPEC-7 " + "a" * 32, files=files, route=route, since=since, spec_hash="a" * 32
        )

    def test_hostile_spec_text_is_escaped_everywhere(self):
        page = self.render()
        self.assertEqual(page_problems(page), [])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)

    def test_what_the_approver_reads(self):
        page = self.render("over the limit")
        for want in (
            "SPEC-7",
            "Finance:",
            "A1",
            "A3",
            "nothing covers it",
            "refunds",
            "financial",
            "Revert the PR",
            "specs/SPEC-7/flow.md",
            "graph TD",
            "tests/test_refunds.py",
            "/aidd approve-spec SPEC-7 " + "a" * 32,
            "Changed since the last approval",
            "This page never approves",
        ):
            self.assertIn(want, page)
        self.assertIn("<details", page)
        self.assertEqual(page, self.render("over the limit"))


class MergePageTests(unittest.TestCase):
    def setUp(self):
        self.ctx, _ = examples.load_example(ROOT / "examples" / "02-normal-feature")

    def test_the_worked_example(self):
        ctx = copy.deepcopy(self.ctx)
        d = decide(copy.deepcopy(ctx))
        page = merge_approval.merge_page(ctx, d)
        self.assertEqual(page_problems(page), [])
        for want in ("PASS", "SPEC-220", "src/checkout/rate_limit/limiter.py", "rate-limit", "every gate holds", "a1a1a1a1a1a1", "Scope and budget"):
            self.assertIn(want, page)

    def test_hostile_names_findings_reviews_and_diffs_are_escaped(self):
        ctx = copy.deepcopy(self.ctx)
        ctx["files"].append({"path": f"src/other/{HOSTILE}.py", "previous_path": None, "additions": 3, "deletions": 0})
        ctx["head_tree"][f"src/other/{HOSTILE}.py"] = "9" * 40
        ctx["comments"].append({"user": HOSTILE, "body": f"## Review\n\n- **Critical**: {HOSTILE}\n- Nit: {HOSTILE}\n"})
        ctx["evidence"]["results"][0]["name"] = HOSTILE
        d = decide(copy.deepcopy(ctx))
        self.assertEqual(d.decision, "fail")  # the hostile path is outside the scope
        page = merge_approval.merge_page(ctx, d, diffs={f"src/other/{HOSTILE}.py": f"+{HOSTILE}\n-{HOSTILE}\n"})
        self.assertEqual(page_problems(page), [])
        self.assertIn("Critical", page)
        self.assertIn("Nit", page)
        self.assertIn('class="add"', page)
        self.assertIn("FAIL", page)

    def test_findings_are_grouped_by_level_with_their_fixes(self):
        ctx = copy.deepcopy(self.ctx)
        ctx["reviews"] = []
        d = decide(copy.deepcopy(ctx))
        page = merge_approval.merge_page(ctx, d)
        self.assertIn("Pending", page)
        self.assertIn("merge_approval", page)
        self.assertIn("Fix:", page)


class VerificationPageTests(unittest.TestCase):
    """The verification on the Merge approval page: each Acceptance item, its commands and results, and what the verifier
    recorded for the head, read from `<evidence>/preview/<head>/artifacts.json`."""

    HEAD = "a" * 40

    def evidence(self) -> dict:
        return {
            "aidd_version": "1.0.0",
            "head_sha": self.HEAD,
            "base_sha": "b" * 40,
            "results": [
                {"name": "refunds", "command": ["pytest", "-q"], "red_green": "green", "status": "passed", "exit": 0, "source": "spec"},
                {"name": "refunds", "command": ["pytest", "-q"], "red_green": "red", "status": "failed", "exit": 1, "source": "spec"},
            ],
        }

    def recorded(self, out: Path, sha: str, path: str | None = None) -> None:
        folder = out / "preview" / self.HEAD
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a1-refund.png").write_bytes(PNG)
        items = [{"path": path or f"preview/{self.HEAD}/a1-refund.png", "kind": "screenshot", "sha256": sha}]
        (folder / "artifacts.json").write_text(json.dumps(items), encoding="utf-8")

    def page(self, ev: dict, text: str | None, out: Path | None) -> str:
        data, body = verification.spec_parts(text, "specs/SPEC-7.md")
        return html_parts.page("Verification", [html_parts.Section("verification", "Verification", verification.verification_section(ev, data, body, out))])

    def test_each_acceptance_item_to_commands_results_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.recorded(out, hashlib.sha256(PNG).hexdigest())
            page = self.page(self.evidence(), spec_text(), out)
        self.assertEqual(page_problems(page), [])
        self.assertIn("data:image/png;base64," + base64.b64encode(PNG).decode(), page)
        for want in ("A1", "A2", "A3", "nothing covers it", "fails on base", "passed", self.HEAD, "a1-refund.png"):
            self.assertIn(want, page)

    def test_an_artifact_is_embedded_only_when_its_hash_matches_and_it_stays_in_the_evidence_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ev"
            (Path(tmp) / "outside.png").write_bytes(PNG)
            self.recorded(out, "0" * 64)
            wrong = self.page(self.evidence(), None, out)
            self.recorded(out, hashlib.sha256(PNG).hexdigest(), "../outside.png")
            escaped = self.page(self.evidence(), None, out)
        self.assertNotIn("data:image/png", wrong)
        self.assertIn("does not match", wrong)
        self.assertNotIn("data:image/png", escaped)

    def test_hostile_evidence_is_escaped(self):
        ev = self.evidence()
        ev["results"][0]["name"] = HOSTILE
        ev["results"][0]["command"] = ["sh", "-c", HOSTILE]
        ev["runner"] = {"ci": "github", "run_id": "1", "url": f"javascript:{HOSTILE}"}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.recorded(out, "0" * 64, f"preview/{HOSTILE}.png")
            page = self.page(ev, spec_text(HOSTILE), out)
        self.assertEqual(page_problems(page), [])


class GuardrailTests(unittest.TestCase):
    def test_the_gate_never_reads_a_view(self):
        """No module the decision is computed in imports the renderer, and nothing there reads an .html file."""
        for name in (
            "aidd.gate",
            *modules_under("aidd.gate.rules"),
            "aidd.gate.routing",
            "aidd.workitems.approval_ledger",
            "aidd.platforms.local_context",
            "aidd.gate.inputs",
            "aidd.workitems.spec_file",
            "aidd.config",
            "aidd.gate.policy",
            "aidd.gate.change_record",
        ):
            source = source_of(name)
            tree = ast.parse(source)
            imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names} | {
                a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
            }
            imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertFalse({m for m in imported if m == "views" or m.startswith("aidd.views")}, name)
            self.assertNotIn(".html", source, name)


@unittest.skipUnless(shutil.which("git"), "git is required")
class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = root = Path(self.tmp.name).resolve()
        git(root, "init", "-q", "-b", "main")
        (root / "specs").mkdir()
        (root / "specs/SPEC-7.md").write_text(spec_text(HOSTILE), encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests/test_refunds.py").write_text("assert False\n", encoding="utf-8")
        (root / "specs/SPEC-7").mkdir(parents=True)
        (root / "specs/SPEC-7/flow.md").write_text(DOC.format(title=HOSTILE), encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "Spec")
        cwd = os.getcwd()
        os.chdir(root)
        self.addCleanup(os.chdir, cwd)

    def test_hash_html_writes_the_spec_page_and_keeps_stdout(self):
        code, plain = run_cli("hash", "specs/SPEC-7.md", "--line", "--summary")
        code2, out = run_cli("hash", "specs/SPEC-7.md", "--line", "--summary", "--html")
        self.assertEqual((code, code2), (0, 0))
        page_path = self.root / ".aidd/views/spec-SPEC-7.html"
        self.assertTrue(page_path.is_file(), out)
        page = page_path.read_text(encoding="utf-8")
        self.assertEqual(page_problems(page), [])
        line = plain.strip().splitlines()[-1]
        self.assertIn(line, page)
        self.assertIn(plain.strip(), out)
        code3, _ = run_cli("hash", "specs/SPEC-7.md", "--line", "--html", "--out", "elsewhere/p.html")
        self.assertEqual(code3, 0)
        self.assertEqual((self.root / "elsewhere/p.html").read_text(encoding="utf-8"), page)

    def test_hash_html_shows_what_changed_since_the_last_local_approval(self):
        from aidd.workitems import approval_ledger

        _, first = run_cli("hash", "specs/SPEC-7.md", "--line")
        approval_ledger.record_local_approval(first.strip())
        (self.root / "tests/test_refunds.py").write_text("assert 1 == 2\n", encoding="utf-8")
        git(self.root, "commit", "-qam", "tighten")
        code, _ = run_cli("hash", "specs/SPEC-7.md", "--line", "--html")
        self.assertEqual(code, 0)
        page = (self.root / ".aidd/views/spec-SPEC-7.html").read_text(encoding="utf-8")
        self.assertIn("Changed since the last approval", page)
        self.assertIn("assert 1 == 2", page)

    def test_gate_html_from_a_context_and_the_decision_is_the_same(self):
        ctx, _ = examples.load_example(ROOT / "examples" / "02-normal-feature")
        (self.root / "ctx.json").write_text(json.dumps(ctx), encoding="utf-8")
        code, plain = run_cli("gate", "--context", "ctx.json", "--json")
        code2, with_html = run_cli("gate", "--context", "ctx.json", "--json", "--html", "out/merge.html")
        self.assertEqual((code, code2), (0, 0))
        # The page's path goes to stderr: with --json, stdout holds the decision record and nothing else.
        self.assertEqual(plain, "".join(ln for ln in with_html.splitlines(keepends=True) if not ln.startswith("wrote ")))
        page = (self.root / "out/merge.html").read_text(encoding="utf-8")
        self.assertEqual(page_problems(page), [])
        self.assertIn("PASS", page)


if __name__ == "__main__":
    unittest.main()
