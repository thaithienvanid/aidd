"""The code a skill's reference page asks a role to copy still works.

Two checks. Every fenced `python`, `js`, `ts`, `sh`, and `bash` block in a skill's pages parses, so a snippet that was
edited into a syntax error is caught. And the three functions the screenshot loop sends to a page run in a real browser
the way Playwright sends them: `locator.evaluate(fn)` ships the function's own source and runs it in the page, so a name
the function reads from the page that holds it is undefined there. Opt in to the browser check with
`AIDD_BROWSER_TESTS=1` (see `browser_driver.py`).

What these do not prove: that a block does what its prose says, that a `sh` block's commands exist, that a TypeScript block
type-checks, or that a function sent inline as `evaluate((e) => ...)` keeps to its own arguments.
"""

from __future__ import annotations

import ast
import atexit
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from collections.abc import Iterator
from pathlib import Path

from browser_driver import CHROME, ENABLED, finish, needs_chrome, start_browser
from helpers import ROOT, SUBPROCESS_TIMEOUT, repo_files

SESSION: dict = {}
SKILL_PAGE = re.compile(r"^(plugins/[^/]+|\.agents)/skills/.+\.md$")
FENCE = re.compile(r"^( *)```(python|js|ts|sh|bash)\n(.*?)^\1```$", re.S | re.M)
NODE = shutil.which("node")
# Node can strip a TypeScript block's types from v22.13, with `module.stripTypeScriptTypes`; the block then parses as JavaScript.
STRIP_TYPES = "process.stdout.write(require('node:module').stripTypeScriptTypes(require('fs').readFileSync(0, 'utf8')))"
NODE_READS_TYPESCRIPT = (
    bool(NODE)
    and subprocess.run(
        [NODE or "", "-p", "typeof require('node:module').stripTypeScriptTypes"], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT
    ).stdout.strip()
    == "function"
)
SCREENSHOTS = ROOT / "plugins/aidd-team/skills/prototyping/references/prototype-screenshots.md"


def blocks(pages: Iterator[tuple[str, str]] | None = None) -> Iterator[tuple[str, str, str]]:
    """Each fenced block of a skill page: its page, its language, and its code with the fence's indent removed."""
    for name, text in pages or ((f, (ROOT / f).read_text(encoding="utf-8")) for f in repo_files() if SKILL_PAGE.match(f)):
        for found in FENCE.finditer(text):
            yield name, found.group(2), textwrap.dedent(found.group(3))


def problem(language: str, code: str, folder: Path) -> str:
    """Why the block does not parse, or an empty string when it does or when no tool here can tell."""
    if language == "python":
        try:
            ast.parse(code)
        except SyntaxError as error:
            return str(error)
        return ""
    if language in ("sh", "bash"):
        return subprocess.run(["bash", "-n"], input=code, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT).stderr.strip()
    if not NODE or (language == "ts" and not NODE_READS_TYPESCRIPT):
        return ""
    if language == "ts":
        stripped = subprocess.run([NODE, "--no-warnings", "-e", STRIP_TYPES], input=code, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT)
        if stripped.returncode:
            return stripped.stderr.strip()
        code = stripped.stdout
    source = folder / "block.mjs"
    source.write_text(code, encoding="utf-8")
    return subprocess.run([NODE, "--check", str(source)], capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT).stderr.strip()


class ParseTests(unittest.TestCase):
    def test_every_block_of_a_skill_page_parses(self):
        found = list(blocks())
        self.assertEqual({"python", "js", "ts", "sh", "bash"} - {language for _, language, _ in found}, set(), "the scan sees every language it checks")
        with tempfile.TemporaryDirectory() as folder:
            for name, language, code in found:
                with self.subTest(page=name, language=language, starts=code.strip().splitlines()[0][:40]):
                    self.assertEqual(problem(language, code, Path(folder)), "")

    def test_a_block_that_does_not_parse_is_found(self):
        """The check itself, per language, with a good block and a broken one."""
        cases = (
            ("python", "x = [1, 2]\n", "def (:\n"),
            ("sh", "if true; then\n  echo hi\nfi\n", "if true; then\n  echo hi\n"),
            ("bash", "echo hi | cat\n", "echo (\n"),
            ("js", "const a = (x) => x + 1;\n", "const = ;\n"),
            ("ts", "const a = (x: number) => x + 1;\n", "const a = (x: number) => ;\n"),
        )
        with tempfile.TemporaryDirectory() as folder:
            for language, good, bad in cases:
                with self.subTest(language=language):
                    if language == "ts" and (not NODE or not NODE_READS_TYPESCRIPT):
                        continue
                    self.assertEqual(problem(language, good, Path(folder)), "")
                    self.assertNotEqual(problem(language, bad, Path(folder)), "")

    def test_the_scan_reads_an_indented_fence_and_ignores_other_languages(self):
        pages = iter([("a.md", "1. Step\n\n   ```sh\n   echo hi\n   ```\n\n```text\nnot code\n```\n")])
        self.assertEqual(list(blocks(pages)), [("a.md", "sh", "echo hi\n")])


def sent_to_a_page(code: str) -> dict[str, str]:
    """The functions a block sends to a page by name, `locator.evaluate(name)`, each with the source Playwright sends: the
    text on the right of its top-level `const name =`, up to the first line that ends in a semicolon with no indent, and
    nothing else the block holds."""
    lines, sent = code.splitlines(), {}
    for name in dict.fromkeys(re.findall(r"\.evaluate\((\w+)\)", code)):
        start = next((i for i, line in enumerate(lines) if line.startswith(f"const {name} = ")), None)
        if start is None:
            continue
        end = next(i for i in range(start, len(lines)) if lines[i].endswith(";") and (i == start or not lines[i].startswith(" ")))
        sent[name] = "\n".join([lines[start].removeprefix(f"const {name} = "), *lines[start + 1 : end + 1]]).removesuffix(";")
    return sent


PLAIN_PAGE = "<!doctype html><html><head><title>t</title></head><body><button>Pay</button><p>Hello</p></body></html>"
# A page whose size changes in every frame never settles.
GROWING_PAGE = "<!doctype html><title>t</title><body><div id=box style='height: 900px'></div><script>const box = document.getElementById('box'); let h = 900; (function grow() { box.style.height = (h += 5) + 'px'; requestAnimationFrame(grow); })();</script></body></html>"
# A short transition that ends by itself.
MOVING_PAGE = "<!doctype html><title>t</title><style>div { width: 10px; height: 10px; animation: move 150ms linear 1 forwards; } @keyframes move { to { transform: translateX(40px); } }</style><body><div></div></body></html>"


def setUpModule():
    if ENABLED:
        if not CHROME:
            raise AssertionError("AIDD_BROWSER_TESTS=1 asks for the code-block test, but no Chrome or Chromium was found: install one, or set CHROME_BIN to it")
        atexit.register(finish, SESSION)
        SESSION["browser"] = start_browser(SESSION)
        SESSION["page"] = SESSION["browser"].page()


@needs_chrome
class SentToAPageTests(unittest.TestCase):
    """Each function a skill page sends to a page runs there alone, as Playwright sends it: its source, evaluated in the
    page, with the page's own globals and nothing else from the block."""

    def run_alone(self, source: str, argument: str, page_html: str):
        page = SESSION["page"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "page.html"
            path.write_text(page_html, encoding="utf-8")
            page.open(path.as_uri(), (1280, 800))
        expression = f"(async () => {{ const sent = (0, eval)({json.dumps('(' + source + ')')}); return JSON.stringify((await sent({argument})) ?? null); }})()"
        return json.loads(page.js(expression, await_promise=True))

    def functions(self) -> dict[str, str]:
        sent: dict[str, str] = {}
        for name, language, code in blocks():
            if (ROOT / name) == SCREENSHOTS and language == "ts":
                sent.update(sent_to_a_page(code))
        return sent

    def test_every_function_the_screenshot_page_sends_has_a_case_here(self):
        self.assertEqual(sorted(self.functions()), ["hiddenStep", "misplaced", "settled"], "a function sent by name needs a case below")

    def test_the_settle_wait_runs_alone_and_returns_on_a_page_that_holds_still(self):
        self.assertIsNone(self.run_alone(self.functions()["settled"], "document.documentElement", PLAIN_PAGE))

    def test_the_settle_wait_holds_until_an_animation_with_an_end_is_done(self):
        source = self.functions()["settled"]
        self.assertIsNone(self.run_alone(source, "document.documentElement", MOVING_PAGE))
        self.assertEqual(SESSION["page"].js("document.getAnimations().filter((a) => a.playState === 'running').length"), 0)

    def test_the_settle_wait_fails_on_a_layout_that_never_settles(self):
        with self.assertRaisesRegex(AssertionError, "did not settle in 30 frames"):
            self.run_alone(self.functions()["settled"], "document.documentElement", GROWING_PAGE)

    def test_the_cover_check_runs_alone_and_finds_nothing_on_a_plain_page(self):
        self.assertEqual(self.run_alone(self.functions()["misplaced"], "document.documentElement", PLAIN_PAGE), [])

    def test_the_next_step_check_runs_alone_and_finds_a_visible_button_in_place(self):
        self.assertIsNone(self.run_alone(self.functions()["hiddenStep"], "document.querySelector('button')", PLAIN_PAGE))


if __name__ == "__main__":
    unittest.main()
