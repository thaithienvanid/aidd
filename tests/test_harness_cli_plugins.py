"""No second copy of the launcher or the source in a harness's plugin package.

Only Claude Code documents a plugin `bin/` folder that puts an executable on the agent's PATH, so `aidd-cli` is the
one package that gives the `aidd` command (plugins/README.md, "The `aidd` command in other coding agents"). A package
for another harness may ship once its documentation says it works, and it must link to `scripts/aidd` and the source.
"""

from __future__ import annotations

import os
import unittest

from helpers import IN_GIT_CHECKOUT, ROOT


class HarnessCliPluginsTest(unittest.TestCase):
    @unittest.skipUnless(IN_GIT_CHECKOUT, "the sdist leaves the folder links out")
    def test_no_package_holds_its_own_copy_of_the_launcher_or_the_source(self):
        launcher = (ROOT / "scripts" / "aidd").resolve()
        for plugin in sorted(p for p in (ROOT / "plugins").iterdir() if p.is_dir()):
            for found in plugin.rglob("aidd"):
                if not found.resolve().is_dir():
                    with self.subTest(path=found.relative_to(ROOT).as_posix()):
                        self.assertTrue(found.is_symlink(), "a copy of the launcher drifts; link to scripts/aidd")
                        self.assertEqual(found.resolve(), launcher)
                        self.assertFalse(os.path.isabs(os.readlink(found)), "link relatively")
            src = plugin / "src"
            if src.exists() or src.is_symlink():
                with self.subTest(path=src.relative_to(ROOT).as_posix()):
                    self.assertTrue(src.is_symlink(), "a copy of the source drifts; link to src/")
                    self.assertEqual(src.resolve(), (ROOT / "src").resolve())


if __name__ == "__main__":
    unittest.main()
