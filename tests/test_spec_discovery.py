"""`aidd test` finds the Spec a diff changes: only real Specs, never a plain page, a Spec's own notes, or another kind
of work item."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on the path)

from aidd import workitems


class SpecDiscoveryTests(unittest.TestCase):
    def test_only_real_specs_are_found(self):
        heads = {
            "specs/SPEC-1.md": "---\ntype: spec\nid: SPEC-1\n---\n",
            "specs/SPEC-3.md": "type: spec, but its --- lines are gone\n",  # no header: no work item, whatever its name
            "specs/ADR-0001.md": "# Use Postgres\n",  # a plain note named like a work item
            "specs/README.md": "# Specs\n",  # a plain page
            "specs/SPEC-1/notes.md": "Notes.\n",  # a Spec's own document
            "specs/EPIC-1.md": "---\ntype: epic\nid: EPIC-1\n---\n",  # parses, and is no Spec
        }
        files = [{"path": p} for p in heads]
        self.assertEqual(workitems.find_specs_in_diff(files, "specs", heads.get), ["specs/SPEC-1.md"])


if __name__ == "__main__":
    unittest.main()
