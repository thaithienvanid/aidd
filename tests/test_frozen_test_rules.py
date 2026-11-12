"""An approved Spec's acceptance tests are frozen, so each harness with a file-edit ask rule asks before its own
edit tool changes one. `aidd upgrade --yes` writes the rules from the Spec files, the way it writes the push rules from the
default branch, and takes them out when the Spec is done or revised. A shell write (`sed -i`) is no edit tool, so the
rule may miss it. `aidd validate` and `aidd test` compare no test with its approved form: a person's review and a
delegated merge's check (`delegation.local_run.frozen_problem`) hold it then."""

from __future__ import annotations

import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import helpers
from aidd import risk, workitems
from aidd.risk import harness_rules
from aidd.workitems import frozen_tests
from aidd.setup import adoption, doctor_harnesses, upgrading

SPEC = "specs/SPEC-220.md"
TEST = "tests/test_discount.py"
EDIT_HARNESSES = ("claude-code", "grok", "opencode")
NO_EDIT_HARNESSES = ("codex", "vscode", "qwen")
ALL = EDIT_HARNESSES + NO_EDIT_HARNESSES  # the ask-rule formats
HARNESS_KEYS = ("claude-code", "grok-build", "opencode", "codex", "copilot", "qwen-code")  # the agents that write them


def entries(root: Path, fmt: str) -> list[str]:
    """What a harness's ask rules hold for a file edit, each as the harness reads it."""
    path = root / harness_rules.FORMATS[fmt].path
    if not path.is_file():
        return []
    if fmt == "grok":
        return [e for e in tomllib.loads(path.read_text())["permission"]["ask"] if e.startswith("Edit(")]
    if fmt in NO_EDIT_HARNESSES:
        return ["test_discount"] if "test_discount" in path.read_text() else []
    data = json.loads(path.read_text())
    if fmt == "opencode":
        return [r["resource"] for r in data.get("permissions", []) if r["action"] == "edit"]
    return [e for e in data.get("permissions", {}).get("ask", []) if e.startswith("Edit(")]


def repo(tmp: str, status: str) -> Path:
    return helpers.make_repo(Path(tmp).resolve() / "repo", spec=SPEC, status=status, branch=None, harnesses=list(HARNESS_KEYS))


def upgrade(root: Path) -> None:
    upgrading.upgrade(root, ref="v1.0.0", yes=True)


class ASpecPastApprovalHasFrozenTests(unittest.TestCase):
    """A Spec's tests are frozen from Spec approval until it is done, rolled back, cancelled, or revised to a draft."""

    def frozen(self, status: str, files: list[str] | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, status)
            if files is not None:
                path = root / SPEC
                path.write_text(path.read_text().replace('files: ["tests/test_discount.py"]', f"files: {json.dumps(files)}"))
            return workitems.frozen_test_files(root, None).paths

    def test_a_spec_past_approval_and_not_finished_guards_its_tests(self):
        for status, want in (
            ("draft", []),
            ("ready", []),
            ("approved", [TEST]),
            ("in_progress", [TEST]),
            ("in_review", [TEST]),
            ("done", []),
            ("rolled_back", []),
            ("cancelled", []),
        ):
            with self.subTest(status=status):
                self.assertEqual(self.frozen(status), want)

    def test_a_test_section_of_a_manifest_is_left_to_the_hash(self):
        """A rule on `pyproject.toml` would ask at every dependency bump."""
        self.assertEqual(self.frozen("approved", [TEST, "pyproject.toml#tool.pytest"]), [TEST])

    def test_a_path_that_is_no_repository_glob_is_dropped(self):
        for bad in ("/etc/passwd", "../outside.py", "tests/../../x.py", ""):
            with self.subTest(path=bad):
                self.assertEqual(self.frozen("approved", [TEST, bad]), [TEST])


class TheEditRulesAreThePathsAsEachHarnessReadsThem(unittest.TestCase):
    def test_a_path_with_no_wildcard_covers_what_is_under_it(self):
        self.assertEqual(
            risk.harness_edit_paths(["tests/acceptance", "tests/test_*.py", ".claude/**"]),
            [
                "tests/acceptance",
                "tests/acceptance/**",
                "tests/test_*.py",
                ".claude",
                ".claude/**",
            ],
        )

    def test_a_character_a_harness_reads_as_syntax_gets_no_rule(self):
        """A bracket is a class in gitignore, and a space or a parenthesis breaks the rule's own text, so the hash alone
        guards that file."""
        for bad in ("tests/[id].test.ts", "tests/my test.py", "tests/a(1).py", "tests/{a,b}.py", "tests/a\\b.py", "tests/café.py", "tests/a\nb.py"):
            with self.subTest(path=bad):
                self.assertEqual(risk.harness_edit_paths([bad]), [])

    def test_each_format_anchors_the_path_as_its_docs_say(self):
        paths = risk.harness_edit_paths([TEST])
        with tempfile.TemporaryDirectory() as tmp:
            for fmt, want in (
                ("claude-code", f"Edit(/{TEST})"),  # `/path` is the project root in project settings
                ("grok", f"Edit(**/{TEST})"),  # its docs say nothing of the anchor, so any depth
                ("opencode", f"Edit(*{TEST})"),  # its `*` spans `/`, so the relative and the absolute form both match
            ):
                with self.subTest(fmt=fmt):
                    risk.apply_harness_rules(Path(tmp), fmt, [], edit_paths=paths)
                    self.assertIn(want, json.loads((Path(tmp) / ".aidd/harness-rules.json").read_text())[fmt])


class UpgradeWritesTheRulesFromTheSpecFiles(unittest.TestCase):
    def test_an_approved_specs_test_file_asks_in_each_harness_with_an_edit_rule(self):
        for status in ("approved", "in_progress", "in_review"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = repo(tmp, status)
                upgrade(root)
                for fmt in EDIT_HARNESSES:
                    self.assertTrue(any(TEST in e for e in entries(root, fmt)), fmt)
                for fmt in NO_EDIT_HARNESSES:
                    self.assertEqual(entries(root, fmt), [], fmt)
                self.assertTrue(all(harness_rules.FORMATS[f].edits for f in EDIT_HARNESSES))
                self.assertEqual(sorted(f for f, spec in harness_rules.FORMATS.items() if spec.edits), sorted(EDIT_HARNESSES))

    def test_a_draft_specs_test_file_gets_none(self):
        for status in ("draft", "ready"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                root = repo(tmp, status)
                upgrade(root)
                for fmt in ALL:
                    self.assertEqual(entries(root, fmt), [], fmt)

    def test_a_done_specs_rule_is_removed_on_the_next_upgrade(self):
        for later in ("done", "draft"):  # merged, or revised by `spec.revise`
            with self.subTest(later=later), tempfile.TemporaryDirectory() as tmp:
                root = repo(tmp, "approved")
                upgrade(root)
                path = root / SPEC
                path.write_text(path.read_text().replace('status: "approved"', f'status: "{later}"'))
                upgrade(root)
                for fmt in EDIT_HARNESSES:
                    self.assertEqual(entries(root, fmt), [], fmt)
                self.assertNotIn("test_discount", (root / ".aidd/harness-rules.json").read_text())

    def test_a_second_upgrade_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            upgrade(root)
            before = {f: (root / harness_rules.FORMATS[f].path).read_bytes() for f in EDIT_HARNESSES}
            upgrade(root)
            self.assertEqual({f: (root / harness_rules.FORMATS[f].path).read_bytes() for f in EDIT_HARNESSES}, before)

    def test_a_person_s_own_edit_rule_stays_when_the_spec_is_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            upgrade(root)
            cfg = root / ".claude/settings.json"
            data = json.loads(cfg.read_text())
            data["permissions"]["ask"].append("Edit(/docs/**)")
            cfg.write_text(json.dumps(data))
            path = root / SPEC
            path.write_text(path.read_text().replace('status: "approved"', 'status: "done"'))
            upgrade(root)
            self.assertEqual(entries(root, "claude-code"), ["Edit(/docs/**)"])

    def test_uninstall_takes_the_edit_rules_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            upgrade(root)
            risk.remove_harness_rules(root)
            for fmt in EDIT_HARNESSES:
                self.assertEqual(entries(root, fmt), [], fmt)


class OpenCodeWritesItsAsksOnlyBesideNoEditRuleOfTheirs(unittest.TestCase):
    """OpenCode applies the last rule that matches, so an ask among a person's own edit rules raises ordering cases. aidd
    appends its asks when the file holds none of theirs, and writes none otherwise, and `aidd doctor` says why."""

    ASK = {"action": "edit", "resource": "*tests/test_discount.py", "effect": "ask"}
    SHELL_ALLOW = {"action": "shell", "resource": "*", "effect": "allow"}
    # Each way a person holds an edit rule, so one of aidd's asks would have to be ordered around it.
    THEIRS = {
        "a native deny": {"permissions": [{"action": "edit", "resource": "tests/*", "effect": "deny"}]},
        "a native allow": {"permissions": [{"action": "edit", "resource": "docs/*", "effect": "allow"}]},
        "a native allow for every action": {"permissions": [{"action": "*", "resource": "*", "effect": "allow"}]},
        "a native write rule": {"permissions": [{"action": "write", "resource": "docs/*", "effect": "allow"}]},
        "a v1 edit object": {"permission": {"edit": {"tests/test_a.py": "deny"}}},
        "a v1 edit string": {"permission": {"edit": "allow"}},
        "a v1 write rule": {"permission": {"write": "allow"}},
        "a v1 string for every action": {"permission": "allow"},
        "a v1 tool switch": {"tools": {"edit": False}},
        "an agent's rule": {"agent": {"build": {"permission": {"edit": "deny"}}}},
    }

    def written(self, data: dict, paths: list[str] | None = None, *, write: bool = True) -> tuple[dict, list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opencode.json").write_text(json.dumps(data))
            done = risk.apply_harness_rules(root, "opencode", [], edit_paths=paths or [TEST], write=write)
            return json.loads((root / "opencode.json").read_text()), done

    def test_with_no_edit_rule_of_theirs_the_asks_are_appended(self):
        theirs = [self.SHELL_ALLOW]
        data, _ = self.written({"permissions": theirs, "permission": {"bash": {"ls": "allow"}}})
        self.assertEqual(data["permissions"], [*theirs, self.ASK])
        self.assertEqual(self.written({})[0]["permissions"], [self.ASK])

    def test_with_an_edit_rule_of_theirs_none_is_written_and_the_file_is_left_as_it_was(self):
        for how, data in self.THEIRS.items():
            with self.subTest(how):
                after, done = self.written(data)
                self.assertEqual(after, data)
                self.assertTrue(any(d.startswith("kept") and "edit rules of your own" in d for d in done), done)

    def test_without_a_frozen_test_there_is_nothing_to_say(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opencode.json").write_text(json.dumps(self.THEIRS["a native deny"]))
            self.assertEqual(risk.apply_harness_rules(root, "opencode", [], edit_paths=[], write=False), [])

    def test_an_edit_rule_added_later_takes_aidds_asks_out_and_the_rule_stays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            risk.apply_harness_rules(root, "opencode", [], edit_paths=[TEST])
            cfg = root / "opencode.json"
            data = json.loads(cfg.read_text())
            mine = {"action": "edit", "resource": "docs/*", "effect": "allow"}
            data["permissions"].append(mine)
            cfg.write_text(json.dumps(data))
            risk.apply_harness_rules(root, "opencode", [], edit_paths=[TEST])
            self.assertEqual(json.loads(cfg.read_text())["permissions"], [mine])


class DoctorSaysWhenTheRulesLagTheSpecs(unittest.TestCase):
    def lines(self, root: Path) -> list[tuple[str, str]]:
        return doctor_harnesses.harness_checks(root, adoption.detect_harnesses(root))

    def test_an_approved_spec_with_no_rule_yet_is_not_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            self.assertTrue(any(level == "warning" and "not current" in text for level, text in self.lines(root)))
            upgrade(root)
            self.assertFalse(any(level == "warning" and "not current" in text for level, text in self.lines(root)))

    def test_opencode_with_an_edit_rule_of_its_own_says_why_it_has_no_ask(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            (root / "opencode.json").write_text(json.dumps({"permissions": [{"action": "edit", "resource": "docs/*", "effect": "allow"}]}))
            text = "\n".join(t for _, t in self.lines(root))
            self.assertRegex(text, "OpenCode v2: .*edit rules of your own")
            self.assertEqual(entries(root, "opencode"), ["docs/*"])

    def test_a_harness_without_an_edit_rule_says_no_ask_guards_the_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            upgrade(root)
            text = "\n".join(t for _, t in self.lines(root))
            for label in ("Codex", "Qwen Code"):
                self.assertRegex(text, f"{label}: no ask rule guards the frozen tests")


CONFLICT = '<<<<<<< HEAD\nstatus: "approved"\n=======\nstatus: "in_progress"\n>>>>>>> feat'


def claude_ask(root: Path) -> list[str]:
    return json.loads((root / ".claude/settings.json").read_text())["permissions"]["ask"]


def set_status(root: Path, old: str, new: str) -> None:
    path = root / SPEC
    path.write_text(path.read_text().replace(f'status: "{old}"', f'status: "{new}"'))


class AnEntryAiddDropsTakesOnlyItsOwnCopies(unittest.TestCase):
    """F1. Claude Code's record keeps one copy of an entry for each copy aidd wrote, so a person's identical copy, which sits
    after aidd's block, is never dropped with it."""

    def claude_repo(self, tmp: str, status: str) -> Path:
        return helpers.make_repo(Path(tmp).resolve() / "repo", spec=SPEC, status=status, branch=None, harnesses=["claude-code"])

    def test_a_person_s_identical_edit_rule_survives_its_spec_going_done(self):
        mine = ["Edit(/tests/test_discount.py)", "Edit(/tests/test_discount.py/**)"]
        with tempfile.TemporaryDirectory() as tmp:
            root = self.claude_repo(tmp, "draft")
            upgrade(root)
            cfg = root / ".claude/settings.json"
            data = json.loads(cfg.read_text())
            data["permissions"]["ask"] += mine
            cfg.write_text(json.dumps(data))
            set_status(root, "draft", "approved")
            upgrade(root)
            self.assertEqual([e for e in claude_ask(root) if e.startswith("Edit(")], mine + mine)
            set_status(root, "approved", "done")
            upgrade(root)
            self.assertEqual([e for e in claude_ask(root) if e.startswith("Edit(")], mine)

    def test_the_hostile_chain_leaves_the_team_s_own_rule(self):
        """A Spec lists the team's own folder as its tests, is approved, and is cancelled."""
        team = "Edit(/.github/workflows/**)"
        with tempfile.TemporaryDirectory() as tmp:
            root = self.claude_repo(tmp, "draft")
            upgrade(root)
            cfg = root / ".claude/settings.json"
            data = json.loads(cfg.read_text())
            data["permissions"]["ask"].append(team)
            cfg.write_text(json.dumps(data))
            path = root / SPEC
            path.write_text(
                path.read_text().replace('status: "draft"', 'status: "approved"').replace('files: ["tests/test_discount.py"]', 'files: [".github/workflows/"]')
            )
            upgrade(root)
            set_status(root, "approved", "cancelled")
            upgrade(root)
            self.assertEqual([e for e in claude_ask(root) if e.startswith("Edit(")], [team])

    def test_a_person_s_identical_command_rule_survives_when_the_config_drops_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            risk.apply_harness_rules(root, "claude-code", ["git tag*"])
            cfg = root / ".claude/settings.json"
            data = json.loads(cfg.read_text())
            data["permissions"]["ask"].append("Bash(git tag*)")
            cfg.write_text(json.dumps(data))
            risk.apply_harness_rules(root, "claude-code", [])
            self.assertEqual(claude_ask(root), ["Bash(git tag*)"])


class AnUnreadableSpecKeepsTheRulesAsTheyWere(unittest.TestCase):
    """F2. While a Spec file does not parse, aidd cannot tell what is approved, so an upgrade keeps the edit asks it wrote and
    names the file, and doctor names it in place of saying to run the upgrade."""

    def broken(self, tmp: str) -> Path:
        root = repo(tmp, "approved")
        upgrade(root)
        path = root / SPEC
        path.write_text(path.read_text().replace('status: "approved"', CONFLICT))
        return root

    def test_the_recorded_edit_asks_stay_and_the_file_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.broken(tmp)
            before = {f: entries(root, f) for f in EDIT_HARNESSES}
            self.assertTrue(all(before.values()))
            said = "\n".join(upgrading.upgrade(root, ref="v1.0.0", yes=True))
            self.assertIn(SPEC, said)
            self.assertEqual({f: entries(root, f) for f in EDIT_HARNESSES}, before)

    def test_doctor_names_the_file_in_place_of_the_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.broken(tmp)
            lines = doctor_harnesses.harness_checks(root, adoption.detect_harnesses(root))
            text = "\n".join(t for _, t in lines)
            self.assertIn(SPEC, text)
            self.assertFalse(any("not current" in t for _, t in lines), text)

    def test_a_fixed_spec_is_read_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.broken(tmp)
            path = root / SPEC
            path.write_text(path.read_text().replace(CONFLICT, 'status: "done"'))
            upgrade(root)
            self.assertEqual({f: entries(root, f) for f in EDIT_HARNESSES}, dict.fromkeys(EDIT_HARNESSES, []))


class AtMostSoManyTestFilesAreGuarded(unittest.TestCase):
    """F3. A Spec that lists more files than the cap gets the first ones, and doctor names the Spec."""

    def test_the_cap_and_the_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = repo(tmp, "approved")
            path = root / SPEC
            path.write_text(path.read_text().replace('files: ["tests/test_discount.py"]', 'files: ["tests/a.py", "tests/b.py", "tests/c.py"]'))
            with mock.patch.object(frozen_tests, "MAX_FROZEN", 2):
                found = workitems.frozen_test_files(root, None)
                self.assertEqual(found.paths, ["tests/a.py", "tests/b.py"])
                self.assertEqual(found.over_cap, SPEC)
                text = "\n".join(t for _, t in doctor_harnesses.harness_checks(root, adoption.detect_harnesses(root)))
                self.assertIn(SPEC, text)
                self.assertIn("2", text)


class AnOverCapSpecKeepsTheOthersAsks(unittest.TestCase):
    """N1. The cap is shared by all Specs in file order, so a Spec that lists many junk paths must not push another Spec's real
    asks out. Over the cap, an upgrade keeps the asks it wrote, as for an unreadable Spec, and names the Spec with the most paths."""

    def two_specs(self, tmp: str, junk: str = "SPEC-001") -> Path:
        root = repo(tmp, "approved")
        upgrade(root)
        files = ", ".join(f'"junk/{n}.py"' for n in range(3))
        text = (
            helpers.SAMPLE_SPEC.replace("SPEC-220", junk)
            .replace('files: ["tests/test_discount.py"]', f"files: [{files}]")
            .replace("\nroute: ", '\nstatus: "approved"\nroute: ', 1)
        )
        (root / "specs" / f"{junk}.md").write_text(text)
        return root

    def test_the_other_specs_ask_stays_and_the_biggest_spec_is_named(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(frozen_tests, "MAX_FROZEN", 2):
            root = self.two_specs(tmp)
            said = "\n".join(upgrading.upgrade(root, ref="v1.0.0", yes=True))
            for fmt in EDIT_HARNESSES:
                self.assertTrue(any(TEST in e for e in entries(root, fmt)), fmt)
                self.assertFalse(any("junk" in e for e in entries(root, fmt)), fmt)
            self.assertIn("specs/SPEC-001.md", said)
            text = "\n".join(t for _, t in doctor_harnesses.harness_checks(root, adoption.detect_harnesses(root)))
            self.assertIn("specs/SPEC-001.md", text)
            self.assertFalse(any("not current" in t for _, t in doctor_harnesses.harness_checks(root, adoption.detect_harnesses(root))), text)


class APersonSRuleIsNeverPrintedRaw(unittest.TestCase):
    """F4. A rule key from the person's file reaches a terminal through doctor and upgrade, so no control character does."""

    BAD = "x\x1b]0;PWNED\x07y"

    def test_the_edit_rule_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opencode.json").write_text(json.dumps({"permission": {"edit": {self.BAD: "deny"}}}))
            done = risk.apply_harness_rules(root, "opencode", [], edit_paths=[TEST], write=False)
            text = "\n".join(done)
            self.assertIn("edit rules of your own", text)
            self.assertFalse({"\x1b", "\x07"} & set(text), repr(text))

    def test_the_shadow_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "opencode.json").write_text(
                json.dumps({"permission": {"bash": {"git push*": "allow"}}, "agent": {self.BAD: {"permission": {"bash": {"git push*": "allow"}}}}})
            )
            text = "\n".join(risk.opencode_shadow_warnings(root, ["git push*"]))
            self.assertIn("run with no prompt", text)
            self.assertFalse({"\x1b", "\x07"} & set(text), repr(text))


class ASpecPathIsNeverPrintedRaw(unittest.TestCase):
    """N2. A Spec file's name reaches a terminal through upgrade and doctor, so no control character does."""

    BAD = "SPEC-9\x1b]0;PWNED\x07x"

    def test_an_unreadable_spec_and_an_over_cap_spec(self):
        for how, patch_cap in (("unreadable", False), ("over the cap", True)):
            with self.subTest(how), tempfile.TemporaryDirectory() as tmp, mock.patch.object(frozen_tests, "MAX_FROZEN", 2 if patch_cap else 500):
                root = repo(tmp, "approved")
                files = '"a.py", "b.py", "c.py"' if patch_cap else '"a.py"'
                text = helpers.SAMPLE_SPEC.replace("SPEC-220", "SPEC-9").replace('files: ["tests/test_discount.py"]', f"files: [{files}]")
                text = text.replace("\nroute: ", '\nstatus: "approved"\nroute: ', 1)
                if not patch_cap:
                    text = text.replace('status: "approved"', '<<<<<<< HEAD\nstatus: "approved"\n=======\nx\n>>>>>>> y')
                (root / "specs" / f"{self.BAD}.md").write_text(text)
                said = "\n".join(
                    upgrading.upgrade(root, ref="v1.0.0", yes=True) + [t for _, t in doctor_harnesses.harness_checks(root, adoption.detect_harnesses(root))]
                )
                self.assertIn("PWNED", said)
                self.assertFalse({"\x1b", "\x07"} & set(said), repr(said))


class NoPageClaimsAComparisonTheCodeDoesNotRun(unittest.TestCase):
    """Invariant: every sentence that names a control for a frozen test names one the code runs. `aidd validate` and
    `aidd test` hold no comparison of a test file with its approved form, so no page may say a "frozen-test hash" catches
    an edit. What does hold one is the delegated merge's `frozen_problem`."""

    LEFTOVER = re.compile(r"frozen[- ]tests?[- ](?:hash|digest|checksum)", re.I)
    SHIPPED = (".md", ".py", ".json", ".yaml", ".yml")

    def test_no_shipped_page_or_message_names_a_frozen_test_hash(self):
        found = []
        for rel in helpers.repo_files():
            if not rel.endswith(self.SHIPPED) or rel in ("CHANGELOG.md", "tests/test_frozen_test_rules.py") or rel.startswith(("evals/", "tests/fixtures/")):
                continue
            path = helpers.ROOT / rel
            if path.is_file() and (hit := self.LEFTOVER.search(path.read_text(encoding="utf-8", errors="replace"))):
                found.append(f"{rel}: {hit.group(0)}")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
