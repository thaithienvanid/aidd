"""The prototype: one self-contained HTML file per Spec or flow (`aidd new design-spec --prototype`) with every screen of it, a
screen menu, navigation with history, platform chrome, and deep links that restore a screen, state, theme, frame, and
mode; its feedback notes name the screen; `aidd explore` pairs rounds by screen id. A prototype is interactive; a
mockup is a static picture, and wireframe is one of the prototype's modes.
"""

import contextlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, make_repo, run_cli
from test_explorations import write_folder

from aidd.cli import app
from aidd.views import exploration_page

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
PROTO = ASSETS / "prototype.html"
TEAM = ROOT / "plugins" / "aidd-team"
PROTOTYPING = TEAM / "skills" / "prototyping"
STATES = ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run")
FRAMES = ("320", "768", "1024", "1440", "ios", "android")
# The old names, built so this file does not match its own search.
OLD = ("ui-" + "mock", "--" + "mock", 'data-testid="' + "mock-", "UI_" + "MOCK")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def script(ui: str) -> str:
    return ui.split("<script>", 1)[1].split("</script>", 1)[0]


def markup(ui: str) -> str:
    """The file without its HTML comments, which document the attributes they would otherwise seem to use."""
    return re.sub(r"<!--.*?-->", "", ui, flags=re.S)


def screens(ui: str) -> list[tuple[str, str, str]]:
    """Each `<section data-screen>` as (id, its opening tag, its body)."""
    out = []
    ui = markup(ui)
    for m in re.finditer(r"(<section\b[^>]*\bdata-screen=\"([^\"]*)\"[^>]*>)(.*?)</section>", ui, re.S):
        out.append((m.group(2), m.group(1), m.group(3)))
    return out


def states_in(body: str) -> list[str]:
    return re.findall(r"\bdata-state=\"([^\"]+)\"", body)


def function_body(js: str, name: str) -> str:
    start = js.index(f"function {name}(")
    depth, i = 0, js.index("{", start)
    for j in range(i, len(js)):
        depth += {"{": 1, "}": -1}.get(js[j], 0)
        if depth == 0:
            return js[i : j + 1]
    raise AssertionError(f"{name} has no end")


class RenameTests(unittest.TestCase):
    def test_the_file_has_its_new_name_and_hooks(self):
        self.assertTrue(PROTO.is_file())
        self.assertFalse((ASSETS / (OLD[0] + ".html")).exists())
        ui = read(PROTO)
        self.assertNotIn(OLD[2], ui)
        ids = set(re.findall(r'data-testid="(proto-[a-z0-9-]+)"', ui))
        want = {"proto-skip-link", "proto-spec-link", "proto-screens-toggle", "proto-screens-close"}
        want |= {f"proto-state-{s}" for s in STATES} | {f"proto-frame-{f}" for f in FRAMES}
        want |= {f"proto-theme-{t}" for t in ("system", "light", "dark")} | {"proto-mode-full", "proto-mode-wireframe"}
        want |= {f"proto-feedback-{f}" for f in ("toggle", "round", "copy-json", "copy-prompt", "target", "note", "add", "out")}
        self.assertEqual(want - ids, set())

    def test_no_old_name_remains_in_the_repository(self):
        tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
        found = []
        for rel in filter(None, tracked):
            p = ROOT / rel
            if not p.is_file() or p.suffix.lower() in {".png", ".jpg", ".gif", ".webp", ".ico", ".pyz", ".woff2"}:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found += [f"{rel}: {old}" for old in OLD if old in text]
        self.assertEqual(found, [])

    def test_the_cli_has_prototype_and_no_mock_flag(self):
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
            app.main(["new", "design-spec", "cart", "--spec", "SPEC-1", OLD[1]])
        self.assertIn(f"unknown option {OLD[1]}", err.getvalue())
        self.assertIn("--prototype", read(ROOT / "docs" / "CLI.md"))


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.ui = read(PROTO)
        self.screens = screens(self.ui)
        self.ids = [s for s, _, _ in self.screens]

    def test_three_or_more_screens_each_with_a_title_and_states(self):
        self.assertGreaterEqual(len(self.ids), 3)
        self.assertEqual(len(self.ids), len(set(self.ids)), "screen ids are unique")
        seen: set[str] = set()
        for ident, tag, body in self.screens:
            self.assertRegex(ident, r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "a screen id is a URL-safe slug")
            self.assertRegex(tag, r'data-title="[^"]+"', ident)
            found = states_in(body)
            self.assertTrue(found, f"{ident} has at least one state")
            self.assertEqual(len(found), len(set(found)), ident)
            self.assertEqual(set(found) - set(STATES), set(), ident)
            initial = re.search(r'data-initial="([^"]+)"', tag)
            if initial:
                self.assertIn(initial.group(1), found, ident)
            seen |= set(found)
        self.assertEqual(seen, set(STATES), "every state is shown on some screen")

    def test_every_data_go_names_a_screen_and_a_state_it_has(self):
        states = {ident: set(states_in(body)) for ident, _, body in self.screens}
        html = markup(self.ui)
        targets = re.findall(r'\bdata-go="([^"]*)"', html) + re.findall(r'\bdata-item-go="([^"]*)"', html)
        self.assertTrue(targets)
        for target in targets:
            screen, _, state = target.partition("/")
            self.assertIn(screen, states, target)
            if state:
                self.assertIn(state, states[screen], target)
        parents = re.findall(r'\bdata-parent="([^"]*)"', html)
        self.assertTrue(parents, "a child screen names its parent for the back affordance")
        for parent in parents:
            self.assertIn(parent, states)

    def test_the_screens_form_one_flow_from_the_first(self):
        edges = {ident: {t.split("/")[0] for t in re.findall(r'data-(?:item-)?go="([^"]*)"', body)} for ident, _, body in self.screens}
        reached, todo = {self.ids[0]}, [self.ids[0]]
        while todo:
            for nxt in edges.get(todo.pop(), set()) - reached:
                reached.add(nxt)
                todo.append(nxt)
        self.assertEqual(reached, set(self.ids), "each screen is reachable from the first by data-go")

    def test_realistic_content(self):
        main = self.ui.split('<main id="main"', 1)[1].split("</main>", 1)[0]
        self.assertNotRegex(main, r"(?i)lorem|ipsum|\bTODO\b")
        fixtures = json.loads(self.ui.split('<script type="application/json" id="fixtures">', 1)[1].split("</script>", 1)[0])
        self.assertNotRegex(json.dumps(fixtures), r"(?i)lorem|ipsum|\bTODO\b")
        items = next(v for v in fixtures.values() if isinstance(v, list))
        self.assertGreaterEqual(len(items), 3)
        self.assertTrue(any(len(str(i.get("name", ""))) >= 28 for i in items), "a long name to test wrapping at 320")

    def test_the_screen_menu_lists_every_screen(self):
        self.assertIn('id="screen-menu"', self.ui)
        js = script(self.ui)
        self.assertIn('querySelectorAll("section[data-screen]")', js, "the menu is built from the screens, so it lists all")
        build = function_body(js, "buildMenu")
        for want in ("dataset.go", '"proto-screen-"', "dataset.title"):
            self.assertIn(want, build, want)
        self.assertRegex(
            self.ui, r'<button[^>]*aria-controls="screen-menu"[^>]*aria-expanded="false"|<button[^>]*aria-expanded="false"[^>]*aria-controls="screen-menu"'
        )
        self.assertIn('"Escape"', js, "Escape closes the drawer")
        self.assertIn('matchMedia("(max-width: 767px)")', js, "a drawer on a narrow window as on a phone frame")
        self.assertIn('data-menu="drawer"', self.ui)

    def test_navigation_history_and_platform_chrome(self):
        js = script(self.ui)
        for want in ("history.pushState", "history.replaceState", "history.back()", '"popstate"', '"hashchange"', 'closest("[data-go]")'):
            self.assertIn(want, js, want)
        self.assertIn('data-testid="app-back"', self.ui)
        self.assertRegex(self.ui, r'<nav class="tabs"[^>]*>')
        tabs = self.ui.split('<nav class="tabs"', 1)[1].split("</nav>", 1)[0]
        self.assertGreaterEqual(len(re.findall(r"data-go=", tabs)), 2, "a tab bar has two or more tabs")
        for platform in ("web", "ios", "android"):
            self.assertIn(f'[data-platform="{platform}"]', self.ui, platform)
        self.assertIn("@container frame", self.ui, "the screens respond to the frame's width, not the window's")


class ModeTests(unittest.TestCase):
    """Every mode the one-screen file had is still there."""

    def test_every_mode_and_its_controls(self):
        ui = read(PROTO)
        for state in STATES:
            self.assertIn(f'data-show="{state}"', ui)
        for frame in FRAMES:
            self.assertIn(f'data-frame="{frame}"', ui)
        for theme in ("system", "light", "dark"):
            self.assertIn(f'data-theme-pick="{theme}"', ui)
        for mode in ("full", "wireframe"):
            self.assertIn(f'data-mode="{mode}"', ui)
        self.assertIn("data-feedback-toggle", ui)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", ui):
            self.assertIn("data-testid=", tag, tag)

    def test_one_self_contained_file_with_its_csp_and_no_markup_from_strings(self):
        ui = read(PROTO)
        self.assertEqual(ui.count("<html"), 1)
        self.assertNotRegex(ui, r"<(?:script|link|img|iframe)[^>]+(?:src|href)=\"https?://")
        self.assertNotRegex(ui, r"url\(\s*['\"]?https?://|@import")
        csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', ui)
        self.assertIsNotNone(csp, "a CSP meta keeps the file offline")
        assert csp is not None
        for want in ("default-src 'none'", "base-uri 'none'", "form-action 'none'"):
            self.assertIn(want, csp.group(1))
        self.assertNotRegex(csp.group(1), r"https?:|\*", "nothing remote is allowed")
        self.assertLess(ui.index("Content-Security-Policy"), ui.index("<style"), "the policy comes before any style or script")
        js = script(ui)
        self.assertNotRegex(js, r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function", "text only, never markup")
        self.assertNotRegex(js, r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket")


class DeepLinkTests(unittest.TestCase):
    def setUp(self):
        self.ui = read(PROTO)
        self.js = script(self.ui)

    def test_one_scheme_parsed_by_a_pure_function(self):
        parse = function_body(self.js, "parseLink")
        self.assertNotRegex(parse, r"\b(?:location|document|window|history)\b", "the parser reads only its arguments")
        for key in ('"theme"', '"frame"', '"mode"', '"round"'):
            self.assertIn(key, parse, key)
        link = function_body(self.js, "linkFor")
        self.assertNotRegex(link, r"\b(?:location|document|window|history)\b")
        self.assertIn("parseLink(location.hash, location.search)", self.js, "the page's query still works under the fragment")
        self.assertIn("#<screen>/<state>?theme=dark&frame=ios", self.ui, "the scheme is documented in the file")
        for old in ("?mode=wireframe", "?theme=dark", "?round=2"):
            self.assertIn(old, self.ui, old)

    def test_the_prototyping_skill_documents_the_scheme_and_the_screenshot_loop(self):
        text = read(PROTOTYPING / "SKILL.md")
        for want in (
            "prototype.html#<screen>/<state>?theme=dark&frame=ios",
            "<screen>-<state>-<target>-<theme>.png",
            "docs/design/index.md",
            "aidd new design-spec --prototype",
        ):
            self.assertIn(want, text, want)
        loop = read(PROTOTYPING / "references" / "prototype-screenshots.md")
        for want in (
            "for (const screen of",
            "for (const state of",
            "for (const theme of",
            "for (const frame of",
            "page.goto(",
            "#${screen}/${state}?theme=${theme}&frame=${frame}",
            "toHaveScreenshot",
            "emulateMedia",
            "section[data-screen]",
        ):
            self.assertIn(want, loop, want)
        self.assertIn("references/prototype-screenshots.md", text)

    def test_the_docs_use_the_terms(self):
        glossary = read(ROOT / "docs" / "GLOSSARY.md")
        for term in ("Prototype", "Mockup", "Wireframe mode", "Deep link"):
            self.assertRegex(glossary, rf"(?m)^\| {term} \|", term)
        mockup = next(line for line in glossary.splitlines() if line.startswith("| Mockup |"))
        self.assertIn("static", mockup)
        how = read(ROOT / "docs" / "HOW-TO.md")
        for want in ("aidd new design-spec", "--prototype", "docs/design/index.md", "#<screen>/<state>"):
            self.assertIn(want, how, want)
        self.assertIn("prototype.html#<screen>/<state>", read(ASSETS / "design-spec.md"))


class FeedbackTests(unittest.TestCase):
    def test_a_note_names_its_screen_and_its_link(self):
        js = script(read(PROTO))
        add = js.split('getElementById("feedback-add").addEventListener', 1)[1].split("});", 1)[0]
        for want in ("screen:", "state:", "frame:", "theme:", "testid:", "link:"):
            self.assertIn(want, add, want)
        text = function_body(js, "fbText")
        self.assertIn("screen:", text)
        self.assertIn("it.screen", text)

    def test_explore_names_the_screen_and_pairs_feedback_by_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = write_folder(Path(tmp), "split")
            data = json.loads(read(folder / "feedback-round-1.json"))
            data["items"].append({"id": "r1-3", "screen": "split", "state": "error", "testid": "split-retry", "note": "say what failed"})
            (folder / "feedback-round-1.json").write_text(json.dumps(data), encoding="utf-8")
            (folder / "rounds/2/split-error-320-light.png").write_bytes((folder / "rounds/1/split-error-320-light.png").read_bytes())
            page = exploration_page.comparison_page(folder)
        rounds = page.split('id="rounds"', 1)[1].split('id="choice"', 1)[0]
        pair = re.search(r"<details[^>]*><summary><code>split-error-320-light</code>.*?</details>", rounds, re.S)
        self.assertIsNotNone(pair)
        assert pair is not None
        self.assertIn("r1-3", pair.group(0), "the feedback on this screen and state sits beside its screenshots")
        self.assertIn("split/error", pair.group(0), "the item names its screen")


class NewPrototypeTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def test_it_writes_prototype_html_in_the_design_folder(self):
        code, out = run_cli("new", "design-spec", "checkout", "--spec", "SPEC-220", "--prototype")
        self.assertEqual(code, 0, out)
        path = self.root / "specs/SPEC-220/design/prototype.html"
        self.assertIn("specs/SPEC-220/design/prototype.html", out)
        text = read(path)
        self.assertIn('content="SPEC-220"', text)
        self.assertIn('"../../SPEC-220.md"', text, "the back-link to the Spec, beside its folder")
        self.assertNotIn("{{", text)
        spec = read(self.root / "specs/SPEC-220.md")
        self.assertIn("docs:\n  - kind: design-spec\n    path: specs/SPEC-220/design/prototype.html", spec)
        code, out = run_cli("new", "design-spec", "checkout", "--spec", "SPEC-220", "--prototype")
        self.assertNotEqual(code, 0)
        self.assertIn("exists", out)

    def test_a_flow_gets_its_own_folder(self):
        code, out = run_cli("new", "design-spec", "checkout", "--spec", "SPEC-220", "--prototype", "--area", "checkout")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "specs/SPEC-220/design/checkout/prototype.html").is_file())  # still in the Spec's folder

    def test_only_the_ui_doc_has_a_prototype(self):
        code, out = run_cli("new", "tech-spec", "checkout", "--spec", "SPEC-220", "--prototype")
        self.assertNotEqual(code, 0)
        self.assertIn("--prototype", out)


if __name__ == "__main__":
    unittest.main()
