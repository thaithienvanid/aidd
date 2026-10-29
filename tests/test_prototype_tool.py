"""aidd-team's prototype tool on its own: the component contract, the Storybook check, the design format, where pages
go, the command line run without aidd, and how aidd loads it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import PROTOTYPE_TOOL, adopted_repo, git, run_cli

from aidd.kernel import resources

pp = resources.team_tool("prototype")
TOOL = PROTOTYPE_TOOL / "prototype.py"


def tool(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """The tool as a person runs it with aidd-team alone: its own file, no aidd on the path (`-I`)."""
    return subprocess.run([sys.executable, "-I", str(TOOL), *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=60)


def product(root: Path) -> Path:
    pp.new_product_prototype(root, product="Field Notes")
    return root / "docs" / pp.APP


class ContractTests(unittest.TestCase):
    def test_each_component_its_variants_screens_and_test_ids(self):
        markup = (
            '<div class="device"><nav class="tabs"><button data-component="tab" data-testid="tab-a">A</button></nav>'
            '<section data-screen="a"><div data-state="success"><input/><br/>'
            '<button data-component="button" data-variant="primary" data-testid="a-go">Go</button></div></section>'
            '<p data-component="footer">after the screens</p></div>'
        )
        contract = pp.component_contract([markup])
        self.assertEqual(contract["format"], pp.FORMAT)
        by_name = {c["name"]: c for c in contract["components"]}
        self.assertEqual(by_name["button"], {"name": "button", "variants": ["primary"], "screens": ["a"], "testids": ["a-go"]})
        self.assertEqual(by_name["tab"]["screens"], [])  # the chrome, on every screen
        self.assertEqual(by_name["footer"]["screens"], [], "a self-closing tag never shifts what follows into a screen")
        self.assertEqual(by_name["footer"]["variants"], ["default"])

    def test_no_contract_from_a_design_with_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = product(root)
            contract, problems = pp.contract_of(root, None)
            self.assertIsNotNone(contract)
            self.assertEqual(problems, [])
            (app / "shell.html").unlink()
            contract, problems = pp.contract_of(root, None)
            self.assertIsNone(contract)
            self.assertIn("a contract is read only from a design with no problem", problems[-1])
            design = root / "a.html"
            design.write_text(
                (PROTOTYPE_TOOL / "design.html").read_text(encoding="utf-8").replace('data-component="app-bar"', 'data-component="AppBar"', 1), encoding="utf-8"
            )
            contract, problems = pp.contract_of(root, "a.html")
            self.assertIsNone(contract)
            self.assertTrue(any("names a component 'AppBar'" in p for p in problems), problems)


class StateNameTests(unittest.TestCase):
    def test_a_screens_own_state_is_fine_and_a_typo_of_a_core_one_is_flagged(self):
        self.assertEqual(pp._state_problems("a.html", "search", "no-results"), [])
        self.assertIn("did you mean `permission-denied`", pp._state_problems("a.html", "x", "permision-denied")[0])
        self.assertIn("lowercase words joined by hyphens", pp._state_problems("a.html", "x", "Loading Now")[0])
        self.assertEqual([s for s in pp.CORE_STATES if pp._state_problems("a.html", "x", s)], [])


class StoriesTests(unittest.TestCase):
    CONTRACT = {"components": [{"name": "note-card", "variants": ["compact"]}, {"name": "card", "variants": ["compact"]}]}

    def test_a_story_matches_by_its_title_and_name_never_by_a_longer_title(self):
        index = {
            "v": 5,
            "entries": {
                "components-notecard--compact": {"type": "story", "id": "components-notecard--compact", "title": "Components/NoteCard", "name": "Compact"}
            },
        }
        stories = pp.stories_of(index)
        self.assertEqual(stories, {("note-card", "compact")})
        missing = pp.missing_stories(self.CONTRACT, stories)
        self.assertEqual(len(missing), 1)
        self.assertIn("component `card` has no story for its `compact` variant", missing[0])  # NoteCard is no card

    def test_every_index_shape(self):
        self.assertEqual(pp.stories_of({"stories": {"ui-card--compact": {"id": "ui-card--compact"}}}), {("ui-card", "compact")})
        docs = {"entries": {"x--docs": {"type": "docs", "id": "x--docs", "title": "X", "name": "Docs"}}}
        self.assertEqual(pp.stories_of(docs), set())  # a docs page is no story
        for bad in ([], {"entries": []}):
            with self.subTest(index=bad), self.assertRaises(ValueError):
                pp.stories_of(bad)

    def test_the_command_fails_on_a_missing_story_and_on_an_index_it_cannot_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product(root)
            index = root / "index.json"
            index.write_text(json.dumps({"entries": {}}), encoding="utf-8")
            done = tool(root, "stories", "index.json")
            self.assertEqual(done.returncode, 1, done.stdout)
            self.assertIn("component `app-bar` has no story", done.stdout)
            index.write_text("[]", encoding="utf-8")
            done = tool(root, "stories", "index.json")
            self.assertEqual(done.returncode, 1)
            self.assertIn("cannot be read (it holds no JSON object)", done.stdout)


class FeedbackRoundTests(unittest.TestCase):
    """The tool reads the earlier rounds beside a design for the viewer: each item done once a later round's
    changes.json answers it (R231). A file of another shape is reported, never a crash."""

    def write(self, folder: Path, rel: str, data) -> None:
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def test_an_item_is_done_once_a_later_round_answers_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            items = [
                {"id": "r1-1", "kind": "remove", "screen": "home", "state": "empty", "testid": "home-x", "note": "Remove this."},
                {"id": "r1-2", "kind": "odd", "screen": "home", "state": "empty", "testid": "home-y", "note": "x" * 900},
                {"id": "r1-3", "screen": "home", "state": "error", "testid": "home-z", "note": "Say what failed."},
                "not an item",
            ]
            self.write(folder, "feedback-round-1.json", {"round": 1, "items": items})
            self.write(folder, "feedback-round-x.json", {})  # no round number: left out
            self.write(folder, "rounds/1/changes.json", {"changes": [{"answers": ["r1-3"]}]})
            self.write(folder, "rounds/2/changes.json", {"changes": [{"answers": ["r1-1", 7]}]})
            self.write(folder, "feedback-round-2.json", "not json")
            rounds, problems = pp.feedback_rounds(folder)
        self.assertEqual([r["round"] for r in rounds], [1, 2])
        first = {it["id"]: it for it in rounds[0]["items"]}
        self.assertTrue(first["r1-1"]["done"])
        self.assertFalse(first["r1-3"]["done"], "round 1's own changes.json answers nothing of round 1")
        self.assertEqual(first["r1-2"]["kind"], "change")  # an unknown kind reads as change
        self.assertEqual(len(first["r1-2"]["note"]), pp.MAX_TEXT)
        self.assertEqual(rounds[1]["items"], [])
        self.assertTrue(any(p.startswith("feedback-round-2.json: not JSON") for p in problems), problems)

    def test_a_file_of_another_shape_is_reported_never_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.write(folder, "feedback-round-1.json", {"items": {"r1-1": "an object, not a list"}})
            self.write(folder, "feedback-round-2.json", {"items": 5})
            self.write(folder, "feedback-round-3.json", {"items": []})
            self.write(folder, "feedback-round-03.json", {"items": []})  # round 3 again
            self.write(folder, "feedback-round-4.json", [1, 2])
            self.write(folder, "rounds/4/changes.json", {"changes": 5})
            self.write(folder, "rounds/5/changes.json", {"changes": [{"answers": "r1-1"}]})
            self.write(folder, "rounds/²/changes.json", {"changes": []})  # a digit Python reads, never a round
            self.write(folder, "rounds/6/changes.json", "[" * 5000)
            rounds, problems = pp.feedback_rounds(folder)
        self.assertEqual([r["round"] for r in rounds], [1, 2, 3, 4])
        self.assertTrue(all(r["items"] == [] for r in rounds))
        text = "\n".join(problems)
        for want in (
            "`items` is not a list",
            "not a JSON object",
            "round 3 has another file",
            "`changes` is not a list",
            "`answers` is not a list",
            "rounds/6/changes.json: not JSON",
        ):
            self.assertIn(want, text, want)

    def test_only_plain_files_in_the_folder_are_read(self):
        """A link out of the design folder, a special file, a file past the cap, and a nested value are left out, never
        read whole or followed (security F2, F3)."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            folder = Path(tmp)
            outside = Path(away) / "secret.json"
            outside.write_text(json.dumps({"items": [{"id": "r1-1", "note": "OUTSIDE"}]}), encoding="utf-8")
            (folder / "feedback-round-1.json").symlink_to(outside)
            os.mkfifo(folder / "feedback-round-2.json")
            self.write(folder, "feedback-round-3.json", " " * (pp.MAX_FILE_BYTES + 1))
            self.write(folder, "feedback-round-4.json", {"items": [{"id": "r4-1", "note": {"deep": [[[1]]]}, "screen": ["x"]}]})
            (folder / "rounds").mkdir()
            (Path(away) / "changes.json").write_text(json.dumps({"changes": [{"answers": ["r4-1"]}]}), encoding="utf-8")
            (folder / "rounds" / "5").symlink_to(Path(away), target_is_directory=True)
            rounds, problems = pp.feedback_rounds(folder)
        notes = [it["note"] for r in rounds for it in r["items"]]
        self.assertNotIn("OUTSIDE", notes)
        self.assertEqual(rounds[-1]["items"], [{"id": "r4-1", "screen": "", "state": "", "testid": "", "note": "", "kind": "change", "done": False}])
        text = "\\n".join(problems)
        self.assertIn("feedback-round-1.json: not a plain file", text)
        self.assertIn("feedback-round-2.json: not a plain file", text)
        self.assertIn("feedback-round-3.json: larger than", text)
        self.assertIn("rounds/5/changes.json: not a plain file", text)

    def test_the_newest_rounds_are_kept_and_the_total_is_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for n in range(1, pp.MAX_ROUNDS + 3):
                self.write(folder, f"feedback-round-{n}.json", {"items": [{"id": f"r{n}-1", "note": "n"}]})
            rounds, _ = pp.feedback_rounds(folder)
            self.assertEqual(rounds[-1]["round"], pp.MAX_ROUNDS + 2)
            self.assertEqual(len(rounds), pp.MAX_ROUNDS)
            big = [{"id": f"r1-{i}", "note": "x" * pp.MAX_TEXT} for i in range(pp.MAX_ITEMS)]
            for n in range(1, pp.MAX_ROUNDS + 3):
                self.write(folder, f"feedback-round-{n}.json", {"items": big})
            rounds, problems = pp.feedback_rounds(folder)
        size = sum(len(it["note"]) for r in rounds for it in r["items"])
        self.assertLessEqual(size, pp.MAX_TOTAL)
        self.assertTrue(any("more than" in p for p in problems))

    def test_the_view_carries_the_rounds_and_a_note_stays_text(self):
        hostile = "</script><img src=x onerror=alert(1)>"
        with adopted_repo() as root:
            design = root / "specs" / "SPEC-9" / "design"
            design.mkdir(parents=True)
            (design / "prototype.html").write_text((PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8"), encoding="utf-8")
            self.write(design, "feedback-round-1.json", {"round": 1, "items": [{"id": "r1-1", "note": hostile}]})
            self.write(design, "rounds/2/changes.json", {"changes": "not a list"})
            page, problems = pp.view_prototype_file(root, "specs/SPEC-9/design/prototype.html")
            self.assertEqual(problems, [])
            assert page is not None
            block = page.read_text(encoding="utf-8").split('id="viewer-config">', 1)[1].split("</script>", 1)[0]
            _, checked = pp.view_prototype_file(root, "specs/SPEC-9/design/prototype.html", write=False)
        self.assertNotIn("<", block, "a note reaches the page only as escaped JSON")
        config = json.loads(block)
        self.assertEqual(config["rounds"][0]["items"][0]["note"], hostile)
        self.assertTrue(config["round_problems"])
        # The tool names the design by its own path, for the prompt the viewer writes. The notes are still kept by the page's path.
        self.assertEqual(config["design"], "specs/SPEC-9/design/prototype.html")
        self.assertEqual(checked, [], "a check never reads the feedback files")

    def test_the_product_prototype_carries_its_rounds(self):
        with adopted_repo() as root:
            app = product(root)
            self.write(app, "feedback-round-1.json", {"items": [{"id": "r1-1", "note": "n"}]})
            page, _ = pp.build_product_prototype(root)
            assert page is not None
            config = json.loads(page.read_text(encoding="utf-8").split('id="viewer-config">', 1)[1].split("</script>", 1)[0])
        self.assertEqual(config["rounds"][0]["items"][0]["id"], "r1-1")
        self.assertNotIn("design", config)


class ProductMessageTests(unittest.TestCase):
    """A value from a flow or the sitemap reaches a message only through `quoted`: no control character, a bounded length."""

    def test_a_control_character_in_a_flow_link_or_a_navigation_item_does_not_reach_the_output(self):
        evil = "go\x1b[2J\x07‮ok: 99 screens"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = product(root)
            flow = app / "flows" / "start.html"
            button = f'<button data-go="{evil}{"x" * 300}" data-testid="s-go">Go</button></div>'
            flow.write_text(flow.read_text(encoding="utf-8").replace("</div>", button, 1), encoding="utf-8")
            sitemap = json.loads((app / "sitemap.json").read_text(encoding="utf-8"))
            sitemap["navigation"] = [{"label": evil, "go": evil}]
            (app / "sitemap.json").write_text(json.dumps(sitemap), encoding="utf-8")
            problems = pp.build_product_prototype(root, write=False)[1]
        text = "\n".join(problems)
        self.assertIn("which no flow draws", text)
        self.assertIn("[2Jok: 99 screens", text, "the printable part of the value stays")
        self.assertNotRegex(text.replace("\n", ""), r"[\x00-\x1f\x7f-\x9f‮]")
        self.assertTrue(all(len(line) < 400 for line in problems), "a long value is cut short")


class SiblingModuleTests(unittest.TestCase):
    def test_the_loaded_check_module_is_keyed_by_its_file_so_one_from_another_folder_is_never_reused(self):
        self.assertIn(f"aidd_team_tools.{pp.HERE / 'design_checks'}", sys.modules)
        self.assertNotIn("aidd_team_tools.design_checks", sys.modules)


class ScriptHashTests(unittest.TestCase):
    """The page's policy names the viewer's own inline scripts by hash (code-scanning alert 14): read in any letter case
    and with a loose end tag, and a script element it cannot account for stops the build."""

    def test_any_case_and_a_loose_end_tag_are_hashed_alike(self):
        plain = pp.script_hashes("<script>run()</script>")
        self.assertEqual(pp.script_hashes("<SCRIPT>run()</SCRIPT >"), plain)
        self.assertEqual(pp.script_hashes('<script type="application/json">{}</script><script>run()</script>'), plain)
        self.assertEqual(pp.script_hashes("<p>no script</p>"), "'none'")

    def test_a_script_it_cannot_name_stops_the_build(self):
        for odd in ('<script src="x.js"></script>', '<script type="module">run()</script>', "<script>run()</scrip>"):
            with self.subTest(odd=odd):
                with self.assertRaises(ValueError):
                    pp.script_hashes(odd)

    def test_the_viewer_itself_is_accounted_for(self):
        self.assertNotEqual(pp.script_hashes((PROTOTYPE_TOOL / "viewer.html").read_text(encoding="utf-8")), "'none'")


class FormatAndViewsTests(unittest.TestCase):
    def test_a_newer_or_unreadable_format_asks_for_a_newer_tool(self):
        self.assertEqual(pp._newer(1), "")
        self.assertIn("newer than this tool's", pp._newer(pp.FORMAT + 1))
        for odd in ("2a", ""):
            self.assertIn("which is no number", pp._newer(odd))
        self.assertEqual(pp._DESIGN_FORMAT.search("<html lang='en' data-aidd-prototype='2'>").group(1), "2")

    def test_pages_go_to_a_folder_that_ignores_itself_and_hides_nothing_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q")
            folder = pp._views(root)
            self.assertEqual((folder / ".gitignore").read_text(encoding="utf-8"), "*\n")
            self.assertFalse((root / ".aidd" / ".gitignore").exists())
            (root / ".aidd" / "config.yaml").write_text("profile: solo\n", encoding="utf-8")
            ignored = subprocess.run(["git", "check-ignore", "-q", ".aidd/config.yaml"], cwd=root)
            self.assertEqual(ignored.returncode, 1, "aidd's config, once a project adopts it, is never hidden")


class CommandLineTests(unittest.TestCase):
    def test_the_showcase_is_shown_never_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            done = tool(root, "example")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue((root / ".aidd" / "views" / "prototype-example.html").is_file())
            self.assertEqual(sorted(p.name for p in root.iterdir()), [".aidd"], "nothing of the showcase lands in the project")

    def test_open_shows_the_page_or_names_the_address(self):
        """`--open` opens the written page in the person's browser; where none opens, as in a headless session, it says to
        open the printed address, so an agent still gets it."""
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "page.html"
            page.write_text("<p>x</p>", encoding="utf-8")
            with mock.patch("webbrowser.open", return_value=True) as opened:
                self.assertEqual(pp.open_page(page), "opened it in your browser")
            opened.assert_called_once_with(page.resolve().as_uri())
            with mock.patch("webbrowser.open", return_value=False):
                self.assertIn("open the address above", pp.open_page(page))
            with mock.patch("webbrowser.open", side_effect=pp.webbrowser.Error("none")):
                self.assertIn("open the address above", pp.open_page(page))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_without_browser = {k: v for k, v in os.environ.items() if k != "BROWSER"} | {"BROWSER": "true"}
            done = subprocess.run(
                [sys.executable, "-I", str(TOOL), "example", "--open"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                env=env_without_browser,
            )
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("file://", done.stdout)
        from aidd.cli import parser as cli_parser

        args = cli_parser.build_parser().parse_args(["prototype", "--example", "--open"])
        self.assertTrue(args.open and args.example, "`aidd prototype --open` takes the flag too")

    def test_the_tool_runs_without_aidd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(tool(root, "new-product", "--name", "Field Notes").returncode, 0)
            self.assertEqual(tool(root, "check").returncode, 0)
            built = tool(root, "build")
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            self.assertIn("wrote .aidd/views/prototype.html", built.stdout)
            contract = json.loads(tool(root, "components").stdout)
            self.assertIn("app-bar", [c["name"] for c in contract["components"]])
            made = tool(root, "new-design", "directions/a.html", "--title", "Cards")
            self.assertEqual(made.returncode, 0, made.stderr)
            sketch = (root / "directions" / "a.html").read_text(encoding="utf-8")
            self.assertNotIn("{{", sketch)
            self.assertIn("directions/a.html", sketch)
            self.assertEqual(tool(root, "build", "directions/a.html").returncode, 0)

    def test_in_aiddsprocess_the_messages_keep_aidds_command(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("pathlib.Path.cwd", return_value=Path(tmp)):
            product(Path(tmp))
            with mock.patch("builtins.print"):
                pp.main(["components"])
        self.assertEqual(pp.BUILD, "aidd prototype")

    def test_aidd_runs_the_same_commands(self):
        with adopted_repo():
            run_cli("new", "product-prototype")
            code, out = run_cli("prototype", "--components")
            self.assertEqual(code, 0, out)
            self.assertIn('"name": "app-bar"', out)
            code, out = run_cli("prototype", "--new-design", "specs/explore/cards/directions/a.html", "--title", "Cards")
            self.assertEqual(code, 0, out)
            self.assertNotIn("{{", Path("specs/explore/cards/directions/a.html").read_text(encoding="utf-8"))
            code, out = run_cli("prototype", "--example")
            self.assertEqual(code, 0, out)
            self.assertIn("never a start", out)
            code, out = run_cli("prototype", "--check", "--components")
            self.assertNotEqual(code, 0)
            self.assertIn("give one of them", out)


class LoaderTests(unittest.TestCase):
    def test_a_missing_tool_names_the_fix_and_a_broken_one_is_never_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            team = Path(tmp)
            (team / "tools" / "broken").mkdir(parents=True)
            (team / "tools" / "broken" / "broken.py").write_text("raise RuntimeError('half made')\n", encoding="utf-8")
            with mock.patch("aidd.kernel.resources.data_dir", return_value=team):
                with self.assertRaisesRegex(FileNotFoundError, "reinstall aidd"):
                    resources.team_tool("absent")
                for _ in range(2):  # the second load fails as the first did: nothing half made was kept
                    with self.assertRaisesRegex(RuntimeError, "half made"):
                        resources.team_tool("broken")


if __name__ == "__main__":
    unittest.main()
