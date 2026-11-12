import json
import os
import tempfile
import unittest
from pathlib import Path

import graph_repo
import helpers

from aidd import workitems
from aidd.kernel import documents, git, json_schema


def _write_spec(root: Path, spec_id: str, rel: str | None = None) -> None:
    target = root / (rel or f"specs/{spec_id}.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(helpers.SAMPLE_SPEC.replace("SPEC-220", spec_id), encoding="utf-8")


def _commit_with_time(root: Path, msg: str, when: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    helpers.git(root, "add", "-A", env=env)
    helpers.git(root, "commit", "-qm", msg, env=env)
    return helpers.git(root, "rev-parse", "HEAD")


def _init_release_repo(root: Path, env_yaml: str) -> tuple[Path, str]:
    helpers.make_repo(root, "team", branch=None)
    cfg_path = root / ".aidd" / "config.yaml"
    existing = cfg_path.read_text(encoding="utf-8")
    updated = existing.rstrip() + "\n" + env_yaml
    cfg_path.write_text(updated, encoding="utf-8")
    base_sha = _commit_with_time(root, "configure environments", "2026-11-18T10:00:00Z")
    return root, base_sha


class ConfigEnvironmentSchemaTests(unittest.TestCase):
    def test_environment_schema_accepts_production_and_paths_while_keeping_required_guard(self) -> None:
        base_cfg = {"aidd_version": "1.0.0", "profile": "team", "owners": {"approvers": ["@maya"]}}
        cases = [
            ("legacy branches only", [{"name": "staging", "branches": ["main"]}], True),
            ("production boolean only", [{"name": "production", "production": True}], True),
            ("production with globs", [{"name": "api-production", "production": True, "paths": ["api/**", "shared/"]}], True),
            ("non-production explicit", [{"name": "qa", "production": False}], True),
            ("empty environment object rejected", [{"name": "production"}], False),
            ("non-boolean production rejected", [{"name": "production", "production": "yes"}], False),
            ("absolute path rejected", [{"name": "production", "production": True, "paths": ["/etc/**"]}], False),
        ]
        for label, envs, expected in cases:
            with self.subTest(label=label):
                errs = json_schema.validate({**base_cfg, "environments": envs}, "config.schema.json")
                self.assertEqual(not errs, expected, errs)


class ReleaseAuthoringAndCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "repo"

    def test_new_release_refusals(self) -> None:
        env_yaml = "environments:\n  - name: sandbox\n    branches: [main]\n  - name: production\n    production: true\n    branches: [hotfix]\n"
        _, base_sha = _init_release_repo(self.root, env_yaml)
        helpers.git(self.root, "checkout", "-qb", "feat/wip")
        _write_spec(self.root, "SPEC-1")
        feat_sha = _commit_with_time(self.root, "feat work", "2026-11-19T09:00:00Z")
        helpers.git(self.root, "checkout", "-q", "main")

        cases = [
            ("unknown environment typo", "producton", base_sha, None, "Did you mean `aidd new release production"),
            ("leading digit environment rejected", "1prod", base_sha, None, "lowercase letter"),
            ("missing commit flag value", "production", "", None, "`--commit <sha>`"),
            ("unknown commit", "production", "deadbeef00", None, "git log"),
            ("commit only on feature branch", "production", feat_sha, None, "hotfix"),
            ("bad released_at without zone", "production", base_sha, "2026-11-20", "--released-at"),
        ]
        for label, env_name, sha, at, needle in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError) as ctx:
                    workitems.new_release(self.root, env_name, sha, released_at=at)
                self.assertIn(needle, str(ctx.exception))

        workitems.new_release(self.root, "production", base_sha, released_at="2026-11-20T12:00:00Z")
        for label, at in [
            ("older released_at refused", "2026-11-20T11:00:00Z"),
            ("equal released_at refused", "2026-11-20T12:00:00Z"),
        ]:
            with self.subTest(label=label):
                with self.assertRaises(ValueError) as ctx:
                    workitems.new_release(self.root, "production", base_sha, released_at=at)
                msg = str(ctx.exception)
                self.assertIn("production-2026-11-20-1.md", msg)
                self.assertIn("2026-11-20T12:00:00Z", msg)

        _write_spec(self.root, "SPEC-2")
        c2 = _commit_with_time(self.root, "add SPEC-2", "2026-11-20T13:00:00Z")
        shallow = Path(self.tmp.name).resolve() / "shallow_new"
        helpers.git(self.root.parent, "clone", "-q", "--depth", "1", f"file://{self.root}", str(shallow))
        with self.subTest(label="shallow clone refused"):
            with self.assertRaises(ValueError) as ctx:
                workitems.new_release(shallow, "production", c2, released_at="2026-11-20T14:00:00Z")
            self.assertIn("git fetch --unshallow", str(ctx.exception))

        outside = Path(self.tmp.name).resolve() / "plain"
        outside.mkdir()
        with self.assertRaises(ValueError) as ctx:
            workitems.new_release(outside, "production", base_sha)
        self.assertIn("git", str(ctx.exception))

        no_cfg = Path(self.tmp.name).resolve() / "nocfg"
        no_cfg.mkdir()
        helpers.git(no_cfg, "init", "-q", "-b", "main")
        (no_cfg / "a.txt").write_text("hi\n", encoding="utf-8")
        c0 = _commit_with_time(no_cfg, "init", "2026-11-18T10:00:00Z")
        with self.assertRaises(ValueError) as ctx:
            workitems.new_release(no_cfg, "production", c0)
        self.assertIn("aidd init", str(ctx.exception))

    def test_new_release_sequence_autofill_and_cli_roundtrip(self) -> None:
        env_yaml = "environments:\n  - name: production\n    production: true\n    branches: [hotfix]\n  - name: prod_eu\n    production: true\n"
        _, _ = _init_release_repo(self.root, env_yaml)

        # Commit 1 on main: holds SPEC-1.
        _write_spec(self.root, "SPEC-1")
        c1 = _commit_with_time(self.root, "merge SPEC-1", "2026-11-20T10:00:00Z")
        # Commit 2 on main: adds SPEC-2 (now holds SPEC-1, SPEC-2).
        _write_spec(self.root, "SPEC-2")
        c2 = _commit_with_time(self.root, "merge SPEC-2", "2026-11-20T12:00:00Z")
        # Hotfix branch off c2 with SPEC-3.
        helpers.git(self.root, "checkout", "-qb", "hotfix", c2)
        _write_spec(self.root, "SPEC-3")
        c3 = _commit_with_time(self.root, "hotfix SPEC-3", "2026-11-20T13:00:00Z")
        helpers.git(self.root, "checkout", "-q", "main")

        # Release 1 via CLI on main at c1 -> production-2026-11-20-1.md
        r1 = helpers.aidd_here("new", "release", "production", "--commit", c1[:7], "--released-at", "2026-11-20T11:00:00Z", cwd=self.root)
        self.assertEqual(r1.returncode, 0, r1.stderr + r1.stdout)
        f1 = self.root / "docs" / "releases" / "production-2026-11-20-1.md"
        self.assertTrue(f1.is_file())
        d1, _ = documents.split_front_matter(f1.read_text(encoding="utf-8"), str(f1))
        self.assertEqual(d1["commit"], c1)
        self.assertEqual(d1["specs"], ["SPEC-1"])
        self.assertEqual(d1["rolled_back"], [])

        # Release 2 on same day from hotfix branch at c3 -> increments sequence (-2.md) and fills only delta [SPEC-2, SPEC-3]
        f2 = workitems.new_release(self.root, "production", c3, released_at="2026-11-20T14:00:00Z")
        self.assertEqual(f2.name, "production-2026-11-20-2.md")
        d2, _ = documents.split_front_matter(f2.read_text(encoding="utf-8"), str(f2))
        self.assertEqual(d2["specs"], ["SPEC-2", "SPEC-3"])
        self.assertEqual(d2["rolled_back"], [])

        # Release 3 rolling back to c1 -> specs: [], rolled_back: [SPEC-2, SPEC-3]
        f3 = workitems.new_release(self.root, "production", c1, released_at="2026-11-20T15:00:00Z")
        self.assertEqual(f3.name, "production-2026-11-20-3.md")
        d3, _ = documents.split_front_matter(f3.read_text(encoding="utf-8"), str(f3))
        self.assertEqual(d3["specs"], [])
        self.assertEqual(d3["rolled_back"], ["SPEC-2", "SPEC-3"])

        # Underscore environment name accepted and validates cleanly.
        f_eu = workitems.new_release(self.root, "prod_eu", c1, released_at="2026-11-20T11:00:00Z")
        self.assertEqual(f_eu.name, "prod_eu-2026-11-20-1.md")

        # All written release files validate cleanly with zero findings.
        errs, warns = workitems.check_repo(self.root)
        self.assertEqual((errs, warns), ([], []))

    def test_cli_flag_guards(self) -> None:
        _init_release_repo(self.root, "environments:\n  - name: production\n    production: true\n")
        bad_cases = [
            ("release missing environment", ("new", "release")),
            ("release passed --title", ("new", "release", "production", "--commit", "HEAD", "--title", "hi")),
            ("spec passed --commit", ("new", "spec", "SPEC-9", "--title", "T", "--commit", "HEAD")),
        ]
        for label, argv in bad_cases:
            with self.subTest(label=label):
                res = helpers.aidd_here(*argv, cwd=self.root)
                self.assertNotEqual(res.returncode, 0, label)


class ReleaseReaderTests(unittest.TestCase):
    def _fixture_case(self, path: str, case_id: str) -> dict:
        data = json.loads((helpers.ROOT / "tests" / "fixtures" / "design" / "graph_cases" / path).read_text(encoding="utf-8"))
        for row in data["rows"]:
            if row["id"] == case_id:
                return row
        raise KeyError(case_id)

    def test_reader_table_across_deploy_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "r1"
            _, base_sha = _init_release_repo(
                root,
                "environments:\n  - name: sandbox\n    branches: [main]\n  - name: production\n    production: true\n",
            )
            _write_spec(root, "SPEC-1", "specs/archive/SPEC-1.md")
            c1 = _commit_with_time(root, "add SPEC-1 in archive", "2026-11-20T10:00:00Z")

            # Deploy-on-merge sandbox picks up main tip without release files; production has none yet.
            sandbox_state = workitems.read_environment(root, "sandbox")
            self.assertIsInstance(sandbox_state, workitems.EnvironmentState)
            self.assertEqual(sandbox_state.live_commit, c1)
            self.assertEqual(sandbox_state.live_specs, ("SPEC-1",))
            self.assertEqual(sandbox_state.rolled_back, ())

            prod_empty = workitems.read_environment(root, "production")
            self.assertIsNone(prod_empty.live_commit)
            self.assertEqual(prod_empty.live_specs, ())
            self.assertEqual(prod_empty.rolled_back, ())

            # Flag rollback in production without changing commit, plus later release adding SPEC-2 (C1-24).
            workitems.new_release(root, "production", c1, released_at="2026-11-20T11:00:00Z")
            _write_spec(root, "SPEC-2")
            c2 = _commit_with_time(root, "add SPEC-2", "2026-11-20T11:30:00Z")
            (root / "docs" / "releases" / "production-2026-11-20-2.md").write_text(
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T12:00:00Z"\ncommit: "{c1}"\nspecs: []\nrolled_back: ["SPEC-1"]\n---\n',
                encoding="utf-8",
            )
            (root / "docs" / "releases" / "production-2026-11-20-3.md").write_text(
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T13:00:00Z"\ncommit: "{c2}"\nspecs: ["SPEC-2"]\nrolled_back: []\n---\n',
                encoding="utf-8",
            )
            state_after_rel = workitems.read_environment(root, "production")
            self.assertEqual(state_after_rel.live_commit, c2)
            self.assertEqual(state_after_rel.live_specs, ("SPEC-2",))
            self.assertEqual(state_after_rel.rolled_back, ("SPEC-1",))

            # Release file rolled_back listing a Spec no earlier live commit held does NOT read as rolled back.
            (root / "docs" / "releases" / "production-2026-11-20-4.md").write_text(
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T14:00:00Z"\ncommit: "{c2}"\nspecs: []\nrolled_back: ["SPEC-NEVER"]\n---\n',
                encoding="utf-8",
            )
            self.assertNotIn("SPEC-NEVER", workitems.read_environment(root, "production").rolled_back)

            # Commit touching only a non-Spec file on main moves deploy-on-merge live commit and preserves live Specs (C1-17).
            (root / "README.md").write_text("docs update\n", encoding="utf-8")
            readme_sha = _commit_with_time(root, "touch readme", "2026-11-20T11:45:00Z")
            sandbox_readme = workitems.read_environment(root, "sandbox")
            self.assertEqual(sandbox_readme.live_commit, readme_sha)
            self.assertEqual(sandbox_readme.live_specs, ("SPEC-1", "SPEC-2"))
            self.assertEqual(sandbox_readme.rolled_back, ())

            # Deploy-on-merge where a release file is newer than main tip keeps release commit until a newer main commit.
            (root / "docs" / "releases" / "sandbox-2026-11-20-1.md").write_text(
                f'---\ntype: release\nenvironment: "sandbox"\nreleased_at: "2026-11-20T15:00:00Z"\ncommit: "{base_sha}"\nspecs: []\nrolled_back: ["SPEC-1"]\n---\n',
                encoding="utf-8",
            )
            sandbox_pin = workitems.read_environment(root, "sandbox")
            self.assertEqual(sandbox_pin.live_commit, base_sha)
            self.assertEqual(sandbox_pin.rolled_back, ("SPEC-1", "SPEC-2"))

            # Deploy-on-merge revert on main (delete Spec file and commit) -> live_specs=(), rolled_back=('SPEC-1', 'SPEC-2').
            helpers.git(root, "rm", "-q", "specs/archive/SPEC-1.md", "specs/SPEC-2.md")
            rev_sha = _commit_with_time(root, "revert specs", "2026-11-20T16:00:00Z")
            sandbox_reverted = workitems.read_environment(root, "sandbox")
            self.assertEqual(sandbox_reverted.live_commit, rev_sha)
            self.assertEqual(sandbox_reverted.live_specs, ())
            self.assertEqual(sandbox_reverted.rolled_back, ("SPEC-1", "SPEC-2"))

    def test_graph_cases_deploy_fixtures(self) -> None:
        # C1-01..C1-02, C1-05..C1-16, C1-18..C1-19, C2-H12..C2-H16, and C2-H20 test spec_status / status lines (C4a/C5) or needs_person.
        cases = [
            ("deploy-shapes.json", "C1-03", "production", "main_tip", ("SPEC-1",), ()),
            ("deploy-shapes.json", "C1-04", "staging", "main_tip", ("SPEC-1",), ()),
            ("deploy-shapes.json", "C1-04", "production", "3f2c1a9", ("SPEC-1",), ()),
            ("deploy-shapes.json", "C1-20", "production", "3f2c1a9", ("SPEC-1",), ()),
            ("deploy-shapes.json", "C1-21", "production", "1b2c3d4", (), ("SPEC-1",)),
            ("deploy-shapes.json", "C1-22", "production", "5d7e2b8", ("SPEC-1",), ()),
            ("deploy-shapes.json", "C1-23", "production", "1b2c3d4", (), ("SPEC-1", "SPEC-2")),
            ("deploy-shapes.json", "C1-24", "production", "5d7e2b8", (), ("SPEC-1",)),
            ("hard-cases.json", "C2-H11", "sandbox", "3f2c1a9", ("SPEC-1",), ()),
            ("hard-cases.json", "C2-H11", "production", None, (), ()),
        ]
        for filename, cid, env_name, commit_key, expected_live, expected_rb in cases:
            with self.subTest(case=cid, env=env_name), tempfile.TemporaryDirectory() as tmp:
                built = graph_repo.build(self._fixture_case(filename, cid)["facts"], Path(tmp) / cid)
                state = workitems.read_environment(built.root, env_name)
                if commit_key is None:
                    self.assertIsNone(state.live_commit)
                elif commit_key == "main_tip":
                    self.assertEqual(state.live_commit, git.rev_parse("main", str(built.root)))
                else:
                    self.assertEqual(state.live_commit, built.shas[commit_key])
                self.assertEqual(state.live_specs, expected_live)
                self.assertEqual(state.rolled_back, expected_rb)
                if cid == "C1-20":
                    self.assertEqual(state.note, workitems.SHALLOW_NOTE)

        c2h17 = self._fixture_case("hard-cases.json", "C2-H17")
        variant = next(v for v in c2h17["variants"] if v["name"] == "a rollback by release")
        with self.subTest(variant="a rollback by release"), tempfile.TemporaryDirectory() as tmp:
            built = graph_repo.build(variant["facts"], Path(tmp) / "h17")
            state = workitems.read_environment(built.root, "production")
            self.assertEqual(state.live_specs, ())
            self.assertEqual(state.rolled_back, ("SPEC-1",))

        with self.subTest(case="C2-H18"), tempfile.TemporaryDirectory() as tmp:
            built = graph_repo.build(self._fixture_case("hard-cases.json", "C2-H18")["facts"], Path(tmp) / "h18")
            state = workitems.read_environment(built.root, "production")
            self.assertEqual(state.live_commit, built.shas["5d7e2b8"])
            self.assertEqual(state.live_specs, ("SPEC-1",))
            self.assertEqual(state.rolled_back, ())

        with self.subTest(case="C2-H19", env="production"), tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "h19"
            _init_release_repo(repo, "environments:\n  - name: production\n    production: true\n    branches: [hotfix]\n")
            helpers.git(repo, "checkout", "-qb", "hotfix")
            _write_spec(repo, "SPEC-1")
            c_hotfix = _commit_with_time(repo, "hotfix SPEC-1", "2026-11-20T15:00:00Z")
            helpers.git(repo, "checkout", "-q", "main")
            workitems.new_release(repo, "production", c_hotfix, released_at="2026-11-20T15:10:00Z")
            state = workitems.read_environment(repo, "production")
            self.assertEqual(state.live_commit, c_hotfix)
            self.assertEqual(state.live_specs, ("SPEC-1",))
            self.assertEqual(state.rolled_back, ())


class ReleaseValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "repo"

    def test_validate_release_errors_and_warnings(self) -> None:
        env_yaml = "environments:\n  - name: production\n    production: true\n"
        _, c0 = _init_release_repo(self.root, env_yaml)
        _write_spec(self.root, "SPEC-1")
        c1 = _commit_with_time(self.root, "add SPEC-1", "2026-11-20T10:00:00Z")
        helpers.git(self.root, "checkout", "-qb", "feat/off")
        _write_spec(self.root, "SPEC-2")
        feat_sha = _commit_with_time(self.root, "off branch spec", "2026-11-20T10:30:00Z")
        helpers.git(self.root, "checkout", "-q", "main")

        cases = [
            (
                "specs holds spec missing from commit",
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "{c0}"\nspecs: ["SPEC-1"]\nrolled_back: []\n---\n',
                True,
                "does not hold",
            ),
            (
                "unknown environment in config",
                f'---\ntype: release\nenvironment: "staging"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "{c1}"\nspecs: ["SPEC-1"]\nrolled_back: []\n---\n',
                True,
                "environments",
            ),
            (
                "unknown commit in full repo",
                '---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "deadbeef00"\nspecs: []\nrolled_back: []\n---\n',
                True,
                "git log",
            ),
            (
                "commit not on allowed branch",
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "{feat_sha}"\nspecs: ["SPEC-2"]\nrolled_back: []\n---\n',
                True,
                "not on",
            ),
            (
                "duplicate YAML field rejected",
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "{c1}"\nspecs: ["SPEC-1"]\nspecs: ["SPEC-1"]\n---\n',
                True,
                "specs",
            ),
            (
                "malformed extra key rejected",
                f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "{c1}"\nspecs: ["SPEC-1"]\nextra: "bad"\n---\n',
                True,
                "extra",
            ),
        ]
        rel_dir = self.root / "docs" / "releases"
        rel_dir.mkdir(parents=True, exist_ok=True)
        for label, content, expect_err, needle in cases:
            with self.subTest(label=label):
                target = rel_dir / "production-2026-11-20-1.md"
                target.write_text(content, encoding="utf-8")
                findings = workitems.validate_file(target)
                errs = [f for f in findings if workitems.is_error(f)]
                self.assertEqual(bool(errs), expect_err, findings)
                self.assertTrue(any(needle in f for f in errs), errs)

    def test_validate_repo_rollback_warning_spurious_warning_and_same_timestamp_error(self) -> None:
        env_yaml = "environments:\n  - name: production\n    production: true\n"
        _, c0 = _init_release_repo(self.root, env_yaml)
        _write_spec(self.root, "SPEC-1")
        _write_spec(self.root, "SPEC-2")
        c1 = _commit_with_time(self.root, "add two specs", "2026-11-20T10:00:00Z")

        rel_dir = self.root / "docs" / "releases"
        rel_dir.mkdir(parents=True, exist_ok=True)
        # First release holds SPEC-1 and SPEC-2.
        (rel_dir / "production-2026-11-20-1.md").write_text(
            f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T11:00:00Z"\ncommit: "{c1}"\nspecs: ["SPEC-1", "SPEC-2"]\nrolled_back: []\n---\n',
            encoding="utf-8",
        )
        # Second release rolls back to c0, names only SPEC-1 (missing SPEC-2 -> warning), plus spurious SPEC-9 (warning).
        (rel_dir / "production-2026-11-20-2.md").write_text(
            f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T12:00:00Z"\ncommit: "{c0}"\nspecs: []\nrolled_back: ["SPEC-1", "SPEC-9"]\n---\n',
            encoding="utf-8",
        )
        # Third release shares identical released_at instant with second (different tz format -> error).
        (rel_dir / "production-2026-11-20-3.md").write_text(
            f'---\ntype: release\nenvironment: "production"\nreleased_at: "2026-11-20T14:00:00+02:00"\ncommit: "{c0}"\nspecs: []\nrolled_back: []\n---\n',
            encoding="utf-8",
        )
        errs, warns = workitems.check_repo(self.root)
        self.assertTrue(any("matches" in e and "production-2026-11-20-2.md" in e for e in errs), errs)
        self.assertTrue(any("SPEC-2" in w and "rolled_back" in w for w in warns), warns)
        self.assertTrue(any("SPEC-9" in w and "rolled_back" in w for w in warns), warns)

    def test_validate_shallow_clone_unreadable_commit_warns_instead_of_error(self) -> None:
        _, _ = _init_release_repo(self.root, "environments:\n  - name: production\n    production: true\n")
        _write_spec(self.root, "SPEC-1")
        c1 = _commit_with_time(self.root, "c1", "2026-11-20T10:00:00Z")
        workitems.new_release(self.root, "production", c1, released_at="2026-11-20T11:00:00Z")
        helpers.git(self.root, "add", "-A")
        _commit_with_time(self.root, "commit release", "2026-11-20T11:05:00Z")
        shallow = Path(self.tmp.name).resolve() / "shallow"
        helpers.git(self.root.parent, "clone", "-q", "--depth", "1", f"file://{self.root}", str(shallow))
        errs, warns = workitems.check_repo(shallow)
        self.assertEqual(errs, [])
        self.assertTrue(any(workitems.SHALLOW_NOTE in w for w in warns), warns)
