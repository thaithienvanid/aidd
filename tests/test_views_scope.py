"""Four pages, each with a reason to exist, and the verifier's recordings beside the preview they came from.

The HTML pages are the Spec approval page (`aidd hash --html`), the Merge approval page (`aidd gate --html`, which holds
the verification), the exploration (`aidd explore`), and the client status (`aidd digest --client --html`). `aidd test`,
`aidd release-notes`, and the team digest print text only. `aidd metrics --design` and the handoff note's `ts` are gone.
What the verifier records for a head is listed in `.aidd/evidence/preview/<head_sha>/artifacts.json`, never in
evidence.json, and the pages read it there.
"""

import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, run_cli

from aidd import views
from aidd.workitems import handoff_notes
from aidd.views import verification
from aidd.cli import parser
from aidd.gate import test_runner
from aidd.kernel import json_schema, resources

HEAD = "a" * 40


def parses(*argv: str) -> bool:
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        try:
            parser.build_parser().parse_args(list(argv))
        except SystemExit as stop:
            return stop.code == 0
    return True


class ThePages(unittest.TestCase):
    def test_the_cut_flags_are_refused(self):
        for argv in (("test", "--html"), ("release-notes", "--since", "v1", "--html"), ("metrics", "--design")):
            self.assertFalse(parses(*argv), argv)

    def test_the_four_pages_stay(self):
        for argv in (
            ("hash", "specs/SPEC-1.md", "--html"),
            ("gate", "--html"),
            ("explore", "specs/SPEC-1/explore/split-bill"),
            ("digest", "--since", "v1", "--client", "--html"),
        ):
            self.assertTrue(parses(*argv), argv)
        for gone in ("verification_page",):
            self.assertFalse(hasattr(views, gone), gone)

    def test_the_team_digest_has_no_page(self):
        code, out = run_cli("digest", "--since", "2026-09-01", "--html")
        self.assertEqual(code, 2, out)
        self.assertIn("--html goes with --client", out)


class NoTs(unittest.TestCase):
    def test_a_handoff_ts_is_a_key_aidd_does_not_read(self):
        note = '```aidd-handoff\ndone: x\nnext: tester\nneeds: none\nstopped_at: none\nts: "2026-09-30T10:00:00Z"\n```\n'
        (w,) = handoff_notes.handoff_warnings("specs/SPEC-1.md", note)
        self.assertIn("keys aidd does not read: ts", w)
        self.assertNotIn("ts = ", (ROOT / ".agents" / "skills" / "aidd" / "references" / "handoff.md").read_text(encoding="utf-8"))


class Recordings(unittest.TestCase):
    def test_evidence_json_holds_no_artifacts(self):
        self.assertNotIn("artifacts", resources.load_json("evidence.schema.json")["properties"])
        self.assertFalse(hasattr(test_runner, "kept_artifacts"))

    def test_the_pages_read_the_previews_artifacts_json(self):
        with tempfile.TemporaryDirectory() as d:
            ev_dir = Path(d)
            shot = ev_dir / "preview" / HEAD / "a1-checkout.png"
            shot.parent.mkdir(parents=True)
            shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            items = [{"path": f"preview/{HEAD}/a1-checkout.png", "kind": "screenshot", "sha256": hashlib.sha256(shot.read_bytes()).hexdigest()}]
            self.assertEqual(json_schema.validate(items, "artifacts.schema.json"), [])
            (shot.parent / "artifacts.json").write_text(__import__("json").dumps(items), encoding="utf-8")
            self.assertEqual(verification.preview_artifacts(ev_dir, HEAD), items)
            evidence = {"head_sha": HEAD, "base_sha": "b" * 40, "results": []}
            html = str(verification.verification_section(evidence, {}, "", ev_dir))
            self.assertIn("a1-checkout.png", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertEqual(verification.preview_artifacts(ev_dir, "c" * 40), [])


class RecordPreview(unittest.TestCase):
    """`aidd record preview SHA` writes artifacts.json for the files the verifier saved, so the verifier stays
    read-only: aidd writes the list, as `aidd test` writes the evidence."""

    def saved(self, ev_dir: Path, files: dict[str, bytes]) -> Path:
        folder = ev_dir / "preview" / HEAD
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (folder / name).write_bytes(data)
        return folder

    def test_the_list_it_writes_is_the_one_the_page_shows(self):
        with tempfile.TemporaryDirectory() as d:
            ev_dir = Path(d)
            folder = self.saved(ev_dir, {"a1-checkout.png": b"\x89PNG\r\n\x1a\n" + b"0" * 32, "main-flow.zip": b"PK", "api.txt": b"GET /"})
            code, out = run_cli("record", "preview", HEAD, "--dir", str(ev_dir))
            self.assertEqual(code, 0, out)
            self.assertIn("1 screenshot, 1 trace, 1 transcript", out)
            items = verification.preview_artifacts(ev_dir, HEAD)
            self.assertEqual(
                [(i["path"], i["kind"]) for i in items],
                [
                    (f"preview/{HEAD}/a1-checkout.png", "screenshot"),
                    (f"preview/{HEAD}/api.txt", "transcript"),
                    (f"preview/{HEAD}/main-flow.zip", "trace"),
                ],
            )
            self.assertEqual(items[0]["sha256"], hashlib.sha256((folder / "a1-checkout.png").read_bytes()).hexdigest())
            html = str(verification.verification_section({"head_sha": HEAD, "base_sha": "b" * 40, "results": []}, {}, "", ev_dir))
            self.assertIn("data:image/png;base64,", html)
            # Run again after a new capture: the list is written again, and never lists itself.
            (folder / "a2-receipt.png").write_bytes(b"\x89PNG\r\n\x1a\n1")
            self.assertEqual(run_cli("record", "preview", HEAD, "--dir", str(ev_dir))[0], 0)
            paths = [i["path"] for i in verification.preview_artifacts(ev_dir, HEAD)]
            self.assertIn(f"preview/{HEAD}/a2-receipt.png", paths)
            self.assertNotIn(f"preview/{HEAD}/artifacts.json", paths)

    def test_it_refuses_what_it_cannot_list_and_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as d:
            ev_dir = Path(d)
            code, out = run_cli("record", "preview", "not-a-sha", "--dir", str(ev_dir))
            self.assertEqual(code, 2)
            self.assertIn("git rev-parse HEAD", out)
            code, out = run_cli("record", "preview", HEAD, "--dir", str(ev_dir))
            self.assertEqual(code, 2)
            self.assertIn("save the screenshots, traces, and transcripts there first", out)
            folder = self.saved(ev_dir, {"notes.docx": b"x"})
            code, out = run_cli("record", "preview", HEAD, "--dir", str(ev_dir))
            self.assertEqual(code, 2)
            self.assertIn("aidd knows no kind for .docx", out)
            (folder / "notes.docx").unlink()
            (folder / "a1.png").symlink_to(ev_dir / "elsewhere.png")
            code, out = run_cli("record", "preview", HEAD, "--dir", str(ev_dir))
            self.assertEqual(code, 2)
            self.assertIn("is a link or not a regular file", out)
            self.assertFalse((folder / "artifacts.json").exists())

    def test_a_link_never_sends_the_write_elsewhere(self):
        # An agent cannot point the list, or a folder on its way, at a file the guard keeps it from: aidd refuses.
        with tempfile.TemporaryDirectory() as d:
            ev_dir, victim = Path(d) / "evidence", Path(d) / "app.py"
            victim.write_text("print('mine')\n", encoding="utf-8")
            folder = self.saved(ev_dir, {"a1.png": b"\x89PNG"})
            (folder / "artifacts.json").symlink_to(victim)
            code, out = run_cli("record", "preview", HEAD, "--dir", str(ev_dir))
            self.assertEqual(code, 2)
            self.assertIn("is a link or not a regular file", out)
            (folder / "artifacts.json").unlink()
            elsewhere = Path(d) / "elsewhere" / HEAD
            elsewhere.mkdir(parents=True)
            (elsewhere / "a1.png").write_bytes(b"\x89PNG")
            (folder / "a1.png").unlink()
            folder.rmdir()
            (ev_dir / "preview").rmdir()
            (ev_dir / "preview").symlink_to(elsewhere.parent)
            code, out = run_cli("record", "preview", HEAD, "--dir", str(ev_dir))
            self.assertEqual(code, 2)
            self.assertIn("is a symbolic link", out)
            self.assertFalse((elsewhere / "artifacts.json").exists())
            self.assertEqual(victim.read_text(encoding="utf-8"), "print('mine')\n")

    def test_the_default_folder_is_the_evidences(self):
        self.assertEqual(parser.build_parser().parse_args(["record", "preview", HEAD]).dir, ".aidd/evidence")


if __name__ == "__main__":
    unittest.main()
