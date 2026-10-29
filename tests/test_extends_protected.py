"""A parent config the repository's config extends by path sets what the config itself sets, so an edit of it is a
protected change, routed as one, at any depth of the chain. A parent fetched by URL lives outside the repository."""

from __future__ import annotations

import unittest

import helpers  # noqa: F401  (puts src/ on the path, as for every test file)

from aidd import config
from aidd.gate import routing

VERSION = 'aidd_version: "1.0.0"\n'
BASE = VERSION + "profile: team\nextends:\n  - path: shared/aidd-base.yaml\nowners:\n  approvers: ['@lead']\n"
PARENTS = {
    "shared/aidd-base.yaml": VERSION + "profile: team\nextends:\n  - path: shared/aidd-root.yaml\n",
    "shared/aidd-root.yaml": VERSION + "profile: team\n",
}


class ExtendsProtectedTests(unittest.TestCase):
    def test_every_parent_by_path_is_protected_at_any_depth(self):
        cfg = config.load_text(BASE, prefetched=PARENTS)
        self.assertEqual(cfg.parent_paths, ("shared/aidd-base.yaml", "shared/aidd-root.yaml"))
        protected = routing.protected_paths(cfg)
        for path in PARENTS:
            with self.subTest(path=path):
                self.assertIn(path, protected)
                self.assertTrue(any(h.rule == "protected" for h in routing.scan([path], cfg)), routing.scan([path], cfg))

    def test_a_parent_path_is_protected_as_git_names_it(self):
        base = BASE.replace("path: shared/aidd-base.yaml", "path: shared//aidd-base.yaml")
        cfg = config.load_text(base, prefetched={"shared//aidd-base.yaml": PARENTS["shared/aidd-root.yaml"]})
        self.assertEqual(cfg.parent_paths, ("shared/aidd-base.yaml",))
        self.assertTrue(any(h.rule == "protected" for h in routing.scan(["shared/aidd-base.yaml"], cfg)))

    def test_a_config_with_no_parents_protects_nothing_more(self):
        cfg = config.load_text(VERSION + "profile: team\nowners:\n  approvers: ['@lead']\n")
        self.assertEqual(cfg.parent_paths, ())
        self.assertFalse(any(h.rule == "protected" for h in routing.scan(["shared/aidd-base.yaml"], cfg)))


if __name__ == "__main__":
    unittest.main()
