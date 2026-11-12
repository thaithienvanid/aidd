"""The Intent on the default branch may be from before an upgrade. Invariant: the delegate reads that Intent in today's shape, so an
upgrade alone changes no label on a saved request: the request is the person's exactly when the Intent on the default branch lists
the Spec as a slice, whether the Intent holds the old `slices` list or the `phases` an upgrade made of it. A Spec the Intent does
not list, in either shape, is still the change's own claim."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from helpers import git

from aidd.delegation import parts

MINE = "specs/requests/mine.md"
TEXT = "Shoppers must be able to use a percentage discount code.\n"
# The Intent's list of slices in each shape a default branch may hold, and whether it lists SPEC-220.
SHAPES = {
    "slices, the shape before the upgrade, listing the Spec": ('aidd_version: "1.0.0"\nslices: [{id: SPEC-220, title: Discounts}]\n', True),
    "slices, listing another Spec": ('aidd_version: "1.0.0"\nslices: [{id: SPEC-300, title: Other}]\n', False),
    "slices, empty": ("slices: []\n", False),
    "phases, as the upgrade writes them, listing the Spec": ("phases: [{id: P1, name: Discounts, slices: [{id: SPEC-220, title: Discounts}]}]\n", True),
    "phases, listing the Spec in a later phase": (
        "phases: [{id: P1, name: a, slices: [{id: SPEC-1, title: a}]}, {id: P2, name: b, slices: [{id: SPEC-220, title: Discounts}]}]\n",
        True,
    ),
    "phases, listing another Spec": ("phases: [{id: P1, name: Discounts, slices: [{id: SPEC-300, title: Other}]}]\n", False),
    "phases, empty": ("phases: [{id: P1, name: Discounts, slices: []}]\n", False),
    "no list at all": ("", False),
}


class IntentShapeTests(unittest.TestCase):
    def test_the_request_is_labelled_the_same_in_every_shape_the_default_branch_holds(self):
        """One commit for each shape on one default branch; the change claims `parent: INTENT-1` and the default branch holds no Spec,
        so only the Intent's list can make the request the person's."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            git(root, "init", "-q", "-b", "main")
            (root / "specs" / "requests").mkdir(parents=True)
            (root / MINE).write_text(TEXT, encoding="utf-8")
            tips = {}
            for n, (name, (listing, _)) in enumerate(SHAPES.items()):
                intent = f"---\ntype: intent\nid: INTENT-1\ntitle: Discounts\nrequest: {MINE}\n{listing}---\n\n## Problem\n\nTODO {n}\n"
                (root / "specs" / "INTENT-1.md").write_text(intent, encoding="utf-8")
                git(root, "add", "-A")
                git(root, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", "commit", "-qm", name)
                tips[name] = git(root, "rev-parse", "HEAD")
            for name, (_, lists_it) in SHAPES.items():
                with self.subTest(name):
                    check = SimpleNamespace(top=str(root), tip=tips[name], cfg=None, spec_data={"id": "SPEC-220", "parent": "INTENT-1"})
                    self.assertEqual(parts.saved_request(check), (MINE, TEXT, lists_it))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
