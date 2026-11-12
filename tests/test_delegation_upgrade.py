"""`aidd upgrade` renames and cuts keys of an approved Spec. Compared with the approval commit, that alone is no revision: both
sides read in today's shape (`workitems.todays_shape`), so nothing waits for a person for a change that altered nothing. A real
change still does, and a frozen test file is still compared by its bytes. Split from test_delegation_spec_changes to keep each
file inside the test budget."""

import unittest

from helpers import SAMPLE_SPEC, git
from test_delegation_spec import SpecCase

from aidd import workitems
from aidd.delegation import local_run

OLD_KEYS = {"aidd_version": '"1.0.0"', "assisted_by": "[]", "labels": "[area:x]", "blockers": "legal"}


def old_spec() -> str:
    text = SAMPLE_SPEC.replace("route: normal", "status: ready\nroute: normal").replace("new_behavior: true", "new_behavior: true\n      retries: 2")
    return text.replace("type: spec", "".join(f"{k}: {v}\n" for k, v in OLD_KEYS.items()) + "type: spec", 1)


def upgraded(text: str) -> str:
    """The same Spec as `aidd upgrade` leaves it."""
    for key in ("aidd_version", "assisted_by", "labels"):
        text = "".join(line + "\n" for line in text.splitlines() if not line.startswith(f"{key}:"))
    return text.replace("blockers:", "waiting_on:").replace("retries:", "reruns:")


class UpgradeAfterApprovalTests(SpecCase):
    def test_a_pure_migration_is_no_revision_and_a_migration_that_changes_anything_else_still_differs(self):
        repo, approval = self.spec_repo(spec_text=old_spec())
        migrated = upgraded(old_spec())
        cases = {
            "a pure migration": (migrated, {}, ""),
            "a changed rerun count": (migrated.replace("reruns: 2", "reruns: 0"), {}, "`tests` block differs"),
            "a command made not new behavior": (migrated.replace("new_behavior: true", "new_behavior: false"), {}, "`tests` block differs"),
            "a frozen test file changed": (migrated, {"tests/test_discount.py": "import unittest\n"}, "differ from the approved commit"),
        }
        for name, (text, tests, said) in cases.items():
            with self.subTest(name):
                git(self.root, "reset", "-q", "--hard", approval)
                repo.write("specs/SPEC-220.md", text)
                for path, body in tests.items():
                    repo.write(path, body)
                head = repo.commit("The head")
                data, _, errs = workitems.load_object(text, "specs/SPEC-220.md")
                self.assertEqual(errs, [], "the head is valid in today's shape")
                found = local_run.frozen_problem(str(self.root), head, "specs", ("specs/SPEC-220.md", data), approval)
                self.assertIn(said, found) if said else self.assertEqual(found, "")

    def test_the_head_is_read_as_it_is(self):
        """A Spec that still holds a retired name fails its own load, so the old shape never reaches the head."""
        self.assertTrue(workitems.load_object(old_spec(), "specs/SPEC-220.md")[2])
        self.assertEqual(workitems.load_object(old_spec(), "specs/SPEC-220.md", read_old_shape=True)[2], [])


if __name__ == "__main__":
    unittest.main()
