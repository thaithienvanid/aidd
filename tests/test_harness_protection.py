"""Every path an agent harness reads as instructions or runs as a hook is a protected path.

An agent that can rewrite its own instructions or hooks in a minor change has no limits. The protected
set is derived from `harnesses.HARNESSES`, so these tests fail when a harness gains a signal, a pointer
file, or a native agent folder that the derivation does not cover.
"""

import unittest

import helpers  # noqa: F401  # puts src/ on the path

from aidd.config import baseline, harnesses
from aidd.kernel import globs, resources


def protected(path: str) -> bool:
    return globs.match_any(baseline.baseline_data()["protected_paths"], path, fold_case=True)


class HarnessProtectionTests(unittest.TestCase):
    def test_every_harness_signal_and_pointer_is_protected(self):
        missing = []
        for h in harnesses.HARNESSES.values():
            for path in (*h.repo, *((h.pointer,) if h.pointer else ()), *h.agent_dirs):
                probes = [path] if harnesses._is_file(path) else [f"{path}/x.md", f"{path}/hooks/pre.sh"]
                missing += [f"{h.key}: {p}" for p in probes if not protected(p)]
        self.assertEqual(missing, [])

    def test_executable_hook_folders_and_files_named_in_the_audit_are_protected(self):
        for path in (
            ".github/hooks/pre-tool.json",
            "QWEN.md",
            ".opencode/plugin/guard.ts",
            "opencode.json",
            ".goosehints",
            ".rules",
            "WARP.md",
            "CONVENTIONS.md",
            ".amp/settings.json",
            ".factory/droids/x.md",
            ".agents/rules/a.md",
            ".agent/rules/a.md",
        ):
            self.assertTrue(protected(path), path)

    def test_release_and_governance_documents_are_protected_in_this_repository_not_the_baseline(self):
        """aidd's own release documents are this repository's protected paths (.aidd/config.yaml): an adopter's
        SECURITY.md or RELEASING.md is its own business, and the baseline cannot be switched off."""
        from helpers import ROOT

        from aidd import config
        from aidd.gate import routing

        mine = routing.protected_paths(config.load_file(config.CONFIG_PATH, str(ROOT)))
        for path in ("RELEASING.md", "GOVERNANCE.md", "SECURITY.md"):
            self.assertFalse(protected(path), path)
            self.assertTrue(globs.match_any(mine, path, fold_case=True), path)

    def test_the_merge_keeps_the_baseline_and_adds_no_duplicate(self):
        data = resources.load_json("baseline.json")
        raw = data["protected_paths"] + data["harness_paths"]
        merged = baseline.baseline_data()["protected_paths"]
        self.assertEqual(merged[: len(raw)], raw)
        self.assertEqual(len(merged), len(set(merged)))
        self.assertFalse(any(globs.is_catch_all(p) for p in merged))

    def test_an_ordinary_source_file_is_not_protected(self):
        for path in ("src/app.py", "docs/guide.md", "README.md", "tests/test_x.py"):
            self.assertFalse(protected(path), path)


if __name__ == "__main__":
    unittest.main()
