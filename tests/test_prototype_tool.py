"""aidd-team's prototype tool on its own: the component contract, the Storybook check, the design format, where pages
go, the command line run without aidd, and how aidd loads it."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import PROTOTYPE_TOOL, copy_showcase_images, adopted_repo, git, run_cli

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


class RoundCommentsTests(unittest.TestCase):
    """The tool reads the comments of the earlier rounds beside a design for the viewer, each in its round's folder, and
    each comment done once a later round's changes.json answers it (R231). A file of another shape is reported, never a
    crash."""

    def write(self, folder: Path, rel: str, data) -> None:
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def test_an_item_is_done_once_a_later_round_answers_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            items = [
                {"id": "r1-1", "type": "remove", "screen": "home", "state": "empty", "testid": "home-x", "comment": "Remove this."},
                {"id": "r1-2", "type": "odd", "screen": "home", "state": "empty", "testid": "home-y", "comment": "x" * 900},
                {"id": "r1-3", "screen": "home", "state": "error", "testid": "home-z", "comment": "Say what failed."},
                "not an item",
            ]
            self.write(folder, "rounds/1/comments.json", {"round": 1, "items": items})
            self.write(folder, "rounds/x/comments.json", {})  # no round number: left out
            self.write(folder, "rounds/1/changes.json", {"changes": [{"answers": ["r1-3"]}]})
            self.write(folder, "rounds/2/changes.json", {"changes": [{"answers": ["r1-1", 7]}]})
            self.write(folder, "rounds/2/comments.json", "not json")
            rounds, problems = pp.round_comments(folder)
        self.assertEqual([r["round"] for r in rounds], [1, 2])
        first = {it["id"]: it for it in rounds[0]["items"]}
        self.assertTrue(first["r1-1"]["done"])
        self.assertFalse(first["r1-3"]["done"], "round 1's own changes.json answers nothing of round 1")
        self.assertEqual(first["r1-2"]["type"], "change")  # an unknown type reads as change
        self.assertEqual(len(first["r1-2"]["comment"]), pp.MAX_TEXT)
        self.assertEqual(rounds[1]["items"], [])
        self.assertTrue(any(p.startswith("rounds/2/comments.json: not JSON") for p in problems), problems)

    def test_the_reader_passes_by_as_capped_text_and_leaves_a_persons_item_without_it(self):
        cases = (
            ("an agent", "agent:claude-code/claude-opus-5-5", "agent:claude-code/claude-opus-5-5"),
            ("a person", "@mai", "@mai"),
            ("too long", "agent:" + "x" * 900, ("agent:" + "x" * 900)[: pp.MAX_TEXT]),
            ("not text", {"deep": ["agent:x"]}, None),
            ("empty", "", None),
        )
        for name, by, want in cases:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp)
                item = {"id": "r1-1", "screen": "home", "state": "empty", "testid": "home-x", "comment": "Fix.", "by": by}
                self.write(folder, "rounds/1/comments.json", {"items": [item]})
                got = pp.round_comments(folder)[0][0]["items"][0]
                self.assertEqual(got.get("by"), want)
                self.assertEqual("by" in got, want is not None, "an item without a writer carries no `by`")

    def test_a_file_of_another_shape_is_reported_never_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.write(folder, "rounds/1/comments.json", {"items": {"r1-1": "an object, not a list"}})
            self.write(folder, "rounds/2/comments.json", {"items": 5})
            self.write(folder, "rounds/3/comments.json", {"items": []})
            self.write(folder, "rounds/03/comments.json", {"items": []})  # round 3 again
            self.write(folder, "rounds/4/comments.json", [1, 2])
            self.write(folder, "rounds/4/changes.json", {"changes": 5})
            self.write(folder, "rounds/5/changes.json", {"changes": [{"answers": "r1-1"}]})
            self.write(folder, "rounds/²/changes.json", {"changes": []})  # a digit Python reads, never a round
            self.write(folder, "rounds/6/changes.json", "[" * 5000)
            rounds, problems = pp.round_comments(folder)
        self.assertEqual([r["round"] for r in rounds], [1, 2, 3, 4])
        self.assertTrue(all(r["items"] == [] for r in rounds))
        text = "\n".join(problems)
        for want in (
            "`items` is not a list",
            "not a JSON object",
            "rounds/3/comments.json: round 3 has another file",
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
            outside = Path(away) / "comments.json"
            outside.write_text(json.dumps({"items": [{"id": "r1-1", "comment": "OUTSIDE"}]}), encoding="utf-8")
            for n in (1, 2):
                (folder / "rounds" / str(n)).mkdir(parents=True)
            (folder / "rounds" / "1" / "comments.json").symlink_to(outside)
            os.mkfifo(folder / "rounds" / "2" / "comments.json")
            self.write(folder, "rounds/3/comments.json", " " * (pp.MAX_FILE_BYTES + 1))
            self.write(folder, "rounds/4/comments.json", {"items": [{"id": "r4-1", "comment": {"deep": [[[1]]]}, "screen": ["x"]}]})
            (Path(away) / "changes.json").write_text(json.dumps({"changes": [{"answers": ["r4-1"]}]}), encoding="utf-8")
            (folder / "rounds" / "5").symlink_to(Path(away), target_is_directory=True)
            rounds, problems = pp.round_comments(folder)
        comments = [it["comment"] for r in rounds for it in r["items"]]
        self.assertNotIn("OUTSIDE", comments)
        fourth = next(r["items"] for r in rounds if r["round"] == 4)
        self.assertEqual(fourth, [{"id": "r4-1", "screen": "", "state": "", "testid": "", "comment": "", "type": "change", "done": False}])
        text = "\\n".join(problems)
        self.assertIn("rounds/1/comments.json: not a plain file", text)
        self.assertIn("rounds/2/comments.json: not a plain file", text)
        self.assertIn("rounds/3/comments.json: larger than", text)
        self.assertIn("rounds/5/comments.json: not a plain file", text, "a round folder linked out of the design is never read")
        self.assertIn("rounds/5/changes.json: not a plain file", text)

    def test_the_newest_rounds_are_kept_and_the_total_is_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for n in range(1, pp.MAX_ROUNDS + 3):
                self.write(folder, f"rounds/{n}/comments.json", {"items": [{"id": f"r{n}-1", "comment": "n"}]})
            rounds, _ = pp.round_comments(folder)
            self.assertEqual(rounds[-1]["round"], pp.MAX_ROUNDS + 2)
            self.assertEqual(len(rounds), pp.MAX_ROUNDS)
            big = [{"id": f"r1-{i}", "comment": "x" * pp.MAX_TEXT} for i in range(pp.MAX_ITEMS)]
            for n in range(1, pp.MAX_ROUNDS + 3):
                self.write(folder, f"rounds/{n}/comments.json", {"items": big})
            rounds, problems = pp.round_comments(folder)
        size = sum(len(it["comment"]) for r in rounds for it in r["items"])
        self.assertLessEqual(size, pp.MAX_TOTAL)
        self.assertTrue(any("more than" in p for p in problems))

    def test_the_view_carries_the_rounds_and_a_comment_stays_text(self):
        hostile = "</script><img src=x onerror=alert(1)>"
        with adopted_repo() as root:
            design = root / "specs" / "SPEC-9" / "design"
            design.mkdir(parents=True)
            (design / "prototype.html").write_text((PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8"), encoding="utf-8")
            copy_showcase_images(design)
            self.write(design, "rounds/1/comments.json", {"round": 1, "items": [{"id": "r1-1", "comment": hostile}]})
            self.write(design, "rounds/2/changes.json", {"changes": "not a list"})
            page, problems = pp.view_prototype_file(root, "specs/SPEC-9/design/prototype.html")
            self.assertEqual(problems, [])
            assert page is not None
            block = page.read_text(encoding="utf-8").split('id="viewer-config">', 1)[1].split("</script>", 1)[0]
            _, checked = pp.view_prototype_file(root, "specs/SPEC-9/design/prototype.html", write=False)
        self.assertNotIn("<", block, "a comment reaches the page only as escaped JSON")
        config = json.loads(block)
        self.assertEqual(config["rounds"][0]["items"][0]["comment"], hostile)
        self.assertTrue(config["round_problems"])
        # The tool names the design by its own path, for the prompt the viewer writes. The comments are still kept by the page's path.
        self.assertEqual(config["design"], "specs/SPEC-9/design/prototype.html")
        self.assertEqual(checked, [], "a check never reads the comments files")

    def test_the_product_prototype_carries_its_rounds(self):
        with adopted_repo() as root:
            app = product(root)
            self.write(app, "rounds/1/comments.json", {"items": [{"id": "r1-1", "comment": "n"}]})
            page, _ = pp.build_product_prototype(root)
            assert page is not None
            config = json.loads(page.read_text(encoding="utf-8").split('id="viewer-config">', 1)[1].split("</script>", 1)[0])
        self.assertEqual(config["rounds"][0]["items"][0]["id"], "r1-1")
        self.assertNotIn("design", config)

    def test_a_direction_reads_its_own_file_in_the_explorations_rounds_and_a_bad_name_is_refused(self):
        """A design in an exploration's directions/ folder reads `rounds/<N>/comments-<direction>.json` in the exploration,
        and its page carries the direction's name. A file name other than letters, digits, and `-` is refused."""
        with adopted_repo() as root:
            exploration = root / "specs" / "SPEC-9" / "explore" / "listing"
            showcase = (PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8")
            for name in ("a", "b_2"):
                self.write(exploration, f"directions/{name}.html", showcase)
            copy_showcase_images(exploration / "directions")
            self.write(exploration, "exploration.md", "---\ntype: exploration\n---\n")
            self.write(exploration, "rounds/1/comments-a.json", {"round": 1, "items": [{"id": "a-r1-1", "comment": "Lead with the distance."}]})
            self.write(exploration, "rounds/1/comments-b.json", {"round": 1, "items": [{"id": "b-r1-1", "comment": "Another direction's."}]})
            self.write(exploration, "rounds/2/changes.json", {"changes": [{"answers": ["a-r1-1"]}]})
            page, problems = pp.view_prototype_file(root, "specs/SPEC-9/explore/listing/directions/a.html")
            self.assertEqual(problems, [])
            assert page is not None
            config = json.loads(page.read_text(encoding="utf-8").split('id="viewer-config">', 1)[1].split("</script>", 1)[0])
            refused, why = pp.view_prototype_file(root, "specs/SPEC-9/explore/listing/directions/b_2.html")
            checked = pp.check_design_file(root, "specs/SPEC-9/explore/listing/directions/b_2.html")[0]
        self.assertEqual(config["direction"], "a")
        self.assertEqual([(it["id"], it["done"]) for r in config["rounds"] for it in r["items"]], [("a-r1-1", True)])
        self.assertIsNone(refused)
        self.assertIn("letters, digits, and `-` only", why[0])
        self.assertTrue(any("letters, digits, and `-` only" in problem for problem in checked), checked)

    def test_a_design_in_directions_with_no_exploration_keeps_its_comments_beside_it(self):
        """No `exploration.md` beside `directions/`: the design is no direction, so it reads `rounds/<N>/comments.json`
        beside itself, and its ids carry no direction."""
        with adopted_repo() as root:
            folder = root / "specs" / "SPEC-9" / "design" / "directions"
            self.write(folder, "a.html", (PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8"))
            copy_showcase_images(folder)
            self.write(folder, "rounds/1/comments.json", {"round": 1, "items": [{"id": "r1-1", "comment": "n"}]})
            self.assertEqual(pp.direction_of(root, folder / "a.html"), ("", folder, ""))
            page, problems = pp.view_prototype_file(root, "specs/SPEC-9/design/directions/a.html")
            self.assertEqual(problems, [])
            assert page is not None
            config = json.loads(page.read_text(encoding="utf-8").split('id="viewer-config">', 1)[1].split("</script>", 1)[0])
        self.assertEqual((pp.comments_file(config["direction"]), config["rounds"][0]["items"][0]["id"]), ("comments.json", "r1-1"))

    def test_a_direction_needs_its_exploration_inside_the_repository_and_never_a_linked_one(self):
        """A repository whose root folder is named `directions`, with an `exploration.md` above it, and a linked
        `exploration.md`, are no direction: neither reads rounds from outside the design's own folder."""
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            root = top / "directions"
            (root / "rounds" / "1").mkdir(parents=True)
            (top / "exploration.md").write_text("---\n", encoding="utf-8")
            self.assertEqual(pp.direction_of(root, root / "a.html"), ("", root, ""), "the exploration above the repository is no exploration")
            linked = root / "explore" / "x"
            (linked / "directions").mkdir(parents=True)
            (linked / "exploration.md").symlink_to(top / "exploration.md")
            self.assertEqual(pp.direction_of(root, linked / "directions" / "a.html")[0], "", "a linked exploration.md is none")
            (linked / "exploration.md").unlink()
            (linked / "exploration.md").write_text("---\n", encoding="utf-8")
            self.assertEqual(pp.direction_of(root, linked / "directions" / "a.html"), ("a", linked, ""))

    def test_a_comment_whose_id_names_another_direction_is_left_out_and_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            items = [{"id": "a-r1-1", "comment": "mine"}, {"id": "b-r1-1", "comment": "b's"}, {"id": "r1-2", "comment": "a design's"}]
            self.write(folder, "rounds/1/comments-a.json", {"round": 1, "items": items})
            self.write(folder, "rounds/1/comments.json", {"round": 1, "items": [{"id": "zz-r1-1", "comment": "a direction's"}]})
            rounds, problems = pp.round_comments(folder, "a")
            own, own_problems = pp.round_comments(folder)
        self.assertEqual([it["id"] for it in rounds[0]["items"]], ["a-r1-1"])
        self.assertIn("rounds/1/comments-a.json: b-r1-1 is left out: its id names another direction", problems)
        self.assertIn("rounds/1/comments-a.json: r1-2 is left out: its id names another direction", problems)
        self.assertEqual((own[0]["items"], own_problems), ([], ["rounds/1/comments.json: zz-r1-1 is left out: its id names another direction"]))


class ImageFieldTests(unittest.TestCase):
    """R249: an image field names a data URI or a file beside the design; the tool reads the file in, and never a path out."""

    PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16

    def test_a_file_inside_the_folder_is_read_in_and_every_other_value_is_left_out_with_its_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            folder = top / "design"
            (folder / "img").mkdir(parents=True)
            (folder / "img" / "a.png").write_bytes(self.PNG)
            (top / "secret.png").write_bytes(self.PNG)
            (folder / "notes.txt").write_text("x", encoding="utf-8")
            (folder / "big.png").write_bytes(b"0" * (pp.MAX_IMAGE_BYTES + 1))
            link = folder / "out.png"
            try:
                link.symlink_to(top / "secret.png")
            except OSError:
                link = None
            uri = "data:image/png;base64,iVBORw0KGgo="
            cases = {
                "img/a.png": ("data:image/png;base64,", ""),
                uri: (uri, ""),
                "../secret.png": ("", "outside the design's folder"),
                str(top / "secret.png"): ("", "outside the design's folder"),
                "img/../../secret.png": ("", "outside the design's folder"),
                "notes.txt": ("", "no image file"),
                "missing.png": ("", "no file in the design's folder"),
                "img": ("", "no image file"),
                "big.png": ("", "larger than"),
                "data:text/html;base64,PHA+": ("", "no image type"),
                **({"out.png": ("", "outside the design's folder")} if link else {}),
            }
            for value, (shown, why) in cases.items():
                with self.subTest(value=value):
                    out, problems = pp.with_images({"list": [{"photo": value}]}, {"photo"}, folder)
                    self.assertTrue(out["list"][0]["photo"].startswith(shown) if shown else out["list"][0]["photo"] == "")
                    self.assertEqual(bool(problems), bool(why))
                    if why:
                        self.assertIn(why, problems[0])

    def test_the_showcase_page_carries_each_drawing_and_a_check_names_a_missing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = pp.view_example(root).read_text(encoding="utf-8")
            fixtures = json.loads(page.split('id="fixtures">', 1)[1].split("</script>", 1)[0])
            self.assertTrue(all(s["photo"].startswith("data:image/svg+xml;base64,") for s in fixtures["sitters"]))
            (root / "prototype.html").write_text((PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8"), encoding="utf-8")
            problems, _ = pp.check_design_file(root, "prototype.html")
            self.assertEqual(len([p for p in problems if "sitters/" in p and "no file" in p]), 4, problems)


class ServerTests(unittest.TestCase):
    """R241: the opt-in server listens on 127.0.0.1 unless asked, serves only the page and the design's folder, and stays off
    under AIDD_OFFLINE=1."""

    server = pp._sibling("server")

    def folder(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        top = Path(tmp.name)
        (top / "design" / "img").mkdir(parents=True)
        (top / "design" / "img" / "a.png").write_bytes(b"png")
        (top / "design" / "prototype.html").write_text("<p>design</p>", encoding="utf-8")
        (top / "secret.txt").write_text("secret", encoding="utf-8")
        try:
            (top / "design" / "out.txt").symlink_to(top / "secret.txt")
        except OSError:
            pass
        return top / "design"

    def test_a_path_never_leaves_the_designs_folder_and_no_folder_is_listed(self):
        folder = self.folder()
        cases = {
            "/img/a.png": "img/a.png",
            "/img/a.png?x=1": "img/a.png",
            "/prototype.html": "prototype.html",
            "/../secret.txt": None,
            "/img/../../secret.txt": None,
            "/%2e%2e/secret.txt": None,
            "/..%2fsecret.txt": None,
            "/img/..%5c..%5csecret.txt": None,
            "//etc/passwd": None,
            "/img/": None,
            "/img": None,
            "/missing.png": None,
            "/out.txt": None,
            "/a%00.png": None,
            "/C:/Windows/win.ini": None,
            "/.env": None,
            "/img/.git/config": None,
        }
        for url, want in cases.items():
            with self.subTest(url=url):
                got = self.server.file_in(folder, url)
                self.assertEqual(got, (folder / want).resolve() if want else None)

    def test_it_binds_to_the_loopback_address_unless_asked_for_the_network(self):
        for lan, host in ((False, "127.0.0.1"), (True, "0.0.0.0")):
            with self.subTest(lan=lan):
                server = self.server.make_server(self.folder(), lambda: "page", lan=lan, port=0)
                self.addCleanup(server.server_close)
                self.assertEqual(server.server_address[0], host)

    def test_it_answers_the_page_and_files_and_refuses_the_rest(self):
        import threading
        import urllib.error
        import urllib.request

        server = self.server.make_server(self.folder(), lambda: "<p>page</p>", port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base + "/", timeout=10) as answer:
            self.assertEqual((answer.read(), answer.headers["Cache-Control"]), (b"<p>page</p>", "no-store"))
        with opener.open(base + "/img/a.png", timeout=10) as answer:
            self.assertEqual((answer.read(), answer.headers["Content-Type"]), (b"png", "image/png"))
        for path in ("/img/", "/../secret.txt", "/%2e%2e/secret.txt"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                opener.open(base + path, timeout=10)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()

    def test_it_answers_only_its_own_address_and_under_lan_only_behind_the_token(self):
        """A page that rebinds a domain to 127.0.0.1 sends its own Host, so it reads nothing; under --lan a device that
        lacks the printed token reads nothing either."""
        import http.client
        import threading

        server = self.server.make_server(self.folder(), lambda: "<p>page</p>", port=0, token="t0k", hosts=("192.168.1.9",))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        cases = [
            # (the Host header, the path, the status)
            (f"127.0.0.1:{port}", "/t0k/", 200),
            (f"localhost:{port}", "/t0k/img/a.png", 200),
            (f"192.168.1.9:{port}", "/t0k/", 200),
            (f"evil.example:{port}", "/t0k/", 421),
            (f"127.0.0.1:{port}", "/", 404),
            (f"127.0.0.1:{port}", "/img/a.png", 404),
        ]
        for host, path, want in cases:
            with self.subTest(host=host, path=path):
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                conn.request("GET", path, headers={"Host": host})
                self.assertEqual(conn.getresponse().status, want)
                conn.close()

    def test_a_port_out_of_range_and_a_design_at_the_top_are_refused(self):
        said: list[str] = []
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": ""}):
            self.assertEqual(self.server.serve(self.folder(), lambda: "", port=70000, say=said.append), 2)
        self.assertIn("is no port", said[0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "prototype.html").write_text((PROTOTYPE_TOOL / "examples" / "showcase.html").read_text(encoding="utf-8"), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(pp.serve_design(root, "prototype.html"), 2)
            self.assertIn("sits at the repository's top", out.getvalue())

    def test_a_page_is_never_written_through_a_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, outside = Path(tmp) / "repo", Path(tmp) / "outside"
            (root / ".aidd").mkdir(parents=True)
            outside.mkdir()
            try:
                (root / ".aidd" / "views").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("no symlinks here")
            with self.assertRaisesRegex(ValueError, r"\.aidd/views is a link"):
                pp.view_example(root)
            self.assertEqual(list(outside.iterdir()), [])

    def test_a_shortened_flag_is_refused(self):
        """`serve --la` would open the network listener past the `network.listen` pattern, which reads `--lan`."""
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            pp._parser().parse_args(["serve", "--la"])
        self.assertTrue(pp._parser().parse_args(["serve", "--lan"]).lan)

    def test_aidd_offline_keeps_it_off(self):
        said: list[str] = []
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}), mock.patch.object(self.server, "make_server") as made:
            self.assertEqual(self.server.serve(self.folder(), lambda: "", say=said.append), 2)
        made.assert_not_called()
        self.assertIn("AIDD_OFFLINE=1", said[0])


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
            self.assertIn("next: start your own design with `aidd new design-spec", done.stdout, "the showcase names the step after it")
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

    def test_check_with_no_file_and_no_product_prototype_names_both_ways_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = tool(Path(tmp), "check")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("name a design file", done.stdout)
        self.assertIn("start a product prototype", done.stdout)

    def test_a_broken_boundary_is_named_with_its_line_never_called_old(self):
        """R258: a blank line before the fixtures block is a boundary to fix, named with its line, never a design that predates the
        viewer; CRLF line ends read as LF."""
        design = (PROTOTYPE_TOOL / "design.html").read_text(encoding="utf-8")
        line = design[: design.index('<script type="application/json" id="fixtures">')].count("\n") + 1
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crlf.html").write_bytes(design.replace("\n", "\r\n").encode("utf-8"))
            (root / "gap.html").write_text(
                design.replace('</template>\n<script type="application/json" id="fixtures">', '</template>\n\n<script type="application/json" id="fixtures">'),
                encoding="utf-8",
            )
            crlf = pp.check_design_file(root, "crlf.html")[0]
            gap = pp.check_design_file(root, "gap.html")[0]
        self.assertEqual(crlf, [])
        self.assertEqual(len(gap), 1, gap)
        self.assertIn(f"gap.html, line {line + 1}: the fixtures block must start on the line right after", gap[0])

    def test_a_design_that_check_fails_builds_its_page_and_exits_1(self):
        # R252: a design with a dead link never builds quietly, in the tool or in `aidd prototype`, so nobody approves it unseen
        def broken(root: Path) -> str:
            self.assertEqual(tool(root, "new-design", "d/a.html", "--title", "Cards").returncode, 0)
            sketch = root / "d" / "a.html"
            sketch.write_text(sketch.read_text(encoding="utf-8").replace('data-go="start"', 'data-go="nowhere"', 1), encoding="utf-8")
            return "d/a.html"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            done = tool(root, "build", broken(root))
            outputs = [(done.returncode, done.stdout)]
        with adopted_repo() as root:
            outputs.append(run_cli("prototype", broken(root)))
            page = (root / ".aidd" / "views" / "prototype-d-a.html").read_text(encoding="utf-8")  # still written, to look at
            config = json.loads(page.split('id="viewer-config">', 1)[1].split("</script>", 1)[0])
            # R253: the page names the same problems above the artboard, so a person who opens it sees them too.
            self.assertEqual([p for p in config["problems"] if 'data-go="nowhere" names no screen' in p], config["problems"][:1])
        for code, out in outputs:
            self.assertEqual(code, 1, out)
            self.assertIn('data-go="nowhere" names no screen', out)
            self.assertIn("1 problem(s); fix them in d/a.html", out)

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
