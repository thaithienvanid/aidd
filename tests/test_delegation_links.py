"""Whose words the saved request is. Invariant: the packet labels a saved request the person's only when the link from this
change to it rests on nothing the change's own head controls: the Spec as the default branch holds it names the parent, or
the Intent on the default branch lists the Spec as a slice. Any other link reaches the delegate as the change's claim."""

import tempfile
from pathlib import Path

from helpers import SAMPLE_SPEC
from test_delegation_check import ENV
from test_delegation_spec import SpecCase

from aidd import delegation


class LinkTests(SpecCase):
    def fresh(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def packet(self, repo, head):
        return delegation.packet(delegation.Request(action="spec.approve", head=head, spec="SPEC-220", cwd=str(repo.root), env=ENV))

    def intent(self, iid: str, request: str, specs: str = "[]") -> str:
        return f"---\ntype: intent\nid: {iid}\ntitle: Discounts\nrequest: {request}\nphases: [{{id: P1, name: p, specs: {specs}}}]\n---\n\n## Problem\n\nTODO\n"

    def test_a_text_is_the_persons_only_when_the_link_to_it_is_not_the_changes_own(self):
        """Invariant: for every Spec, the saved request is labelled the person's only if the Spec as the default branch holds
        it names the parent, or the Intent on the default branch lists the Spec as a slice. A `parent` only the head's Spec
        holds reaches the delegate as the change's claim, so it cannot borrow another Intent's request."""
        mine, other = "specs/requests/mine.md", "specs/requests/other.md"
        main = {
            "product/intents/INTENT-1.md": self.intent("INTENT-1", mine, "[{id: SPEC-220, title: Discounts}]"),
            "product/intents/INTENT-2.md": self.intent("INTENT-2", other, "[{id: SPEC-300, title: Something else}]"),
            "product/intents/INTENT-3.md": self.intent("INTENT-3", "specs/requests/gone.md"),
            mine: "Shoppers must be able to use a percentage discount code.\n",
            other: "A request for something else entirely.\n",
        }

        def spec(parent: str | None) -> str:
            return SAMPLE_SPEC.replace("route: normal", (f"parent: {parent}\n" if parent else "") + "status: ready\nroute: normal")

        held = spec("INTENT-1")
        cases = {
            "a real link: the Intent lists the Spec": (spec("INTENT-1"), {}, ("person_request", mine)),
            "a borrowed parent: the Intent lists another Spec": (spec("INTENT-2"), {}, ("claimed_request", other)),
            "a parent whose request file is not on the default branch": (spec("INTENT-3"), {}, None),
            "a parent that is no Intent on the default branch": (spec("INTENT-9"), {}, None),
            "no parent": (spec(None), {}, None),
            "the default branch holds the Spec, and the head moves its parent": (spec("INTENT-2"), {"specs/SPEC-220.md": held}, ("person_request", mine)),
            "the default branch holds a list as the parent, and the head claims an Intent": (
                spec("INTENT-2"),
                {"specs/SPEC-220.md": spec("[INTENT-1]")},
                ("claimed_request", other),
            ),
            "the default branch holds a number as the parent, and the head claims an Intent": (
                spec("INTENT-2"),
                {"specs/SPEC-220.md": spec("5")},
                ("claimed_request", other),
            ),
            "the default branch holds an empty parent, and the head claims an Intent": (
                spec("INTENT-2"),
                {"specs/SPEC-220.md": spec('""')},
                ("claimed_request", other),
            ),
        }
        for name, (head_spec, extra, want) in cases.items():
            with self.subTest(name):
                self.fresh()
                repo, head = self.spec_repo(spec_text=head_spec, on_main={**main, **extra})
                quoted = self.packet(repo, head)["quoted"]
                kinds = [k for k in ("person_request", "claimed_request") if k in quoted]
                self.assertEqual(kinds, [want[0]] if want else [])
                if want:
                    self.assertEqual(quoted[want[0]]["data"], main[want[1]])
                    self.assertIn(want[1], quoted[want[0]]["source"])
                    self.assertEqual("claim" in quoted[want[0]]["source"], want[0] == "claimed_request")
                self.assertIn("asker", quoted["request"]["source"])

    def test_the_request_only_on_the_changes_branch_is_not_the_persons(self):
        intent = self.intent("INTENT-1", "specs/requests/r.md", "[{id: SPEC-220, title: x}]")
        repo, head = self.spec_repo(spec_text=SAMPLE_SPEC.replace("route: normal", "parent: INTENT-1\nstatus: ready\nroute: normal"))
        repo.write("product/intents/INTENT-1.md", intent)
        repo.write("specs/requests/r.md", "Written by the change.\n")
        head = repo.commit("The change writes its own request")
        quoted = self.packet(repo, head)["quoted"]
        self.assertTrue("person_request" not in quoted and "claimed_request" not in quoted)


if __name__ == "__main__":
    import unittest

    unittest.main()
