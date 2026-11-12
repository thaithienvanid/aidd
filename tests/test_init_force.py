"""`aidd init --force`. It rewrites aidd's generated files and keeps every value a person set in the config: only a value
a flag sets changes, each as a line of output."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, git
from init_plan_helpers import files_of, repo

from aidd.kernel import documents
from aidd.setup import config_keep


class ForceKeepsEveryValueTests(unittest.TestCase):
    """`aidd init --force` rewrites aidd's generated files and keeps every value a person set in the config."""

    EDITED = (
        'aidd_version: "1.0.0"\n'
        "profile: team      # who decides\n"
        "\n"
        "owners:\n"
        "  # whoever approves\n"
        '  approvers: ["@a", "@b"]\n'
        '  reviewers: ["@r"]\n'
        "\n"
        "tests:\n"
        "  - name: unit\n"
        "    command: [make, test]\n"
        "\n"
        "# my own note: keep this comment\n"
        "specs_dir: my-specs\n"
        "proposals_dir: my-proposals\n"
        "risks:\n"
        "  rules:\n"
        "    - {action: pr.open, level: allow}\n"
    )

    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = repo(cls.template_dir.name)
        assert aidd_here("init", "--profile", "team", "--approvers", "@a", cwd=cls.template).returncode == 0
        git(cls.template, "add", "-A")
        git(cls.template, "commit", "-qm", "day 0")

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def adopted(self, d: str, text: str | None = None) -> Path:
        """A copy of the repository that adopted aidd once, its config replaced by `text` (EDITED by default)."""
        root = Path(d).resolve() / "r"
        shutil.copytree(self.template, root, symlinks=True)
        (root / ".aidd" / "config.yaml").write_text(self.EDITED if text is None else text, encoding="utf-8")
        return root

    def leaves(self, data, prefix=()):
        if isinstance(data, dict) and data:
            return {k: v for key, value in data.items() for k, v in self.leaves(value, (*prefix, key)).items()}
        return {prefix: data}

    def config(self, root: Path) -> dict:
        return documents.parse_yaml((root / ".aidd" / "config.yaml").read_text(encoding="utf-8"), "config")

    def test_with_no_flag_every_value_and_comment_stays_and_the_run_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d)
            done = aidd_here("init", "--force", cwd=root)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((root / ".aidd" / "config.yaml").read_text(encoding="utf-8"), self.EDITED)
            self.assertIn("kept     .aidd/config.yaml (--force keeps every value in it, and no flag changed one)", done.stdout)
            self.assertNotIn("config   ", done.stdout)

    def test_the_cases_below_set_every_value_a_flag_can_set(self):
        """A value a new flag sets joins `config_keep.SETS`, and so these cases."""
        self.assertEqual(sorted(config_keep.SETS), sorted(self.NAMES))

    NAMES = ("profile", "approvers", "specialists", "test", "environments", "delegate", "compliance_targets")

    def test_a_flag_changes_only_its_own_value_and_each_change_is_a_line(self):
        cases = [
            # (flags, the paths they change, their line's words)
            (["--profile", "solo"], {("profile",)}, "config   changed profile: team -> solo (--profile)"),
            (["--approvers", "@c"], {("owners", "approvers")}, 'config   changed owners.approvers: ["@a", "@b"] -> ["@c"] (--approvers)'),
            (["--specialist", "security=@s"], {("owners", "specialists")}, 'config   added   owners.specialists.security: ["@s"] (--specialist)'),
            (["--test", "make check"], {("tests",)}, "config   changed tests.unit: "),
            (["--environment", "production=main"], {("environments",)}, "config   added   environments: "),
            (["--environment", "none"], {("environments",)}, "config   added   environments: [] (--environment or --own-environment)"),
            (
                ["--compliance-target", "soc2"],
                {("project", "compliance", "targets")},
                "config   added   project.compliance.targets: [soc2] (--compliance-target)",
            ),
            (["--delegate"], {("delegation",)}, "config   added   delegation: "),
        ]
        for flags, paths, words in cases:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                root = self.adopted(d)
                before = self.leaves(self.config(root))
                done = aidd_here("init", "--force", *flags, cwd=root)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                after = self.leaves(self.config(root))
                moved = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
                self.assertTrue(moved and all(any(p[: len(s)] == s for s in paths) for p in moved), moved)
                self.assertIn(words, done.stdout)
                self.assertEqual(len([line for line in done.stdout.splitlines() if line.startswith("config   ")]) >= 1, True)
                kept = (root / ".aidd" / "config.yaml").read_text(encoding="utf-8")
                for stay in (
                    "# my own note: keep this comment",
                    "specs_dir: my-specs",
                    "proposals_dir: my-proposals",
                    "reviewers:",
                    "{action: pr.open, level: allow}",
                ):
                    self.assertIn(stay, kept)

    MANY = (
        'aidd_version: "1.0.0"\n'
        "profile: team\n"
        "owners:\n"
        '  approvers: ["@a"]\n'
        "  specialists:\n"
        '    security: ["@old"]\n'
        '    privacy: ["@p"]\n'
        "tests:\n"
        "  - name: unit\n"
        "    command: [make, test]\n"
        '    when_changed: ["src/**"]\n'
        "  - name: lint\n"
        "    command: [ruff, check]\n"
        "  - name: types\n"
        "    command: [mypy]\n"
        "environments:\n"
        "  - {name: staging, branches: [develop]}\n"
        "  - {name: production, branches: [main]}\n"
        "project:\n"
        "  compliance:\n"
        "    targets: [gdpr]\n"
        "delegation:\n"
        '  by: "Old <old@example.com>"\n'
        '  at: "2026-11-01T09:00:00Z"\n'
        "  decides: [spec.approve]\n"
        "  reserved: [pr.merge]\n"
        '  default_branch: "trunk"\n'
        '  review_due: "2020-01-01"\n'
        "  digest: each_session\n"
    )

    def test_a_flag_that_names_one_item_sets_only_that_item_and_the_line_shows_it_in_full(self):
        """For every flag, the value it sets is that one pool, test, environment, target or key; each value it did not name stays."""
        cases = [
            # (flags, the value at a path after the run, the old values that must stay: (path, value))
            (
                ["--specialist", "security=@new"],
                (("owners", "specialists"), {"security": ["@new"], "privacy": ["@p"]}),
                'config   changed owners.specialists.security: ["@old"] -> ["@new"] (--specialist)',
            ),
            (
                ["--specialist", "finance=@l"],
                (("owners", "specialists"), {"security": ["@old"], "privacy": ["@p"], "finance": ["@l"]}),
                'config   added   owners.specialists.finance: ["@l"] (--specialist)',
            ),
            (
                ["--test", "pytest -q"],
                (
                    ("tests",),
                    [
                        {"name": "unit", "command": ["pytest", "-q"], "when_changed": ["src/**"]},
                        {"name": "lint", "command": ["ruff", "check"]},
                        {"name": "types", "command": ["mypy"]},
                    ],
                ),
                "config   changed tests.unit: {name: unit, command: [make, test], when_changed: [src/**]} -> {name: unit, command: [pytest, -q], when_changed: [src/**]} (--test)",
            ),
            (
                ["--environment", "production=release", "--environment", "preview=pr"],
                (
                    ("environments",),
                    [
                        {"name": "staging", "branches": ["develop"]},
                        {"name": "production", "branches": ["release"]},
                        {"name": "preview", "branches": ["pr"]},
                    ],
                ),
                "config   changed environments.production: {name: production, branches: [main]} -> {name: production, branches: [release]} (--environment",
            ),
            (
                ["--compliance-target", "soc2"],
                (("project", "compliance", "targets"), ["gdpr", "soc2"]),
                "config   changed project.compliance.targets: [gdpr] -> [gdpr, soc2]",
            ),
            (["--approvers", "@z"], (("owners", "approvers"), ["@z"]), 'config   changed owners.approvers: ["@a"] -> ["@z"] (--approvers)'),
        ]
        for flags, (path, expected), words in cases:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                root = self.adopted(d, self.MANY)
                done = aidd_here("init", "--force", *flags, cwd=root)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                data = self.config(root)
                for step in path:
                    data = data[step]
                self.assertEqual(data, expected)
                self.assertIn(words, done.stdout)
                self.assertNotIn("...", done.stdout, "a value the run changed or dropped is shown in full")
                self.assertEqual(self.config(root)["delegation"], documents.parse_yaml(self.MANY, "c")["delegation"])

    def test_a_changed_value_is_shown_whole_however_long(self):
        who = ",".join(f"@team-{i}" for i in range(30))
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d, self.MANY)
            done = aidd_here("init", "--force", "--specialist", f"security={who}", cwd=root)
            self.assertIn("@team-29", done.stdout)
            self.assertNotIn("...", done.stdout)

    def test_delegate_keeps_a_delegation_as_it_is_so_an_expired_one_stays_expired(self):
        """A renewal is a person's own edit of `review_due`, never a side effect of a flag."""
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d, self.MANY)
            before = self.config(root)["delegation"]
            self.assertEqual(before["review_due"], "2020-01-01")
            for flags in (["--delegate"], ["--delegate", "--approvers", "@z"]):
                done = aidd_here("init", "--force", *flags, cwd=root)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertEqual(self.config(root)["delegation"], before)
                self.assertIn("config   kept    delegation as it is, set by Old <old@example.com> until 2020-01-01 (--delegate)", done.stdout)
            said = aidd_here("init", "--force", "--dry-run", "--delegate", cwd=root).stdout
            self.assertIn("delegation as it is, set by Old <old@example.com> until 2020-01-01", said)

    def test_delegate_writes_the_block_when_there_is_none(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d, self.MANY.split("delegation:")[0])
            done = aidd_here("init", "--force", "--delegate", cwd=root)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("config   added   delegation: ", done.stdout)
            self.assertEqual(self.config(root)["delegation"]["by"], "Maya Lee <maya@users.noreply.github.com>")

    def test_environment_none_does_not_drop_environments_that_are_listed(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d, self.MANY)
            before = files_of(root)
            done = aidd_here("init", "--force", "--environment", "none", cwd=root)
            self.assertEqual(done.returncode, 2, done.stdout)
            self.assertIn("--environment none would drop the environments .aidd/config.yaml lists (staging, production)", done.stderr)
            self.assertIn("remove `environments` from the file by hand", done.stderr)
            self.assertIn("Nothing was written", done.stderr)
            self.assertEqual(files_of(root), before)
            dry = aidd_here("init", "--force", "--dry-run", "--environment", "none", cwd=root)
            self.assertEqual(dry.returncode, 2, "the dry run refuses as the real run does")

    def test_a_comment_a_flag_drops_is_named_whole(self):
        text = self.MANY.replace("owners:\n", "owners:\n  # " + "who decides, in a long sentence " * 4 + "\n")
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d, text)
            done = aidd_here("init", "--force", "--approvers", "@z", cwd=root)
            self.assertIn(("who decides, in a long sentence " * 4).strip(), done.stdout)

    def test_the_profile_stays_when_no_flag_names_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d)
            self.assertEqual(aidd_here("init", "--force", "--approvers", "@c", cwd=root).returncode, 0)
            self.assertEqual(self.config(root)["profile"], "team")

    def test_a_value_from_a_flag_equal_to_the_one_there_is_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d)
            done = aidd_here("init", "--force", "--profile", "team", "--approvers", "@a", "--approvers", "@b", cwd=root)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual((root / ".aidd" / "config.yaml").read_text(encoding="utf-8"), self.EDITED)

    def test_a_config_it_cannot_read_back_refuses_the_run_before_any_file(self):
        for text in ("profile: [unclosed\n", "a: 1\na: 2\n", "- not a mapping\n"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as d:
                root = self.adopted(d, text)
                before = files_of(root)
                done = aidd_here("init", "--force", "--approvers", "@c", cwd=root)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertIn("--force cannot keep the values in .aidd/config.yaml", done.stderr)
                self.assertIn("Nothing was written", done.stderr)
                self.assertEqual(files_of(root), before)

    def test_the_dry_run_plans_the_same_force(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d)
            said = aidd_here("init", "--force", "--dry-run", "--approvers", "@c", cwd=root)
            self.assertEqual(said.returncode, 0, said.stderr)
            self.assertIn('config   would change owners.approvers: ["@a", "@b"] -> ["@c"] (--approvers)', said.stdout)
            block = said.stdout.split("```yaml\n", 1)[1].split("```", 1)[0]
            self.assertEqual(aidd_here("init", "--force", "--approvers", "@c", cwd=root).returncode, 0)
            self.assertEqual(block, (root / ".aidd" / "config.yaml").read_text(encoding="utf-8"))

    def test_a_generated_file_a_person_edited_is_rewritten_and_the_line_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d)
            (root / "specs" / "README.md").write_text("my own readme\n", encoding="utf-8")
            (root / "AGENTS.md").write_text((root / "AGENTS.md").read_text(encoding="utf-8") + "\n## Mine\nkeep\n", encoding="utf-8")
            done = aidd_here("init", "--force", cwd=root)
            self.assertIn("wrote    specs/README.md (--force replaced a file whose text differed)", done.stdout)
            self.assertIn("## Mine", (root / "AGENTS.md").read_text(encoding="utf-8"), "a hand-written section of AGENTS.md stays")

    def test_without_force_an_existing_config_is_kept_whole(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.adopted(d)
            self.assertEqual(aidd_here("init", "--approvers", "@c", cwd=root).returncode, 0)
            self.assertEqual((root / ".aidd" / "config.yaml").read_text(encoding="utf-8"), self.EDITED)


if __name__ == "__main__":
    unittest.main()
