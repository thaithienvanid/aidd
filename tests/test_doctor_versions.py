"""`aidd doctor` says when the aidd in play is of different shapes, and never guesses.

The invariant: the aidd plugins are installed for the user, so one `claude plugin update` moves the skill, the roles, and the MCP
tools of every project at once, while the `aidd` command and each repository's files stay as they were. Doctor reads the versions
it can see in files, with no network call and no program: this aidd's own, the enabled plugin's (the skill in the folder Claude
Code installed it to), and the skill vendored in the repository (the one text every harness reads). When the plugin or the
vendored skill is newer than the command, it says to update the command. When the plugin is older, it says to update the plugin.
It says nothing for equal versions, for a version it cannot read, or for a plugin that is not enabled. It also counts the names
aidd retired that a file holds while the config loads, and names `aidd upgrade --yes`. Each case below is a line in the output
of `doctor`, and the table of cases fails when one note is taken out."""

import contextlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, make_repo

from aidd import __version__, config
from aidd.setup import doctor_checks, doctor_probes

OLDER, NEWER = "0.0.1", "99.0.0"
PM = (ROOT / "tests" / "fixtures" / "migration" / "pre" / "docs" / "postmortems" / "PM-1.md").read_text(encoding="utf-8")


def skill_text(version: str | None) -> str:
    meta = f'metadata:\n  version: "{version}"\n' if version else ""
    return f'---\nname: aidd\ndescription: "x"\n{meta}---\n\n# aidd\n'


def lines(root: Path) -> list[str]:
    return [message for level, message in doctor_checks.doctor(root) if level == "warn"]


def has(found: list[str], words: str) -> list[str]:
    return [m for m in found if words in m]


def skew(found: list[str]) -> list[str]:
    """The lines that compare the versions of aidd: each says "than this aidd"."""
    return has(found, "than this aidd")


@contextlib.contextmanager
def claude_home(root: Path, *, enabled: bool = True, installed: object = "ok", version: str | None = __version__):
    """A Claude Code folder with the aidd plugin installed at `version` and, when `enabled`, switched on; `installed` is the
    plugin record's text (`ok` writes the record for the folder), or anything else the file should hold."""
    with tempfile.TemporaryDirectory() as d:
        home = Path(d).resolve()
        folder = home / "plugins" / "cache" / "aidd" / "aidd" / "abc123"
        skill = folder / ".agents" / "skills" / "aidd" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(skill_text(version), encoding="utf-8")
        (home / "settings.json").write_text(json.dumps({"enabledPlugins": {f"aidd@{config.MARKETPLACE}": enabled}}), encoding="utf-8")
        record = {"version": 2, "plugins": {f"aidd@{config.MARKETPLACE}": [{"scope": "user", "installPath": str(folder), "version": "abc123"}]}}
        (home / "plugins" / "installed_plugins.json").write_text(json.dumps(record) if installed == "ok" else str(installed), encoding="utf-8")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(home)}):
            yield home


class ThePluginAndTheCommand(unittest.TestCase):
    """The enabled plugin against this aidd: say which to update when they differ, and nothing when they do not or when no
    version reads."""

    CASES = (
        # (what the case is, the plugin's version, keywords of its settings, the words the one line holds or None)
        ("same versions", __version__, {}, None),
        ("the plugin is newer", NEWER, {}, ("newer than this aidd", "aidd self-update", NEWER, __version__)),
        ("the command is newer", OLDER, {}, ("older than this aidd", "claude plugin update aidd@aidd", OLDER, __version__)),
        ("the skill names no version", None, {}, None),
        ("the record cannot be read", NEWER, {"installed": "{not json"}, None),
        ("the record names no plugin", NEWER, {"installed": json.dumps({"plugins": {}})}, None),
        ("the plugin is not enabled", NEWER, {"enabled": False}, None),
    )

    def test_each_case_says_what_it_should_in_one_line(self):
        for label, version, kwargs, words in self.CASES:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                with claude_home(root, version=version, **kwargs):
                    found = [m for _, m in doctor_probes.version_lines(root)]
                if words is None:
                    self.assertEqual(found, [])
                else:
                    [one] = found
                    for word in words:
                        self.assertIn(word, one)

    def test_the_whole_doctor_says_it_once_and_a_failures_only_run_leaves_it_out(self):
        for version, words in ((NEWER, "aidd self-update"), (OLDER, "claude plugin update")):
            with self.subTest(plugin=version), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                with claude_home(root, version=version):
                    full = skew(lines(root))
                    brief = skew([m for level, m in doctor_checks.doctor(root, failures_only=True)])
                self.assertEqual(len(full), 1, full)
                self.assertIn(words, full[0])
                self.assertEqual(brief, [], "a note that only warns is left out of a failures-only run")

    def test_a_version_too_long_to_be_one_and_a_record_nested_too_deep_say_nothing(self):
        """The skill file and the record are files' text, so doctor reads a version only in its short shape and a record only when
        it reads: anything else is no version, never a long line or a crash."""
        deep = "[" * 200_000 + "]" * 200_000
        cases = {
            "a suffix of 33 characters": {"version": "99.0.0-" + "a" * 33},
            "a suffix that carries words past the limit": {"version": "99.0.0-" + ".".join(["run"] * 20)},
            "a number of seven digits": {"version": "9999999.0.0"},
            "a record nested too deep to read": {"version": NEWER, "installed": deep},
        }
        for name, how in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                with claude_home(root, **how):
                    self.assertIsNone(doctor_probes.plugin_version(root))
                    self.assertEqual(doctor_probes.version_lines(root), [])
        self.assertEqual(doctor_probes.skill_version(skill_text("99.0.0-" + "a" * 32)), "99.0.0-" + "a" * 32, "a suffix at the limit is a version")

    def test_two_folders_of_two_versions_say_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
            with claude_home(root, version=NEWER) as home:
                other = home / "plugins" / "cache" / "aidd" / "aidd" / "def456" / ".agents" / "skills" / "aidd"
                other.mkdir(parents=True)
                (other / "SKILL.md").write_text(skill_text(OLDER), encoding="utf-8")
                record = json.loads((home / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
                key = f"aidd@{config.MARKETPLACE}"
                record["plugins"][key].append({"scope": "project", "installPath": str(other.parents[2])})
                (home / "plugins" / "installed_plugins.json").write_text(json.dumps(record), encoding="utf-8")
                self.assertIsNone(doctor_probes.plugin_version(root))
                self.assertEqual(doctor_probes.version_lines(root), [])


class TheVendoredSkillAndTheCommand(unittest.TestCase):
    """The skill vendored in the repository is the one text every harness reads, so a newer one than this aidd gets the same
    line whichever harness the repository wires."""

    def test_a_newer_skill_says_to_update_the_command_for_every_harness(self):
        for key in config.HARNESSES:
            with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(Path(d) / "no-claude")}):
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None, harnesses=[key])
                skill = root / ".agents" / "skills" / "aidd" / "SKILL.md"
                skill.parent.mkdir(parents=True, exist_ok=True)
                for version, found in ((NEWER, True), (__version__, False), (OLDER, False), (None, False)):
                    with self.subTest(harness=key, skill=version):
                        skill.write_text(skill_text(version), encoding="utf-8")
                        said = [m for _, m in doctor_probes.version_lines(root)]
                        self.assertEqual(len(said), 1 if found else 0, said)
                        if found:
                            self.assertIn("aidd self-update", said[0])
                            self.assertIn(NEWER, said[0])
                            self.assertEqual(skew(lines(root)), said, "the whole doctor says it too")

    def test_the_plugin_and_the_skill_both_newer_make_one_line(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
            skill = root / ".agents" / "skills" / "aidd" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(skill_text(NEWER), encoding="utf-8")
            with claude_home(root, version=NEWER):
                said = skew(lines(root))
        self.assertEqual(len(said), 1, said)
        self.assertIn("the aidd plugin", said[0])
        self.assertIn("the skill in this repository", said[0])


class RetiredNamesInFilesThatLoad(unittest.TestCase):
    """A file with a name aidd retired, while the config loads, gets one line with the count and `aidd upgrade --yes`."""

    def test_the_count_follows_the_files_and_none_gives_no_line(self):
        cases = (("no retired name", {}, None), ("one", {"docs/postmortems/PM-1.md": PM}, "1 name aidd retired is still in 1 file"))
        for label, files, words in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                for rel, text in files.items():
                    (root / rel).parent.mkdir(parents=True, exist_ok=True)
                    (root / rel).write_text(text, encoding="utf-8")
                said = has(lines(root), "aidd retired")
                said = [m for m in said if "standards" not in m]
                if words is None:
                    self.assertEqual(said, [])
                else:
                    [one] = said
                    self.assertIn(words, one)
                    self.assertIn("aidd upgrade --yes", one)

    def test_a_config_that_does_not_load_has_its_own_failure_and_no_second_line(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
            path = root / ".aidd" / "config.yaml"
            path.write_text(path.read_text(encoding="utf-8") + "tests:\n  - {name: t, command: x, retries: 1}\n", encoding="utf-8")
            results = doctor_checks.doctor(root)
        self.assertEqual([m for level, m in results if level == "fail" and "retries" in m and "aidd upgrade --yes" in m] != [], True)
        self.assertEqual(has([m for _, m in results], "still in"), [])


if __name__ == "__main__":
    unittest.main()
