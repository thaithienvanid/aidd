"""R385 fix 3: `aidd upgrade` and `aidd doctor` report what an older aidd stored and this aidd does not read, and write nothing to a Spec.

The fixture is a gate-era repository: Specs with no `status` that commits already touched, an approval in the old
`refs/aidd/approvals`, and a config with fields this aidd removed."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git

from aidd import __version__
from aidd.kernel import documents, json_schema
from aidd.setup import doctor_checks, unread_state, upgrading

GATE_ERA_CONFIG = (ROOT / "tests" / "fixtures" / "config-gate-era.yaml").read_text(encoding="utf-8")

CONFIG = """aidd_version: "0.9.0"
profile: solo
components:
  loop: false
mode: advisory
gates:
  approvals: {major: 2}
owners:
  approvers: ["@lead"]
  backup_approvers: ["@other"]
tests:
  - name: unit
    command: [python3, -m, unittest]
"""


def spec(sid: str, scope: str, extra: str = "") -> str:
    return f'---\naidd_version: "0.9.0"\ntype: spec\nid: {sid}\ntitle: t\n{extra}tasks:\n  - id: T1\n    title: t\n    scope: ["{scope}"]\n---\n\n## Intent\n\n"x"\n'


@unittest.skipUnless(shutil.which("git"), "git is required")
class UnreadStateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "T")
        git(self.root, "config", "user.email", "t@example.com")
        self.write(".aidd/config.yaml", CONFIG)
        self.write("specs/SPEC-1.md", spec("SPEC-1", "src/auth/**"))
        self.write("specs/SPEC-2.md", spec("SPEC-2", "TODO"))
        self.write("specs/SPEC-3.md", spec("SPEC-3", "src/billing/**", "status: draft\n"))
        self.write("specs/SPEC-4.md", spec("SPEC-4", "src/nothing/**"))
        self.write("specs/SPEC-5.md", spec("SPEC-5", "src/billing/**"))  # a fresh Spec over code that other work wrote
        self.write("specs/SPEC-10.md", spec("SPEC-10", "src/auth/**"))  # SPEC-1's commits do not name SPEC-10
        for n in (1, 2):
            self.write(f"src/auth/f{n}.py", "x = 1\n")
            self.commit(f"SPEC-1: auth {n}")
        self.write("src/billing/a.py", "x = 1\n")
        self.commit("billing")
        empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"  # an approval commit holds no project file
        approval = git(self.root, "commit-tree", empty_tree, "-m", "approve SPEC-1 at f292892").strip()
        git(self.root, "update-ref", "refs/aidd/approvals", approval)

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", message)

    def test_it_names_each_spec_with_no_status_whose_scope_has_commits_and_suggests_one(self):
        specs = [m for level, m in unread_state.unread_state(self.root) if "has no `status`" in m]
        self.assertEqual(len(specs), 1, "only a commit that names the Spec counts, and a fresh Spec over old code is not named")
        self.assertIn("SPEC-1 has no `status`, and 2 commits that name it touch its Tasks' scope", specs[0])
        self.assertIn("set `status: ready` and ask for Spec approval again", specs[0])
        self.assertNotIn("in_progress", specs[0], "never a status past a person's yes")
        self.write("specs/SPEC-4.md", spec("SPEC-4", "src/auth/**"))
        self.write("src/auth/f3.py", "x = 3\n")
        self.commit("SPEC-4: one")
        self.assertIn(
            "SPEC-4 has no `status`, and 1 commit that names it touches its Tasks' scope", "\n".join(m for _, m in unread_state.unread_state(self.root))
        )

    def test_it_names_the_old_approvals_as_history_and_never_as_a_yes(self):
        (note,) = [m for level, m in unread_state.unread_state(self.root) if "refs/aidd/approvals" in m]
        self.assertIn("holds 1 entry from an older aidd, naming SPEC-1.", note)
        self.assertIn("history only and never a yes", note)
        self.assertIn("asked again where a risk rule asks", note)

    def test_it_names_each_removed_config_field_and_the_next_step(self):
        fields = {m.split("holds `")[1].split("`")[0]: m for level, m in unread_state.unread_state(self.root) if "cannot load a config" in m}
        self.assertEqual(sorted(fields), ["components", "gates", "mode", "owners.backup_approvers"])
        self.assertIn(
            "remove lines 3 to 4 (`components:` and the lines under it) first, because this aidd cannot load a config that holds `components`",
            fields["components"],
        )
        self.assertIn("remove lines 6 to 7 (`gates:` and the lines under it) first", fields["gates"])
        for note in fields.values():
            self.assertIn("`aidd upgrade --yes` does this and keeps each block as a comment", note, "the config is otherwise valid, so upgrade can fix it")
            self.assertIn("your agent asks you once first", note, "upgrade changes the config, so the agent asks")
            self.assertIn(unread_state._UNKNOWN[1:], note, "a field with no replacement gets the one note")
        self.assertIn("remove line 5 (`mode: advisory`) first", fields["mode"])
        self.assertIn('remove line 10 (`backup_approvers: ["@other"]`) first', fields["owners.backup_approvers"])

    def test_upgrade_and_doctor_report_it_and_write_nothing_to_a_spec(self):
        before = {p: p.read_bytes() for p in sorted((self.root / "specs").glob("*.md"))}
        for yes, expected in ((False, 6), (True, 2)):  # SPEC-1, the approvals, and four fields; --yes comments the fields out
            lines = upgrading.upgrade(self.root, ref="v1.0.0", yes=yes)
            notes = [x for x in lines if x.startswith("note     ")]
            self.assertEqual(len(notes), expected, notes)
            self.assertTrue(any("SPEC-1 has no `status`" in n for n in notes))
        self.assertEqual({p: p.read_bytes() for p in before}, before, "no Spec changed")
        found = [m for level, m in doctor_checks.doctor(self.root) if "has no `status`" in m or "refs/aidd/approvals" in m or "cannot load a config" in m]
        self.assertEqual(len(found), 2, found)

    def test_a_1_0_stub_named_by_a_commit_is_no_note(self):
        # A 1.0.0 Spec stub has no `status` by design: a Day-0 commit that names it is no upgrade state, in doctor too.
        git(self.root, "update-ref", "-d", "refs/aidd/approvals")
        self.write(".aidd/config.yaml", 'aidd_version: "1.0.0"\nprofile: solo\n')
        for name in ("SPEC-1", "SPEC-4", "SPEC-5", "SPEC-10"):
            path = self.root / "specs" / f"{name}.md"
            path.write_text(path.read_text(encoding="utf-8").replace('aidd_version: "0.9.0"', 'aidd_version: "1.0.0"'), encoding="utf-8")
        self.write("src/auth/f3.py", "x = 3\n")
        self.commit("Day 0: the skeleton\n\nSPEC-1 builds those")
        self.assertEqual([m for _, m in unread_state.unread_state(self.root) if "has no `status`" in m], [])
        self.assertEqual([m for _, m in doctor_checks.doctor(self.root) if "has no `status`" in m], [])

    def test_a_pre_1_0_spec_warns_and_says_again_only_for_an_old_approval(self):
        # With no old approvals, a Spec an older aidd wrote still needs its status set, but nobody approved it before.
        git(self.root, "update-ref", "-d", "refs/aidd/approvals")
        (note,) = [m for _, m in unread_state.unread_state(self.root) if "has no `status`" in m]
        self.assertIn("SPEC-1", note)
        self.assertNotIn("again", note)
        # Old approvals mark the repository pre-1.0, so a Spec with a 1.0.0 version beside them is still named.
        approval = git(self.root, "commit-tree", "4b825dc642cb6eb9a060e54bf8d69288fbee4904", "-m", "approve SPEC-1").strip()
        git(self.root, "update-ref", "refs/aidd/approvals", approval)
        self.write("specs/SPEC-4.md", spec("SPEC-4", "src/auth/**").replace('"0.9.0"', '"1.0.0"'))
        self.write("src/auth/f4.py", "x = 4\n")
        self.commit("SPEC-4: one")
        notes = {m.split(" ", 1)[0]: m for _, m in unread_state.unread_state(self.root) if "has no `status`" in m}
        self.assertEqual(sorted(notes), ["SPEC-1", "SPEC-4"])
        self.assertIn("again", notes["SPEC-1"])
        self.assertNotIn("again", notes["SPEC-4"])

    def test_a_repository_with_nothing_to_carry_says_nothing(self):
        self.write(".aidd/config.yaml", 'aidd_version: "1.0.0"\nprofile: solo\n')
        self.write("specs/SPEC-1.md", spec("SPEC-1", "src/auth/**", "status: in_progress\n"))
        git(self.root, "update-ref", "-d", "refs/aidd/approvals")
        self.assertEqual(unread_state.unread_state(self.root), [])


# Each row: the field, then the first and last line of its block in GATE_ERA_CONFIG (the fixture's line numbers).
FIXTURE_BLOCKS = [
    ("mode", 5, 5),  # a scalar with a trailing comment
    ("components", 6, 6),  # a flow mapping with a trailing comment
    ("goal", 8, 8),
    ("budget_exclude_paths", 12, 14),  # a block list; the blank line and the comment after it belong to what follows
    ("owners.default_team", 21, 21),  # a nested key among comment lines and blank lines
    ("identities", 34, 39),  # a mapping with comment lines and blank lines inside, ending at a key
]


class RetiredBlockTests(unittest.TestCase):
    """A retired field's block: its key's line, and the blank or deeper-indented lines after it, up to the first line at or above its indent."""

    def test_the_block_of_each_shape_in_a_gate_era_config(self):
        for field, first, last in FIXTURE_BLOCKS:
            with self.subTest(field=field):
                self.assertEqual(unread_state.retired_block(GATE_ERA_CONFIG, field), (first, last))

    def test_the_end_of_a_block_belongs_to_the_next_one(self):
        rows = [
            ("a trailing indented comment and a blank line", "x:\n  a: 1\n  # about b\n\ny: 2\n", "x", (1, 2)),
            ("a trailing blank line", "x:\n  - a\n\n\ny: 2\n", "x", (1, 2)),
            ("a comment inside, then a key", "x:\n  a: 1\n  # about b\n  b: 2\ny: 3\n", "x", (1, 4)),
            ("the end of the file", "y: 1\nx:\n  - a\n  - b\n", "x", (2, 4)),
            ("the end of the file after a blank line", "y: 1\nx:\n  - a\n\n", "x", (2, 3)),
            ("a list at the key's own indent", "x:\n- a\n- b\ny: 1\n", "x", (1, 3)),
            ("a nested key and a sibling of the same name", "x: 1\nowners:\n  x: 2\n  y: 3\n", "owners.x", (3, 3)),
            ("a nested key under a parent whose name repeats", "tests:\n  - name: a\nowners:\n  - name: b\n    c: 1\n", "owners.c", (5, 5)),
            ("a key indented by a list dash", "tests:\n  - name: a\n    mode: x\n", "tests[0].mode", (3, 3)),
            # A comment is skipped at any column, as the parser skips it, so it never ends a block.
            ("a column-0 comment inside a list", "budget_exclude_paths:\n  - a\n#  - b\n  - c\ny: 1\n", "budget_exclude_paths", (1, 4)),
            ("a column-0 comment inside a mapping", "x:\n  a: 1\n# about b\n  b: 2\ny: 3\n", "x", (1, 4)),
            ("a column-0 comment before a nested key", "owners:\n# c\n  default_team: x\n", "owners.default_team", (3, 3)),
            ("a column-0 comment at the end of a block", "x:\n  a: 1\n# about y\ny: 2\n", "x", (1, 2)),
            (
                "a pool named like the nested key, before it",
                "owners:\n  specialists:\n    default_team: [a]\n  default_team: m\n",
                "owners.default_team",
                (4, 4),
            ),
            ("a double-quoted key", '"mode": x\ny: 1\n', "mode", (1, 1)),
        ]
        for label, text, field, expected in rows:
            with self.subTest(label):
                self.assertEqual(unread_state.retired_block(text, field), expected)

    def test_a_field_the_text_does_not_set_has_no_block(self):
        self.assertIsNone(unread_state.retired_block("a: 1\n", "b"))
        self.assertIsNone(unread_state.retired_block("a: 1\n", "owners.b"))
        self.assertIsNone(unread_state.retired_block("# mode: advisory\n", "mode"), "a comment sets nothing")


class RetireConfigFieldsTests(unittest.TestCase):
    """The config as `aidd upgrade --yes` writes it: a retired field kept as a comment, `default_team` renamed."""

    def test_each_retired_block_stays_as_a_comment_and_the_config_validates(self):
        new, steps = unread_state.retire_config_fields(GATE_ERA_CONFIG)
        lines = [line.strip() for line in new.splitlines()]
        uncommented = {line.replace("# ", "", 1) for line in new.splitlines()}  # taking the first "# " off gives the old line back
        old = GATE_ERA_CONFIG.splitlines()
        for field, first, last in FIXTURE_BLOCKS:
            if field == "owners.default_team":
                continue
            with self.subTest(field=field):
                for line in old[first - 1 : last]:
                    self.assertTrue(not line.strip() or line in uncommented, line)
        self.assertEqual(len(steps), len(FIXTURE_BLOCKS))
        self.assertIn("  default_owner_team: maintainers", new.splitlines())
        self.assertNotIn("  default_team: maintainers", new.splitlines())
        self.assertEqual(sum(line.startswith("# Retired in aidd") for line in lines), 5, "one line above each commented block")
        self.assertIn("approvers", new)
        self.assertIn(f'aidd_version: "{__version__}"', new.splitlines(), "the text it gives is the text to write, with this aidd's version")
        self.assertEqual(json_schema.validate(documents.parse_yaml(new, "config.yaml"), "config.schema.json"), [])
        self.assertIsNone(unread_state.retire_config_fields(new), "a second run has nothing to do")

    def test_a_default_team_beside_a_default_owner_team_is_commented_out_and_the_value_kept(self):
        text = 'aidd_version: "0.9.0"\nprofile: solo\nowners:\n  default_team: old\n  default_owner_team: new\n'
        new, _ = unread_state.retire_config_fields(text)
        self.assertIn("  default_owner_team: new", new.splitlines())
        self.assertIn("  # default_team: old", new.splitlines())

    def test_nothing_changes_when_the_fix_would_still_leave_the_config_invalid(self):
        head = 'aidd_version: "0.9.0"\nprofile: solo\n'
        tests = "tests:\n  - name: a\n    command: [make]\n"
        rows = [
            ("a value the schema refuses", GATE_ERA_CONFIG.replace("profile: solo", "profile: bogus")),
            ("a retired key a list dash opens", head + "tests:\n  - mode: x\n    name: a\n    command: [make]\n"),
            ("a retired key that is a whole list item", head + tests + "  - mode: x\n"),  # without the dash guard the item just vanishes
            (
                "the same retired key in two list items, the second of which stays",
                head + tests + "    mode: x\n  - name: b\n    command: [make]\n    mode: y\n",
            ),
            ("nothing retired", 'aidd_version: "1.0.0"\nprofile: solo\n'),
            ("a version line the upgrade cannot rewrite", GATE_ERA_CONFIG.replace("aidd_version:", '"aidd_version":')),
        ]
        for label, text in rows:
            with self.subTest(label):
                self.assertIsNone(unread_state.retire_config_fields(text))

    def test_a_pool_named_like_the_retired_key_is_left_alone(self):
        text = 'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  specialists:\n    default_team: ["@a"]\n  default_team: maintainers\n'
        new, _ = unread_state.retire_config_fields(text)
        self.assertIn('    default_team: ["@a"]', new.splitlines())
        self.assertIn("  default_owner_team: maintainers", new.splitlines())

    def test_a_comment_at_column_0_inside_a_retired_block_stays_inside_it(self):
        text = (
            'aidd_version: "1.0.0"\nprofile: solo\nobserve:\n  command: [./scripts/smoke]\n# the preview below starts the app\n'
            "  timeout_seconds: 30\npreview:\n  command: [docker, compose, up]\n"
        )
        new, _ = unread_state.retire_config_fields(text)
        data = documents.parse_yaml(new, "config.yaml")
        self.assertEqual(data["preview"], {"command": ["docker", "compose", "up"]})
        self.assertNotIn("observe", data)
        self.assertNotIn("  timeout_seconds: 30", new.splitlines(), "its last child is part of the block")

    def test_a_column_0_comment_inside_an_indented_retired_block_is_commented_whole(self):
        text = 'aidd_version: "1.0.0"\nprofile: solo\nowners:\n  approvers: ["@a"]\n  backup_approvers:\n    - "@b"\n# a note at column 0\n    - "@c"\n'
        new, _ = unread_state.retire_config_fields(text)
        uncommented = {line.replace("# ", "", 1) for line in new.splitlines()}
        for line in text.splitlines()[4:8]:
            self.assertIn(line, uncommented, "taking the first '# ' off gives the old line back, so no character was cut")

    def test_the_steps_of_a_dry_run_are_in_the_future(self):
        _, done = unread_state.retire_config_fields(GATE_ERA_CONFIG)
        _, would = unread_state.retire_config_fields(GATE_ERA_CONFIG, dry_run=True)
        self.assertTrue(all("would" not in step for step in done))
        self.assertTrue(all("would" in step for step in would), would)
        self.assertEqual(len(would), len(done))

    def test_a_quoted_key_is_found_and_kept_as_a_comment(self):
        text = 'aidd_version: "1.0.0"\nprofile: solo\n"mode": advisory\nowners:\n  "default_team": maintainers\n'
        new, _ = unread_state.retire_config_fields(text)
        self.assertIn('# "mode": advisory', new.splitlines())
        self.assertIn('  "default_owner_team": maintainers', new.splitlines())


class RetiredFieldNoteTests(unittest.TestCase):
    """A retired field with a direct replacement names it; every other one gets the one note, which names a next step a
    person can take, never "ask your agent what it did"."""

    def test_a_field_with_a_replacement_names_it(self):
        for field, mentions in {"owners.default_team": "owners.default_owner_team", "runbook_max_age_days": "docs.max_runbook_age_days"}.items():
            with self.subTest(field=field):
                self.assertIn(mentions, unread_state._about(field))

    def test_every_other_field_gets_the_one_note_with_a_next_step(self):
        for field in ("gates", "mode", "risk_rules", "owners.backup_approvers", "agents.autonomy"):
            with self.subTest(field=field):
                self.assertEqual(unread_state._about(field), unread_state._UNKNOWN)
        self.assertIn("`aidd risk --list`", unread_state._UNKNOWN)
        self.assertNotIn("ask your agent what it did", unread_state._UNKNOWN)

    def test_a_listed_account_that_reads_as_a_person_now_is_told_so(self):
        about = unread_state._about("identities")
        self.assertIn("reads as a person", about)
        self.assertIn("`agent:` identity", about)


class RefusedFixTests(unittest.TestCase):
    """A gate-era profile or lock, which `--yes` never maps, and the findings that stop the fix, are named."""

    def notes(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(text, encoding="utf-8")
            return [m for _, m in unread_state.unread_state(root) if m.startswith(".aidd/config.yaml")]

    HEAD = 'aidd_version: "1.0.0"\n'

    def test_a_profile_this_aidd_lacks_is_named_with_the_choice_left_to_the_person(self):
        for profile in ("org", "audited"):
            with self.subTest(profile=profile):
                notes = self.notes(self.HEAD + f"profile: {profile}\nmode: advisory\n")
                (note,) = [n for n in notes if f"profile: {profile}" in n and "line 2" in n]
                for expected in ("`solo`", "`team`", "strictest", "your agent asks you"):
                    self.assertIn(expected, note)
                (refused,) = [n for n in notes if "still not load" in n]
                self.assertIn(f'$.profile: must be one of solo, team; got "{profile}"', refused, "the finding that stops --yes is named")
                self.assertFalse([n for n in notes if "remove line 3" in n and "does this" in n], "the fix is not offered")

    def test_a_lock_that_names_a_retired_field_is_named(self):
        notes = self.notes(self.HEAD + "profile: solo\nlocks: [disable_rules, project, tenant]\n")
        (note,) = [n for n in notes if "locks" in n and "disable_rules" in n]
        self.assertIn("tenant", note)
        self.assertNotIn("`project`", note, "project is still a lock")
        self.assertIn("line 3", note)
        self.assertIn("remove", note)

    def test_the_findings_that_stop_the_fix_are_named_and_a_fixable_config_has_none(self):
        stuck = self.notes(self.HEAD + "profile: solo\ntests:\n  - mode: x\n    name: a\n    command: [make]\n")
        (refused,) = [n for n in stuck if "still not load" in n]
        self.assertIn("tests[0].mode", refused)
        fine = self.notes(self.HEAD + "profile: solo\nmode: advisory\n")
        self.assertEqual([n for n in fine if "still not load" in n], [])


if __name__ == "__main__":
    unittest.main()
