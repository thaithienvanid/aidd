"""What Spec approval freezes: proof after a base merge, lock order, fences, the emergency window, design paths, and generated docs."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, decide, example, git, rules  # noqa: F401  (ROOT puts src on sys.path)

from aidd import config, docs, gates, inputs, model


@unittest.skipUnless(shutil.which("git"), "git is required")
class G1ProofTests(unittest.TestCase):
    def test_merging_the_base_in_later_does_not_widen_the_approval_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            git(t, "init", "-q", "-b", "main")
            for k, v in (("user.email", "a@example.com"), ("user.name", "A"), ("commit.gpgsign", "false")):
                git(t, "config", k, v)
            (t / "a.txt").write_text("a", encoding="utf-8")
            git(t, "add", ".")
            git(t, "commit", "-qm", "base")
            git(t, "checkout", "-qb", "feat")
            (t / "specs").mkdir()
            (t / "specs/S.md").write_text("s", encoding="utf-8")
            git(t, "add", ".")
            git(t, "commit", "-qm", "spec")
            approved = git(t, "rev-parse", "HEAD")
            git(t, "checkout", "-q", "main")
            (t / "other.txt").write_text("o", encoding="utf-8")
            git(t, "add", ".")
            git(t, "commit", "-qm", "main moves")
            git(t, "checkout", "-q", "feat")
            git(t, "merge", "-q", "--no-edit", "main")
            head = git(t, "rev-parse", "HEAD")
            base = git(t, "merge-base", "main", head)
            got = inputs.approval_commits(str(t), base, head, [{"body": f"/aidd approve-spec S {'0' * 32} {approved}"}])
            self.assertEqual(got[approved], {"ancestor": True, "paths": ["specs/S.md"]})


class LockOrderTests(unittest.TestCase):
    def test_a_lock_binds_a_sibling_listed_before_it(self):
        org = 'aidd_version = "1.0.0"\nprofile = "org"\nlocks = ["scope_exempt_paths"]\n'
        evil = 'aidd_version = "1.0.0"\nprofile = "org"\nscope_exempt_paths = ["src/**"]\n'
        child = 'aidd_version = "1.0.0"\nprofile = "org"\nextends = [{ path = "evil.toml" }, { path = "org.toml" }]\n[owners]\napprovers = ["@x"]\n'
        cfg = config.load_text(child, prefetched={"evil.toml": evil, "org.toml": org})
        self.assertIsNone(cfg.get("scope_exempt_paths"))
        self.assertTrue(any("locked by another parent" in w for w in cfg.warnings), cfg.warnings)


class FenceTests(unittest.TestCase):
    def test_a_shorter_or_labelled_fence_does_not_close_a_longer_one(self):
        body = "````\n```\n/aidd approve " + "a" * 40 + "\n```python\n````\n/aidd approve " + "b" * 40
        self.assertEqual(gates.APPROVE.findall(gates.commands(body)), ["b" * 40])


class EmergencyWindowTests(unittest.TestCase):
    def test_a_fresh_push_restarts_the_window(self):
        ctx = example("05-emergency-under-freeze")  # review_due 2026-09-24
        ctx["change"]["created_at"] = "2026-09-23T10:00:00Z"
        self.assertNotIn("emergency", rules(decide(ctx), "fail"))
        # An old change turned into an emergency needs a fresh push, and the window starts there.
        ctx["head_pushed_at"] = ctx["now"] = "2026-09-26T10:00:00Z"
        self.assertIn("emergency", rules(decide(ctx), "fail"))


class DesignPathTests(unittest.TestCase):
    """design.files: what the Spec approval covers for a user-facing change, frozen like the tests."""

    def with_design(self, declare):
        ctx = example("02-normal-feature")
        if declare:
            spec = ctx["head_files"]["specs/SPEC-220.md"]
            ctx["head_files"]["specs/SPEC-220.md"] = spec.replace("[tests]", '[design]\nfiles = ["docs/design/SPEC-220/**"]\n\n[tests]', 1)
        ctx["files"].append({"path": "docs/design/SPEC-220/flow.md", "previous_path": None, "additions": 900, "deletions": 0})
        return decide(ctx)

    def test_declared_design_files_are_in_scope_and_outside_the_budget(self):
        self.assertNotIn("scope", rules(self.with_design(True), "fail"))
        self.assertNotIn("budget", rules(self.with_design(True), "fail"))

    def test_undeclared_design_files_are_out_of_scope(self):
        self.assertIn("scope", rules(self.with_design(False), "fail"))

    def test_a_design_edit_voids_the_approval(self):
        spec = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"].replace("[tests]", '[design]\nfiles = ["docs/design/**"]\n\n[tests]', 1)
        tree = {"docs/design/a.svg": "1" * 40}
        self.assertNotEqual(model.spec_hash(spec, tree), model.spec_hash(spec, {"docs/design/a.svg": "2" * 40}))

    def test_scope_may_not_cover_the_design(self):
        spec = example("02-normal-feature")["head_files"]["specs/SPEC-220.md"].replace(
            "[tests]", '[design]\nfiles = ["src/checkout/rate_limit/mock.svg"]\n\n[tests]', 1
        )
        data, body = model.split_front_matter(spec, "s")
        self.assertTrue(any("design file" in e for e in model.lint_spec(data, body)))


class SpecHashFramingTests(unittest.TestCase):
    """The hash covers one canonical document, so no part can stand in for another."""

    def setUp(self):
        ctx = example("02-normal-feature")
        self.text, self.tree = ctx["head_files"]["specs/SPEC-220.md"], ctx["head_tree"]
        self.test = "tests/checkout/test_rate_limit.py"

    def test_a_deleted_test_carried_in_the_body_changes_the_hash(self):
        # Separator bytes in the body would reproduce a path/blob framing exactly if the parts were concatenated.
        smuggled = self.text.rstrip("\n") + "\0" + self.test + "\0" + self.tree[self.test] + "\n"
        tree = {k: v for k, v in self.tree.items() if k != self.test}
        self.assertNotEqual(model.spec_hash(self.text, self.tree), model.spec_hash(smuggled, tree))

    def test_moving_text_between_the_body_and_a_file_changes_the_hash(self):
        tree = dict(self.tree, **{self.test: self.tree[self.test] + "x"})
        self.assertNotEqual(model.spec_hash(self.text, self.tree), model.spec_hash(self.text, tree))

    def test_a_spec_with_a_control_character_is_invalid(self):
        _, _, errors = model.load_object(self.text.replace("## ", "## \x1b[8m", 1), "spec")
        self.assertTrue(any("control character" in e for e in errors), errors)

    def test_tabs_and_line_endings_are_allowed(self):
        _, _, errors = model.load_object(self.text.replace("\n", "\r\n").replace("  ", "\t", 1), "spec")
        self.assertFalse(any("control character" in e for e in errors), errors)


class DocsTests(unittest.TestCase):
    def test_a_narrowed_enum_keeps_its_values(self):
        self.assertEqual(
            docs._type({"allOf": [{"$ref": "common.schema.json#/$defs/route"}, {"enum": ["normal", "major"]}]}, "spec.schema.json"), "`normal` \\| `major`"
        )


if __name__ == "__main__":
    unittest.main()
