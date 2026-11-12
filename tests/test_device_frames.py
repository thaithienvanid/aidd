"""The device table: one set of real viewport sizes, owned by the design system (`$extensions.aidd.device` in
src/aidd/views/design/tokens.json), that the prototype viewer draws, `aidd prototype --check` measures against, and
DESIGN.md lists.

The invariant: for every device frame a design names or draws, its size is a row of the table. A deep link names a frame
by id and never by a bare size. A frame a design draws has the table's width and height, in px, with a fixed height and
its own scroll. No shipped page, template, or tool states a device size the table does not hold. Each size has the public
source it was read from and the day, so a size nobody confirmed cannot enter the table.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import PROTOTYPE_TOOL, ROOT

from aidd.docsgen import generate
from aidd.kernel import resources
from aidd.views import design_tokens

pp = resources.team_tool("prototype")
checks = pp.design_checks
TABLE = checks.device_frames()
IDS = list(TABLE)
FRAME = '<div data-device="{id}" style="{style}"><button data-testid="go">Go</button></div>'
MARKUP = '<main><section data-screen="home" data-title="Home"><div data-state="success">{frame}</div></section></main>'


def drawn(ident: str, style: str) -> list[str]:
    """The problems the check finds for one frame a design draws itself, as their messages."""
    markup = MARKUP.format(frame=FRAME.format(id=ident, style=style))
    return [message for _, message in checks.device_problems(checks.read_design(markup, "d.html"))]


def exact(ident: str) -> str:
    frame = TABLE[ident]
    return f"width: {frame['width']}px; height: {frame['height']}px; overflow-y: auto"


class TableTests(unittest.TestCase):
    def test_the_table_is_the_design_systems_and_the_tool_holds_it_byte_for_byte(self):
        self.assertEqual((PROTOTYPE_TOOL / "devices.json").read_text(encoding="utf-8"), design_tokens.devices_json(), "run `aidd gen-docs`")
        self.assertEqual(set(TABLE), set(design_tokens.tokens()["$extensions"]["aidd"]["device"]["frames"]))

    def test_the_first_frame_is_the_phone_and_each_size_is_a_real_device_with_its_source(self):
        self.assertEqual((IDS[0], TABLE["ios"]["width"], TABLE["ios"]["height"]), ("ios", 390, 844))
        self.assertEqual((TABLE["android"]["width"], TABLE["android"]["height"]), (412, 915))
        for key, frame in TABLE.items():
            with self.subTest(frame=key):
                self.assertTrue(frame["devices"], "a size stands for named devices")
                self.assertTrue(frame["citation"]["url"].startswith("https://") and frame["citation"]["quote"].strip())
                self.assertRegex(frame["checked"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(0 < frame["width"] <= design_tokens.MAX_VIEWPORT and 0 < frame["height"] <= design_tokens.MAX_VIEWPORT)

    def test_a_phone_draws_only_the_system_bars_a_source_gives(self):
        # The viewer draws a phone's status bar and its bottom bar from the row, and the product clears them as its safe areas.
        rows = design_tokens.tokens()["$extensions"]["aidd"]["device"]["frames"]
        self.assertEqual({key for key, f in rows.items() if "safe_area" in f}, {key for key, f in rows.items() if f["platform"] in ("ios", "android")})
        for key, frame in rows.items():
            bars = frame.get("safe_area")
            if bars is None:
                continue
            with self.subTest(frame=key):
                for side in ("top", "bottom"):
                    self.assertTrue(isinstance(bars[side], int) and 0 < bars[side] < frame["height"] // 2, side)
                self.assertTrue(bars["citations"], "each bar has the page it was read from")
                for citation in bars["citations"]:
                    self.assertTrue(citation["url"].startswith("https://") and citation["quote"].strip())
                self.assertRegex(bars["checked"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertEqual(TABLE[key]["safe_area"]["top"], bars["top"], "the tool's copy is the table's")

    def test_a_size_in_the_table_keeps_the_ratio_of_a_device_not_the_360_by_576_that_started_this(self):
        # The first prototype drew a phone at 360 by 576 (1.6). Every phone frame is at or past 1.7, like the devices.
        for key in ("ios", "android", "320"):
            self.assertGreaterEqual(TABLE[key]["height"] / TABLE[key]["width"], 1.7, key)
        self.assertNotIn((360, 576), {(f["width"], f["height"]) for f in TABLE.values()})


class SourceGateTests(unittest.TestCase):
    """tokens.json refuses a frame with no source, no day, or a size that is no whole number of px."""

    def fails(self, edit, words: str) -> None:
        data = copy.deepcopy(json.loads(design_tokens.design_text("tokens.json")))
        edit(data["$extensions"]["aidd"]["device"]["frames"])
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tokens.json").write_text(json.dumps(data), encoding="utf-8")
            design_tokens.tokens.cache_clear()
            try:
                with (
                    mock.patch.object(design_tokens, "design_text", lambda name: (Path(d) / name).read_text(encoding="utf-8")),
                    self.assertRaisesRegex(ValueError, words),
                ):
                    design_tokens.tokens()
            finally:
                design_tokens.tokens.cache_clear()

    def test_a_frame_that_breaks_the_table_fails_with_where_and_what(self):
        cases = {  # edit -> the words the error names
            "no frame at all": (lambda f: f.clear(), "no frame"),
            "no source": (lambda f: f["ios"].pop("citation"), "device.frames.ios needs the source"),
            "a source with no quote": (lambda f: f["ios"]["citation"].update(quote=" "), "device.frames.ios needs the source"),
            "a source off https": (lambda f: f["ios"]["citation"].update(url="http://example.com/x"), "device.frames.ios needs the source"),
            "no day": (lambda f: f["ios"].pop("checked"), "device.frames.ios's checked"),
            "a day that is no date": (lambda f: f["ios"].update(checked="2026-13-01"), "device.frames.ios's checked"),
            "a size with a fraction": (lambda f: f["ios"].update(width=390.5), "device.frames.ios's width"),
            "a size of zero": (lambda f: f["ios"].update(height=0), "device.frames.ios's height"),
            "a size past the cap": (lambda f: f["ios"].update(height=design_tokens.MAX_VIEWPORT + 1), "device.frames.ios's height"),
            "a size given as text": (lambda f: f["ios"].update(width="390"), "device.frames.ios's width"),
            "a platform that is none": (lambda f: f["ios"].update(platform="tv"), "device.frames.ios's platform"),
            "no device named": (lambda f: f["ios"].update(devices=[]), "device.frames.ios needs a name"),
            "markup in a name": (lambda f: f["ios"].update(name="<b>iPhone</b>"), "device.frames.ios needs a name"),
            "a bad frame id": (lambda f: f.update({"Bad Id": f["ios"]}), "is not lower-case"),
        }
        for label, (edit, words) in cases.items():
            with self.subTest(label):
                self.fails(edit, words)

    def test_the_real_table_passes_the_gate(self):
        design_tokens.tokens.cache_clear()
        self.assertTrue(design_tokens.tokens()["$extensions"]["aidd"]["device"]["frames"])


class DrawnFrameTests(unittest.TestCase):
    """A frame a design draws itself (`data-device`) is measured against the table, in both directions."""

    def test_a_listed_size_with_a_fixed_height_that_scrolls_inside_passes(self):
        for ident in IDS:
            with self.subTest(frame=ident):
                self.assertEqual(drawn(ident, exact(ident)), [])
        self.assertEqual(drawn("ios", "height:844PX ; WIDTH: 390px;overflow:scroll;color:red"), [], "case, spacing, and `overflow` as a browser reads them")

    def test_an_invented_size_fails_and_names_the_table_size(self):
        for style in (
            "width: 360px; height: 576px; overflow-y: auto",
            "width: 390px; height: 576px; overflow-y: auto",
            "width: 391px; height: 844px; overflow-y: auto",
        ):
            with self.subTest(style=style):
                found = drawn("ios", style)
                self.assertEqual(len(found), 1, found)
                self.assertIn("width: 390px; height: 844px", found[0], "the next step is the style to write")

    def test_a_frame_with_no_fixed_height_fails_and_gives_the_style_to_write(self):
        cases = {
            "no height": "width: 390px; overflow-y: auto",
            "a minimum height only": "width: 390px; min-height: 844px; overflow-y: auto",
            "a height that follows its content": "width: 390px; height: auto; overflow-y: auto",
            "a height in vh": "width: 390px; height: 100vh; overflow-y: auto",
            "a height in percent": "width: 390px; height: 100%; overflow-y: auto",
            "no style": "",
        }
        for label, style in cases.items():
            with self.subTest(label):
                found = [m for m in drawn("ios", style) if "no fixed height" in m]
                self.assertEqual(len(found), 1, drawn("ios", style))
                self.assertIn("height: 844px; overflow-y: auto", found[0], "the next step is the style to write")

    def test_a_frame_with_no_width_in_px_or_no_scroll_fails_with_the_fix(self):
        self.assertIn("390px", " ".join(drawn("ios", "height: 844px; overflow-y: auto")))
        self.assertIn("390px", " ".join(drawn("ios", "width: 50%; height: 844px; overflow-y: auto")))
        found = drawn("ios", "width: 390px; height: 844px")
        self.assertEqual(len(found), 1)
        self.assertIn("does not scroll inside", found[0])
        self.assertIn("overflow-y: auto", found[0])
        self.assertIn("does not scroll inside", " ".join(drawn("ios", "width: 390px; height: 844px; overflow: visible")))
        # The later of overflow-y and the overflow shorthand wins, as in a browser, and the shorthand's last value is y.
        for style, scrolls in (
            ("width: 390px; height: 844px; overflow: hidden; overflow-y: auto", True),
            ("width: 390px; height: 844px; overflow-y: auto; overflow: hidden", False),
            ("width: 390px; height: 844px; overflow-y: auto; overflow-y: visible", False),
            ("width: 390px; height: 844px; overflow: hidden auto", True),
            ("width: 390px; height: 844px; overflow: auto hidden", False),
        ):
            with self.subTest(style=style):
                self.assertEqual(drawn("ios", style) == [], scrolls, drawn("ios", style))

    def test_a_frame_that_is_no_row_fails_whether_named_or_given_as_a_size(self):
        for ident in ("phone", "360", "iPhone", "", "ios "):
            with self.subTest(ident=ident):
                found = drawn(ident, "width: 360px; height: 576px; overflow-y: auto")
                self.assertEqual(len(found), 1, found)
                self.assertIn("no frame of the device table", found[0])
                self.assertIn("`ios` (390 by 844)", found[0], "the next step lists the frames and their sizes")

    def test_a_design_with_no_drawn_frame_has_nothing_to_measure(self):
        self.assertEqual(checks.device_problems(checks.read_design(MARKUP.format(frame="<p>Hi</p>"), "d.html")), [])


class FrameLinkTests(unittest.TestCase):
    """A deep link names a frame by id: a bare size is no frame."""

    def problem(self, link: str) -> list[str]:
        return [m for _, m, rule in checks._lint(f'<a href="{link}">x</a>') if rule == "device-frame"]

    def test_every_listed_frame_and_the_viewers_fill_passes(self):
        for ident in [*IDS, *checks.VIEWER_MODES]:
            for link in (f"#home/success?frame={ident}", f"#home/success?theme=dark&frame={ident}&zoom=actual", f"?frame={ident}"):
                with self.subTest(link=link):
                    self.assertEqual(self.problem(link), [])

    def test_a_bare_size_fails_and_a_width_a_frame_has_names_that_frame(self):
        for link, value in (("#home/success?frame=360", "360"), ("#home/success?theme=dark&frame=5000", "5000"), ("#home/success?frame=0", "0")):
            with self.subTest(link=link):
                found = self.problem(link)
                self.assertEqual(len(found), 1, found)
                self.assertIn(f"frame={value} is no frame of the device table", found[0])
                self.assertIn("`ios` (390 by 844)", found[0])
        self.assertIn("name frame=ios", self.problem("?frame=390")[0])
        self.assertIn("name frame=android", self.problem("?frame=412")[0])
        self.assertNotIn("is the width of", self.problem("?frame=360")[0])

    def test_a_name_that_is_no_frame_fails_with_the_list(self):
        for value in ("iphone", "tablet", "desktop-1280", "x"):
            with self.subTest(value=value):
                found = self.problem(f"?frame={value}")
                self.assertEqual(len(found), 1, found)
                self.assertIn("is no frame of the device table", found[0])
                self.assertIn("`desktop` (1280 by 800)", found[0])

    def test_text_that_only_looks_like_a_frame_link_is_left_alone(self):
        for text in ('<table frame="box">', "<table frame=box>", "?frame=", "?frame=<id>", "?frame={{frame}}", "a frame=360 without a link", "reframe=360"):
            with self.subTest(text=text):
                self.assertEqual([m for _, m, rule in checks._lint(text) if rule == "device-frame"], [])

    def test_a_frame_in_every_line_is_found_with_its_line_number(self):
        text = "ok\n#home/success?frame=ios\n#home/success?frame=360\n"
        self.assertEqual([n for n, _, rule in checks._lint(text) if rule == "device-frame"], [3])


class CheckCommandTests(unittest.TestCase):
    """`check` reports a device fault with the file and the line, beside the other rules, and an older design format only notes it."""

    def design(self, frame: str) -> tuple[str, str]:
        product = MARKUP.format(frame=frame)
        return f'<html data-aidd-prototype="1">\n<template id="product">\n{product}\n</template>\n</html>', product

    def test_a_drawn_frame_with_a_made_up_size_fails_the_design_and_a_listed_one_passes(self):
        text, product = self.design(FRAME.format(id="ios", style="width: 360px; height: 576px; overflow-y: auto"))
        problems, _ = checks.check(text, product, 3, "p.html")
        self.assertEqual(len(problems), 1, problems)
        self.assertTrue(problems[0].startswith("p.html:3: the frame `ios`"), problems)
        self.assertIn("drawn 360 by 576 px", problems[0])
        text, product = self.design(FRAME.format(id="ios", style=exact("ios")))
        self.assertEqual(checks.check(text, product, 3, "p.html")[0], [])

    def test_the_rule_is_a_family_at_the_tools_format_so_an_older_design_only_gets_a_note(self):
        self.assertEqual(checks.RULE_FORMATS["device-frame"], 1)
        text, product = self.design(FRAME.format(id="ios", style="width: 390px; overflow-y: auto"))
        original = checks.RULE_FORMATS
        checks.RULE_FORMATS = dict(original, **{"device-frame": 2})
        try:
            problems, ok = checks.check(text, product, 3, "p.html", 1)
        finally:
            checks.RULE_FORMATS = original
        self.assertEqual(problems, [])
        self.assertIn("note: p.html:3: format 2 would flag this", ok)

    def test_the_starting_design_and_the_showcase_pass_the_rule(self):
        for path in (PROTOTYPE_TOOL / "design.html", PROTOTYPE_TOOL / "examples" / "showcase.html"):
            text = path.read_text(encoding="utf-8")
            self.assertEqual([m for _, m, rule in checks._lint(text) if rule == "device-frame"], [], path.name)


class ToolReadsTheTableTests(unittest.TestCase):
    def test_the_viewer_holds_no_size_and_each_page_carries_the_table(self):
        viewer = (PROTOTYPE_TOOL / "viewer.html").read_text(encoding="utf-8")
        self.assertNotRegex(viewer, r"\b[wh]: [1-9]\d{2,3}\b|\d{3,4} by \d{3,4}", "the viewer draws its frames from the table")
        self.assertNotRegex(viewer, r"top: [1-9]\d*, bottom: [1-9]\d*", "a phone's system bars come from the table")
        status_bar = re.search(r"\.pv-status \{[^}]*\}", viewer)
        assert status_bar is not None
        self.assertNotRegex(status_bar.group(0), r"height: \d+px", "the status bar is as tall as the table's top bar")
        page = pp._in_viewer(pp._Page("", "{}", "{}", subtitle="s", note="n", title="t"))
        block = re.search(r'<script type="application/json" id="devices">\n(.*?)\n</script(?:[\s/][^>]*)?>', page, re.S)
        assert block is not None
        carried = json.loads(block.group(1))["frames"]
        self.assertEqual(
            {k: (f["width"], f["height"], f["platform"], f.get("safe_area")) for k, f in carried.items()},
            {k: (f["width"], f["height"], f["platform"], f.get("safe_area") and {s: f["safe_area"][s] for s in ("top", "bottom")}) for k, f in TABLE.items()},
        )
        self.assertNotIn("citation", block.group(1), "the page carries the sizes, not the sources")

    def test_the_table_is_missing_or_broken_the_tool_says_so(self):
        source = (PROTOTYPE_TOOL / "design_checks.py").read_text(encoding="utf-8")
        cases = {
            "missing": None,
            "not JSON": "{",
            "no frames": "{}",
            "a frame with a text width": json.dumps({"frames": {"a": {"name": "a", "platform": "web", "width": "1", "height": 2}}}),
            "a phone bar in text": json.dumps(
                {"frames": {"a": {"name": "a", "platform": "ios", "width": 390, "height": 844, "safe_area": {"top": "47", "bottom": 34}}}}
            ),
            "a phone bar taller than half the screen": json.dumps(
                {"frames": {"a": {"name": "a", "platform": "ios", "width": 390, "height": 844, "safe_area": {"top": 422, "bottom": 34}}}}
            ),
        }
        for label, content in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                (Path(d) / "design_checks.py").write_text(source, encoding="utf-8")
                if content is not None:
                    (Path(d) / "devices.json").write_text(content, encoding="utf-8")
                spec = importlib.util.spec_from_file_location(f"copy_{abs(hash(label))}", Path(d) / "design_checks.py")
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module  # as an import does: a dataclass in the module looks its own module up by name
                self.addCleanup(sys.modules.pop, spec.name, None)
                spec.loader.exec_module(module)
                with self.assertRaisesRegex((FileNotFoundError, ValueError), "devices.json"):
                    module.device_frames()

    def test_gen_docs_check_names_a_stale_table(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / generate.DEVICES_JSON).parent.mkdir(parents=True)
            (root / generate.DEVICES_JSON).write_text(design_tokens.devices_json().replace("390", "360"), encoding="utf-8")
            self.assertIn(root / generate.DEVICES_JSON, generate.gen_docs(root, check=True))
            (root / generate.DEVICES_JSON).write_text(design_tokens.devices_json(), encoding="utf-8")
            self.assertNotIn(root / generate.DEVICES_JSON, generate.gen_docs(root, check=True))


class NoSizeOutsideTheTableTests(unittest.TestCase):
    """The lists a person reads, and the templates they copy, hold only sizes of the table."""

    SUFFIXES = (".md", ".html", ".css", ".js", ".mjs", ".py", ".json", ".txt", ".yaml", ".yml")
    SKIP = ("CHANGELOG.md", "tokens.json", "devices.json", "package-lock.json")
    PAIR = re.compile(r"\b(\d{3,4})(?: by | ?[x×] ?)(\d{3,4})\b")
    LINK = re.compile(r"[?&]frame=(\d+)\b")

    def files(self):
        for top in ("docs", "plugins", ".agents", "templates", "src", "README.md", "llms.txt"):
            base = ROOT / top
            for path in [base] if base.is_file() else sorted(base.rglob("*")):
                if path.is_file() and path.suffix in self.SUFFIXES and path.name not in self.SKIP and "node_modules" not in path.parts:
                    yield path

    def test_a_shipped_page_template_or_tool_states_no_size_the_table_lacks(self):
        listed = {(f["width"], f["height"]) for f in TABLE.values()}
        broken = []
        for path in self.files():
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                for m in self.PAIR.finditer(line):
                    if (int(m.group(1)), int(m.group(2))) not in listed:
                        broken.append(f"{path.relative_to(ROOT)}:{number}: {m.group(0)}")
                for m in self.LINK.finditer(line):
                    if m.group(1) not in TABLE:
                        broken.append(f"{path.relative_to(ROOT)}:{number}: frame={m.group(1)}")
        self.assertEqual(broken, [], "name a frame of the device table (docs/design/DESIGN.md, Device frames), or add its row with its source")

    def test_the_scan_catches_what_it_is_for(self):
        listed = {(f["width"], f["height"]) for f in TABLE.values()}
        for text, want in (
            ("a phone of 360 by 576", True),
            ("a 390 by 844 phone", False),
            ("360x576", True),
            ("390 × 844", False),
            ("1440 by 900 screen", False),
            ("12 by 30", False),
        ):
            with self.subTest(text=text):
                found = [m for m in self.PAIR.finditer(text) if (int(m.group(1)), int(m.group(2))) not in listed]
                self.assertEqual(bool(found), want)


if __name__ == "__main__":
    unittest.main()
