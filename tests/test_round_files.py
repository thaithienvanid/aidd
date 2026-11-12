"""The round files beside a design have one owner each, a schema: `rounds/<N>/comments.json`, which the viewer writes,
and `rounds/<N>/changes.json`, which the agent writes. The viewer's export, the prototype tool's reader, and the README's
examples all match it, and `aidd validate` warns on a file that does not."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import PROTOTYPE_TOOL, ROOT

from aidd.kernel import json_schema, resources
from aidd.workitems import explorations

COMMENTS = resources.load_json("round-comments.schema.json")
CHANGES = resources.load_json("round-changes.schema.json")
VIEWER = (PROTOTYPE_TOOL / "viewer.html").read_text(encoding="utf-8")
README = (PROTOTYPE_TOOL / "README.md").read_text(encoding="utf-8")


class SchemaTests(unittest.TestCase):
    def test_the_viewers_export_writes_exactly_the_schemas_fields(self):
        export = re.search(r"const items = \w+\.map\(\(it\) => \(\{(.*?)\}\)\);", VIEWER)
        self.assertIsNotNone(export, "the viewer builds each exported item in one place")
        written = re.findall(r"(\w+):", export.group(1))
        fields = COMMENTS["properties"]["items"]["items"]["properties"]
        # `by` names an agent writer, so the viewer, which a person uses, writes none: an item without it is a person's.
        self.assertEqual(sorted(written), sorted(set(fields) - {"by"}), "a field the viewer writes is a field the schema owns, and back")

    def test_by_names_the_writer_by_an_identity_and_is_optional(self):
        item = {"id": "r1-1", "screen": "s", "state": "empty", "comment": "n"}
        cases = (
            ("an agent", {"by": "agent:claude-code/claude-opus-5-5"}, True),
            ("a person", {"by": "@mai"}, True),
            ("no writer", {}, True),
            ("a space", {"by": "agent:claude code"}, False),
            ("an empty name", {"by": ""}, False),
            ("not text", {"by": 7}, False),
        )
        for name, extra, sound in cases:
            with self.subTest(name):
                found = json_schema.validate({"round": 1, "items": [{**item, **extra}]}, "round-comments.schema.json")
                self.assertEqual(found == [], sound, found)

    def test_the_tools_reader_reads_only_fields_the_schemas_own(self):
        tool = (PROTOTYPE_TOOL / "prototype_rounds.py").read_text(encoding="utf-8")
        read = re.search(r'for k in \(("[a-z]+"(?:, "[a-z]+")*)\)', tool)
        self.assertIsNotNone(read)
        fields = set(COMMENTS["properties"]["items"]["items"]["properties"])
        self.assertLessEqual(set(re.findall(r'"([a-z]+)"', read.group(1))), fields)
        self.assertIn("answers", CHANGES["properties"]["changes"]["items"]["properties"])

    def test_the_readmes_examples_match(self):
        examples = [json.loads(line) for line in README.splitlines() if line.startswith('{"round"') or line.startswith('{"changes"')]
        self.assertEqual(len(examples), 2)
        self.assertEqual(json_schema.validate(examples[0], "round-comments.schema.json"), [])
        self.assertEqual(json_schema.validate(examples[1], "round-changes.schema.json"), [])

    def test_validate_warns_on_a_round_file_its_schema_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "specs" / "SPEC-1" / "design"
            for n in ("1", "2"):
                (folder / "rounds" / n).mkdir(parents=True)
            (folder / "rounds" / "1" / "comments.json").write_text(
                '{"round": 1, "items": [{"id": "r1-1", "screen": "s", "state": "empty", "comment": "n"}]}', encoding="utf-8"
            )
            self.assertEqual(explorations.round_file_warnings(root, folder), [], "a sound file says nothing")
            (folder / "rounds" / "2" / "comments.json").write_text('{"round": 0, "items": [{"id": "x"}]}', encoding="utf-8")
            (folder / "rounds" / "2" / "changes.json").write_text("not json", encoding="utf-8")
            found = explorations.round_file_warnings(root, folder)
            self.assertEqual(len(found), 2, found)
            self.assertIn("specs/SPEC-1/design/rounds/2/comments.json does not match schemas/round-comments.schema.json", found[0])
            self.assertIn("specs/SPEC-1/design/rounds/2/changes.json is not JSON", found[1])

    def test_validate_checks_each_directions_file_its_name_its_design_and_its_ids(self):
        def comments(*ids: str) -> str:
            return json.dumps({"round": 1, "items": [{"id": i, "screen": "s", "state": "empty", "comment": "n"} for i in ids]})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "specs" / "SPEC-1" / "explore" / "listing"
            round_one = folder / "rounds" / "1"
            round_one.mkdir(parents=True)
            (folder / "directions").mkdir()
            for d in ("a", "b"):
                (folder / "directions" / f"{d}.html").write_text("<!doctype html>", encoding="utf-8")
            (round_one / "comments-a.json").write_text(comments("a-r1-1"), encoding="utf-8")
            self.assertEqual(explorations.round_file_warnings(root, folder), [], "a direction's sound file says nothing")
            files = {
                "comments-a.json": comments("a-r1-1", "b-r1-2"),  # another direction's id
                "comments-b.json": '{"round": 1, "items": [{"id": "b-1"}]}',  # the schema rejects it
                "comments-b_2.json": comments("r1-1"),  # no direction's name
                "comments-zzz.json": comments("zzz-r1-1"),  # no directions/zzz.html
                "comments.json": comments("zz-r1-1"),  # a design's own file, with a direction's id
            }
            for name, text in files.items():
                (round_one / name).write_text(text, encoding="utf-8")
            found = explorations.round_file_warnings(root, folder)
        text = "\n".join(found)
        for want in (
            "rounds/1/comments-a.json holds b-r1-2, the ids of another direction",
            "rounds/1/comments-b.json does not match schemas/round-comments.schema.json",
            "rounds/1/comments-b_2.json names no direction",
            "rounds/1/comments-zzz.json names the direction `zzz`, but directions/zzz.html is not in the folder",
            "rounds/1/comments.json holds zz-r1-1, the ids of another direction",
        ):
            self.assertIn(want, text)
        self.assertEqual(len(found), 5, found)

    def test_a_rounds_comments_files_leave_out_a_link_a_way_out_a_large_file_and_any_past_the_cap(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            top = Path(tmp)
            round_one = top / "rounds" / "1"
            round_one.mkdir(parents=True)
            outside = Path(away) / "comments-a.json"
            outside.write_text("{}", encoding="utf-8")
            (round_one / "comments-a.json").symlink_to(outside)
            (top / "rounds" / "2").symlink_to(Path(away), target_is_directory=True)  # a round folder that leads out
            (round_one / "comments-b.json").write_text("x" * 11, encoding="utf-8")
            for i in range(explorations.MAX_DIRECTION_FILES + 1):
                (round_one / f"comments-d{i:02d}.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(explorations, "MAX_LINT_BYTES", 10):
                kept, left_out = explorations.round_comment_files(round_one, top)
                _, led_out = explorations.round_comment_files(top / "rounds" / "2", top)
        text = "\n".join(left_out)
        self.assertIn("comments-a.json is left out: it is a link", text)
        self.assertIn("comments-b.json is left out: it is a link, leads out of the folder, or is larger than 10 bytes", text)
        self.assertIn(f"comments-d{explorations.MAX_DIRECTION_FILES:02d}.json is left out: a round reads the comments of", text)
        self.assertLessEqual(len(kept), explorations.MAX_DIRECTION_FILES)
        self.assertEqual([name for name, _ in kept][:2], ["d00", "d01"])
        self.assertTrue(led_out and led_out[0].startswith("comments-a.json is left out"), led_out)

    def test_each_schema_is_in_the_repository(self):
        for name in ("round-comments.schema.json", "round-changes.schema.json"):
            self.assertTrue((ROOT / "schemas" / name).is_file(), name)


class SaveRoundCommentsTests(unittest.TestCase):
    rounds = resources.team_tool("prototype")._sibling("prototype_rounds")

    def test_save_round_comments_validates_increments_and_refuses_overwrite_or_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            design_dir = top / "specs" / "SPEC-1" / "design"
            design_dir.mkdir(parents=True)
            source = top / "exported.json"
            payload = {
                "round": 1,
                "count": 1,
                "items": [
                    {
                        "id": "r1-1",
                        "type": "change",
                        "screen": "home",
                        "state": "success",
                        "testid": "hero-cta",
                        "index": 0,
                        "box": {"x": 10.6, "y": 20.2, "width": 120.4, "height": 40.9},
                        "comment": "Make larger.",
                    }
                ],
            }
            source.write_text(json.dumps(payload), encoding="utf-8")
            written_path, probs = self.rounds.save_round_comments(design_dir, str(source))
            self.assertEqual(probs, [])
            self.assertEqual(written_path, design_dir / "rounds" / "1" / "comments.json")
            saved = json.loads(written_path.read_text(encoding="utf-8"))
            self.assertEqual(json_schema.validate(saved, "round-comments.schema.json"), [])
            self.assertEqual(saved["items"][0]["box"], {"x": 11, "y": 20, "width": 120, "height": 41})

            # Duplicate round refuses overwrite cleanly
            dup_path, dup_probs = self.rounds.save_round_comments(design_dir, str(source))
            self.assertIsNone(dup_path)
            self.assertTrue(any("already exists" in p for p in dup_probs), dup_probs)

            # Explicit --round 2 writes round 2 cleanly
            second_path, second_probs = self.rounds.save_round_comments(design_dir, str(source), round_num=2)
            self.assertEqual(second_probs, [])
            self.assertEqual(second_path, design_dir / "rounds" / "2" / "comments.json")
            self.assertEqual(json.loads(second_path.read_text(encoding="utf-8"))["round"], 2)

            # Direction naming writes comments-a.json
            explore_dir = top / "specs" / "SPEC-1" / "explore" / "cards"
            explore_dir.mkdir(parents=True)
            payload["items"][0]["id"] = "a-r1-1"
            source.write_text(json.dumps(payload), encoding="utf-8")
            dir_path, dir_probs = self.rounds.save_round_comments(explore_dir, str(source), direction="a")
            self.assertEqual(dir_probs, [])
            self.assertEqual(dir_path, explore_dir / "rounds" / "1" / "comments-a.json")

            # Invalid item refused cleanly
            source.write_text(json.dumps({"round": 1, "items": [{"id": "r1-1"}]}), encoding="utf-8")
            bad_path, bad_probs = self.rounds.save_round_comments(design_dir, str(source), round_num=3)
            self.assertIsNone(bad_path)
            self.assertTrue(bad_probs)

            # Symlink source refused
            outside = top / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            sym = top / "sym.json"
            try:
                sym.symlink_to(outside)
            except OSError:
                self.skipTest("no symlinks here")
            sym_path, sym_probs = self.rounds.save_round_comments(design_dir, str(sym), round_num=4)
            self.assertIsNone(sym_path)
            self.assertTrue(any("symlink" in p for p in sym_probs), sym_probs)

            # NaN rejected in JSON input
            source.write_text(
                '{"round": 1, "items": [{"id": "r1-1", "screen": "home", "state": "s", "comment": "x", "box": {"x": NaN, "y": 0, "width": 10, "height": 10}}]}',
                encoding="utf-8",
            )
            nan_path, nan_probs = self.rounds.save_round_comments(design_dir, str(source), round_num=5)
            self.assertIsNone(nan_path)
            self.assertTrue(any("JSON" in p for p in nan_probs), nan_probs)

    def test_save_comments_cli_handles_symlinked_cwd_and_blocks_docs_traversal(self):
        tool_py = str(PROTOTYPE_TOOL / "prototype.py")
        payload = '{"round": 1, "items": [{"id": "r1-1", "screen": "start", "state": "success", "comment": "Ok."}]}'
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp)
            real_repo = top / "real_repo"
            real_repo.mkdir()
            (top / "outside" / "design" / "app").mkdir(parents=True)
            subprocess.run([sys.executable, "-I", tool_py, "new-product", "--name", "App"], cwd=real_repo, check=True, capture_output=True)
            (real_repo / "exported.json").write_text(payload, encoding="utf-8")
            link_repo = top / "link_repo"
            try:
                link_repo.symlink_to(real_repo, target_is_directory=True)
            except OSError:
                self.skipTest("no symlinks here")
            # Symlinked cwd/root (like macOS /tmp -> /private/tmp) must succeed
            ok = subprocess.run(
                [sys.executable, "-I", tool_py, "save-comments", "exported.json"],
                cwd=link_repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertTrue((real_repo / "docs" / "design" / "app" / "rounds" / "1" / "comments.json").is_file())
            # Traversal via --docs ../outside is rejected cleanly without writing outside
            esc = subprocess.run(
                [sys.executable, "-I", tool_py, "save-comments", "exported.json", "--docs", "../outside/design"],
                cwd=real_repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(esc.returncode, 2)
            self.assertFalse((top / "outside" / "design" / "app" / "rounds").exists())
            # Symlinked docs/design/app is rejected cleanly
            sym_repo = top / "sym_repo"
            (sym_repo / "docs" / "design").mkdir(parents=True)
            (sym_repo / "docs" / "design" / "app").symlink_to(top / "outside" / "design" / "app", target_is_directory=True)
            (sym_repo / "exported.json").write_text(payload, encoding="utf-8")
            sym_res = subprocess.run(
                [sys.executable, "-I", tool_py, "save-comments", "exported.json"],
                cwd=sym_repo,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(sym_res.returncode, 2)
            self.assertFalse((top / "outside" / "design" / "app" / "rounds").exists())


if __name__ == "__main__":
    unittest.main()
