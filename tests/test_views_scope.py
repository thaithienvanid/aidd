"""Four pages, each with a reason to exist, and the verifier's recordings beside the preview they came from.

The HTML pages are the Spec approval page (`aidd hash --html`), the Merge approval page (`aidd gate --html`, which holds
the verification), the exploration (`aidd explore`), and the client status (`aidd digest --client --html`). `aidd test`,
`aidd release-notes`, and the team digest print text only. `aidd metrics --design` and the handoff note's `ts` are gone.
What the verifier records for a head is listed in `aidd-evidence/preview/<head_sha>/artifacts.json`, never in
evidence.json, and the pages read it there.
"""

import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, run_cli

from aidd import cli, resources, runner, schema, views, workitems

HEAD = "a" * 40


def parses(*argv: str) -> bool:
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        try:
            cli.build_parser().parse_args(list(argv))
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
            ("explore", "docs/design/SPEC-1"),
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
        note = '```aidd-handoff\ndone = "x"\nnext = "tester"\nneeds = "none"\nstopped_at = "none"\nts = "2026-09-30T10:00:00Z"\n```\n'
        (w,) = workitems.handoff_warnings("specs/SPEC-1.md", note)
        self.assertIn("keys aidd does not read: ts", w)
        self.assertNotIn("ts = ", (ROOT / ".agents" / "skills" / "aidd" / "references" / "handoff.md").read_text(encoding="utf-8"))


class Recordings(unittest.TestCase):
    def test_evidence_json_holds_no_artifacts(self):
        self.assertNotIn("artifacts", resources.load_json("evidence.schema.json")["properties"])
        self.assertFalse(hasattr(runner, "kept_artifacts"))

    def test_the_pages_read_the_previews_artifacts_json(self):
        with tempfile.TemporaryDirectory() as d:
            ev_dir = Path(d)
            shot = ev_dir / "preview" / HEAD / "a1-checkout.png"
            shot.parent.mkdir(parents=True)
            shot.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            items = [{"path": f"preview/{HEAD}/a1-checkout.png", "kind": "screenshot", "sha256": hashlib.sha256(shot.read_bytes()).hexdigest()}]
            self.assertEqual(schema.validate(items, "artifacts.schema.json"), [])
            (shot.parent / "artifacts.json").write_text(__import__("json").dumps(items), encoding="utf-8")
            self.assertEqual(views.preview_artifacts(ev_dir, HEAD), items)
            evidence = {"head_sha": HEAD, "base_sha": "b" * 40, "results": []}
            html = str(views.verification_section(evidence, {}, "", ev_dir))
            self.assertIn("a1-checkout.png", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertEqual(views.preview_artifacts(ev_dir, "c" * 40), [])


if __name__ == "__main__":
    unittest.main()
