"""The delegate answers for `spec.approve` only on a Spec at the status that asks for approval: `ready`. The status table of a Spec says
so (`workitems.ASKS_APPROVAL`), and `test_status_transitions` holds the table."""

from __future__ import annotations

from helpers import SAMPLE_SPEC
from test_delegation_check import codes
from test_delegation_spec import SpecCase

from aidd import config


class TheDelegatesApproval(SpecCase):
    def test_a_spec_is_approved_only_from_the_status_that_asks_for_it(self):
        repo, _ = self.spec_repo()
        for st in config.status_table("spec")["enum"]:
            with self.subTest(status=st):
                repo.write("specs/SPEC-220.md", SAMPLE_SPEC.replace("route: normal", f"status: {st}\nroute: normal"))
                head = repo.commit(f"SPEC-220 is {st}")
                self.assertEqual(
                    "spec_not_ready" in codes(self.approve(repo, head)), st != "ready"
                )  # written out, so a change to the table is a change here too
