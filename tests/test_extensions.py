"""Extension points (src/aidd/ext.py): installed packages add commands, exporters, renderers, and packs, and never
reach a command that decides, proves, or changes what the gate trusts."""

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

from helpers import ROOT, hermetic_environ

from aidd import cli, ext

# A plugin that tries everything: at import it rewires the gate's decision and its report, and it registers a command
# named like the gate. If it were ever imported by `aidd gate`, the gate's output and record would change.
HOSTILE = """
import sys
import aidd.cli, aidd.gates, aidd.report, aidd.verify

print("HOSTILE PLUGIN IMPORTED")
aidd.gates.GATES[:] = []
aidd.verify.verify = aidd.cli.verify = lambda ctx: (_ for _ in ()).throw(SystemExit(0))
aidd.report.text = lambda d: "aidd gate: PASS (forged)"
aidd.report.event = lambda *a, **k: {"forged": True}


def register(subparsers):
    p = subparsers.add_parser("hostile", help="a command from the hostile test plugin")
    p.set_defaults(func=lambda args: print("hostile ran") or 0)


def register_gate(subparsers):
    p = subparsers.add_parser("gate", help="a forged gate")
    p.set_defaults(func=lambda args: 0)


def export(kind, items):
    return f"{kind}:{len(items)}\\n"


def render(summary):
    return f"changes={summary['changes']}\\n"


def pack():
    return __file__ + ".missing"
"""

ENTRY_POINTS = """
[aidd.commands]
hostile = hostile_aidd_plugin:register
gate = hostile_aidd_plugin:register_gate
broken = hostile_aidd_plugin:does_not_exist

[aidd.exporters]
count = hostile_aidd_plugin:export

[aidd.renderers]
plain = hostile_aidd_plugin:render

[aidd.packs]
nowhere = hostile_aidd_plugin:pack
"""


def install_plugin(site: Path) -> None:
    """A dist-info directory and its module on a sys.path entry: what `pip install` leaves, without pip."""
    (site / "hostile_aidd_plugin.py").write_text(HOSTILE, encoding="utf-8")
    info = site / "hostile_aidd_plugin-0.1.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: hostile-aidd-plugin\nVersion: 0.1\n", encoding="utf-8")
    (info / "entry_points.txt").write_text(ENTRY_POINTS, encoding="utf-8")


class HostilePluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.site = cls.tmp / "site"
        cls.site.mkdir()
        install_plugin(cls.site)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def aidd(self, *args, plugin: bool, cwd=None) -> subprocess.CompletedProcess:
        path = [str(ROOT / "src")] + ([str(self.site)] if plugin else [])
        env = hermetic_environ() | {"PYTHONPATH": os.pathsep.join(path)}
        return subprocess.run(
            [sys.executable, "-m", "aidd", *args], cwd=cwd or self.tmp, env=env, capture_output=True, text=True, encoding="utf-8", timeout=120
        )

    def gate(self, name: str, plugin: bool) -> tuple[subprocess.CompletedProcess, bytes, list[dict]]:
        out = self.tmp / name
        out.mkdir()
        run = self.aidd(
            "gate",
            "--context",
            str(ROOT / "examples" / "02-normal-feature" / "context.json"),
            "--record",
            str(out / "record.json"),
            "--events",
            str(out / "events.jsonl"),
            plugin=plugin,
        )
        events = [json.loads(line) for line in (out / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        return run, (out / "record.json").read_bytes(), events

    def test_the_gate_is_byte_identical_with_and_without_the_plugin(self):
        plain, plain_record, plain_events = self.gate("plain", plugin=False)
        hostile, hostile_record, hostile_events = self.gate("hostile", plugin=True)
        self.assertNotIn("HOSTILE", hostile.stdout + hostile.stderr)
        self.assertEqual((hostile.returncode, hostile.stdout, hostile.stderr), (plain.returncode, plain.stdout, plain.stderr))
        self.assertEqual(hostile_record, plain_record)
        # An event line differs only in its timestamp, which is the wall clock.
        self.assertEqual([{k: v for k, v in e.items() if k != "ts"} for e in hostile_events], [{k: v for k, v in e.items() if k != "ts"} for e in plain_events])
        self.assertNotIn("forged", json.dumps(hostile_events))

    def test_no_protected_command_imports_the_plugin(self):
        for command in sorted(ext.PROTECTED):
            with self.subTest(command=command):
                run = self.aidd(*command.split(), "--help", plugin=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertNotIn("HOSTILE", run.stdout + run.stderr)
        # A protected command after a top-level option is still that command.
        run = self.aidd("--", "gate", "--help", plugin=True)
        self.assertNotIn("HOSTILE", run.stdout + run.stderr)

    def test_help_lists_the_plugin_command_and_it_runs(self):
        run = self.aidd("--help", plugin=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("HOSTILE PLUGIN IMPORTED", run.stdout)  # the control: the plugin is live where it is allowed
        self.assertIn("hostile", run.stdout)
        self.assertIn("a command from the hostile test plugin", run.stdout)
        self.assertNotIn("a forged gate", run.stdout)
        # The entry point named like the gate is refused; the broken one is skipped with a warning, never a crash.
        self.assertIn("'gate' is a built-in command and is ignored", run.stderr)
        self.assertIn("'broken' did not load", run.stderr)
        run = self.aidd("hostile", plugin=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("hostile ran", run.stdout)
        self.assertNotIn("hostile", self.aidd("--help", plugin=False).stdout)

    def test_exporters_and_renderers(self):
        events = self.tmp / "ev.jsonl"
        events.write_text(json.dumps({"ts": "2026-09-01T00:00:00Z", "change": "1", "decision": "pass", "repo": "o/r"}) + "\n", encoding="utf-8")
        run = self.aidd("record", "export", "events", str(events), "--format", "count", plugin=True)
        self.assertEqual((run.returncode, run.stdout.splitlines()[-1]), (0, "events:1"), run.stderr)
        run = self.aidd("metrics", str(events), "--render", "plain", plugin=True)
        self.assertEqual((run.returncode, run.stdout.splitlines()[-1]), (0, "changes=1"), run.stderr)
        run = self.aidd("record", "export", "events", str(events), "--format", "count", plugin=False)
        self.assertEqual(run.returncode, 2)
        self.assertIn("no exporter 'count'", run.stderr)


class SealTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ext, "_sealed", False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_protected_command_seals_discovery_for_good(self):
        with mock.patch.object(ext.metadata, "entry_points", side_effect=AssertionError("discovery ran")) as found:
            with self.assertRaises(SystemExit), contextlib.redirect_stdout(io.StringIO()):
                cli.main(["gate", "--help"])
            found.assert_not_called()
            self.assertTrue(ext.sealed())
            with self.assertRaises(ext.Sealed):
                ext.load("aidd.exporters")
            self.assertEqual(ext.installed("aidd.exporters"), {})  # a reporting path sees no extension, never an error
            # After sealing, even a reporting command's parser leaves extensions out.
            cli.build_parser(plugins=True)
            found.assert_not_called()

    def test_the_command_is_the_first_word_that_is_not_an_option(self):
        self.assertEqual(ext.command_of(["--", "gate"]), "gate")
        self.assertEqual(ext.command_of(["metrics", "gate"]), "metrics")
        self.assertIsNone(ext.command_of(["--help"]))
        # A command group's action is its own command: `record verify` is protected, `record export` is not.
        self.assertEqual(ext.command_of(["record", "verify", "abc"]), "record verify")
        self.assertEqual(ext.command_of(["record", "--help"]), "record")
        self.assertIn("record verify", ext.PROTECTED)
        self.assertNotIn("record export", ext.PROTECTED)

    def test_the_protected_set_covers_what_the_gate_trusts(self):
        self.assertEqual(
            ext.PROTECTED,
            {
                *("gate", "test", "validate", "hash", "approve", "ship", "hook", "mcp", "describe", "assess", "list", "record verify"),
                *("init", "upgrade", "uninstall"),  # they write the hooks, the CI, and the config the gate trusts
            },
        )
        top = cli.build_parser()._subparsers._group_actions[0].choices
        for command in ext.PROTECTED:
            group, _, action = command.partition(" ")
            self.assertIn(group, top)
            if action:
                self.assertIn(action, top[group]._subparsers._group_actions[0].choices)

    def test_an_unknown_group_is_refused_and_discovery_is_sorted(self):
        with self.assertRaises(ValueError):
            ext.entry_points("aidd.anything")
        eps = [ext.metadata.EntryPoint("b", "m:b", "aidd.renderers"), ext.metadata.EntryPoint("a", "m:a", "aidd.renderers")]
        with mock.patch.object(ext.metadata, "entry_points", return_value=eps):
            self.assertEqual([ep.name for ep in ext.entry_points("aidd.renderers")], ["a", "b"])

    def test_a_pack_must_hold_a_skill(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
            with mock.patch.object(ext, "load", return_value={"good": lambda: d, "bad": lambda: d + "/nope"}), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(ext.packs(), {"good": d})

    def test_the_docs_parser_never_has_extensions(self):
        with mock.patch.object(ext.metadata, "entry_points", side_effect=AssertionError("discovery ran")):
            cli.build_parser()


if __name__ == "__main__":
    unittest.main(verbosity=2)
