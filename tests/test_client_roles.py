"""The client lifecycle as data and as roles: qualification, the RAID log, and milestones on the proposal; the contract,
the support SLA, and the vendor register as living docs; handover inside the runbook and the acceptance record; and the
delivery manager who keeps them.

The RAID log is the proposal's own fields (`risks` beside `assumptions`, `issues`, and `dependencies`), never a new
tracker. Kickoff extends the brief and the proposal's Delivery section, and handover extends the runbook and the
acceptance record, so neither adds a file. Neither new role approves anything: the client's decisions, the price, and
the legal terms stay with humans.
"""

import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, run_cli

from aidd import config
from aidd.docsgen import counts
from aidd.workitems import validation
from aidd.workitems import due_dates
from aidd.workitems import authoring
from aidd.workitems import proposal, spec_file
from aidd.knowledge import owners, team_registry
from aidd.kernel import resources
from aidd.kernel import text as kernel_text

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
NEW_ROLES = ("delivery-manager",)

PROPOSAL = """---
aidd_version: "1.0.0"
kind: proposal
id: PROP-7
title: Dealer portal
audience: client
addressee: Acme Corp procurement
goal: Dealers track orders and download invoices without calling us
status: accepted
go_no_go: {{ decision: "go", by: "@lead", decided_on: "2026-09-01" }}
sign_off: {{ by: "@lead", decided_on: "2026-09-10" }}
outcome: {{ decision: "accepted", by: "@lead", decided_on: "2026-09-20" }}
exclusions: [Native mobile apps]
{extra}
qualification:
  fit: A portal like two we built
  budget: "Capped at EUR 120k, confirmed by the CFO"
  authority: The head of sales signs; procurement runs the process
  decision_process: "Shortlist of three, demo, then a vote"
  recommendation: go

assumptions:
  - id: A-1
    text: Acme provides a read-only ERP export
    owner: Acme IT
    status: open
    due: "2026-10-15"

issues:
  - id: I-1
    text: The staging tenant is not provisioned
    owner: "@ops"
    status: open

dependencies:
  - id: D-1
    text: The payment provider's sandbox account
    owner: Acme finance
    status: resolved

milestones:
  - id: M-1
    name: Deposit
    due: "2026-10-01"
    amount: 24000
    currency: EUR
    trigger: {{ event: "contract signed" }}
    invoice_ref: INV-2026-041

  - id: M-2
    name: Order tracking live
    due: "2026-12-15"
    amount: 48000
    currency: EUR
    trigger: {{ specs: ["SPEC-12"], acceptance: ["SPEC-12:A1", "SPEC-12:A2"] }}

needs:
  - id: N-1
    need: Track orders
    answer: met
    epic: Orders

risks:
  - id: R-1
    text: The ERP export is late
    owner: "@pm"
    status: open
    likelihood: medium
    impact: high
    mitigation: Start on a fixture export
---

## Summary
"""


def load(extra: str = "", **replace: str) -> tuple[dict, list[str]]:
    text = PROPOSAL.format(extra=extra)
    for old, new in replace.items():
        if old not in text:
            raise AssertionError(f"the fixture has no {old!r}")
        text = text.replace(old, new)
    data, _, errors = spec_file.load_object(text, "proposals/PROP-7/proposal.md")
    return data, errors


class ProposalFieldTests(unittest.TestCase):
    """Qualification, the RAID log, and milestones are proposal fields, checked by the schema."""

    def test_a_full_proposal_validates(self):
        data, errors = load()
        self.assertEqual(errors, [])
        self.assertEqual(data["qualification"]["recommendation"], "go")
        self.assertEqual([m["id"] for m in data["milestones"]], ["M-1", "M-2"])

    def test_raid_items_carry_an_owner_and_a_status(self):
        sch = resources.load_json("proposal.schema.json")
        for field in ("assumptions", "issues", "dependencies"):
            self.assertIn(field, sch["properties"], field)
        item = sch["$defs"]["raid_item"]
        self.assertEqual(set(item["required"]), {"id", "text", "owner", "status"})
        self.assertIn("due", item["properties"])
        _, errors = load(**{"status: resolved": "status: maybe"})
        self.assertTrue(errors, "an unknown RAID status is refused")
        _, errors = load(**{'    owner: "@ops"\n': ""})
        self.assertTrue(errors, "an issue without an owner is refused")

    def test_a_plain_assumption_is_refused(self):
        text = PROPOSAL.format(extra="assumptions: [The ERP export exists]").replace(
            'assumptions:\n  - id: A-1\n    text: Acme provides a read-only ERP export\n    owner: Acme IT\n    status: open\n    due: "2026-10-15"\n\n', ""
        )
        _, _, errors = spec_file.load_object(text, "p.md")
        self.assertTrue(errors, "an assumption is a RAID item with an owner and a status")

    def test_a_milestone_names_its_trigger_and_its_currency(self):
        _, errors = load(**{"currency: EUR\n    trigger: { event": "currency: eur\n    trigger: { event"})
        self.assertTrue(errors, "a currency is an ISO 4217 code")
        _, errors = load(**{'    trigger: { event: "contract signed" }\n': ""})
        self.assertTrue(errors, "a milestone without a trigger is refused")
        _, errors = load(**{'trigger: { event: "contract signed" }': "trigger: {}"})
        self.assertTrue(errors, "an empty trigger is refused")
        _, errors = load(**{"    amount: 24000\n    currency: EUR\n": "    amount: 24000\n"})
        self.assertTrue(errors, "an amount needs its currency")

    def test_qualification_keeps_the_decision_with_a_person(self):
        q = resources.load_json("proposal.schema.json")["properties"]["qualification"]
        self.assertEqual({"fit", "budget", "authority", "decision_process", "recommendation"}, set(q["properties"]))
        self.assertEqual(set(q["properties"]["recommendation"]["enum"]), {"go", "no_go", "ask"})
        self.assertIn("go_no_go", q["description"])

    def test_an_initiative_carries_milestones(self):
        text = (
            '---\naidd_version: "1.0.0"\nkind: initiative\nid: INIT-1\ntitle: Portal\ngoal: "Dealers self-serve 80% of order questions"\n'
            'milestones:\n  - id: M-1\n    name: Go-live\n    due: "2027-01-10"\n    trigger: {specs: [SPEC-12]}\n---\n'
        )
        _, _, errors = spec_file.load_object(text, "specs/INIT-1.md")
        self.assertEqual(errors, [])
        self.assertIn("milestones", resources.load_json("initiative.schema.json")["properties"])

    def test_the_template_starts_every_field(self):
        text = (ASSETS / "proposal.md").read_text(encoding="utf-8")
        for field in ("\nqualification:", "\nassumptions:", "\n# issues:", "\n# dependencies:", "\n# milestones:", "\nrisks:"):
            self.assertIn(field, text, field)
        filled = kernel_text.fill_template(text, id="PROP-1", title="T", audience="client", addressee="A", owner_team="t", today="2026-09-30")
        _, _, errors = spec_file.load_object(filled, "proposal.md")
        self.assertEqual(errors, [])
        delivery = text.split("## Delivery", 1)[1].split("\n## ", 1)[0]
        for item in ("Kickoff agenda", "Access provisioning", "Tenant and environment setup", "Communication cadence", "Milestones", "RAID"):
            self.assertIn(item, delivery, item)

    def test_the_matrix_renders_the_raid_log_and_milestones(self):
        data, _ = load()
        out = proposal.proposal_matrix(data)
        for heading in ("## Assumptions", "## Issues", "## Dependencies", "## Milestones", "## Risks"):
            self.assertIn(heading, out, heading)
        self.assertIn("| A-1 | Acme provides a read-only ERP export | Acme IT | open | 2026-10-15 |", out)
        self.assertIn("| M-2 | Order tracking live | 2026-12-15 | 48000 EUR | SPEC-12; SPEC-12:A1, SPEC-12:A2 |", out)
        self.assertIn("| R-1 | The ERP export is late | @pm | open | medium | high | Start on a fixture export |", out)

    def test_convert_carries_the_milestones_to_the_initiative(self):
        data, _ = load()
        with tempfile.TemporaryDirectory() as d:
            paths = proposal.convert_proposal(data, Path(d))
            init = next(p for p in paths if p.name.startswith("INIT-"))
            parsed, _, errors = spec_file.load_object(init.read_text(encoding="utf-8"), str(init))
            self.assertEqual(errors, [])
            self.assertEqual([m["id"] for m in parsed["milestones"]], ["M-1", "M-2"])
            self.assertEqual(parsed["milestones"][1]["trigger"]["acceptance"], ["SPEC-12:A1", "SPEC-12:A2"])


class ClientDocTests(unittest.TestCase):
    """The contract (SOW) with its support levels, in the proposal's folder, and the repository's vendor register."""

    def test_the_kinds_are_wired_everywhere(self):
        spec_kinds = resources.load_json("spec.schema.json")["$defs"]["doc"]["properties"]["kind"]["enum"]
        required = resources.load_json("config.schema.json")["properties"]["docs"]["properties"]["required"]["properties"]
        self.assertIn("contract", authoring.DOC_KINDS_NEW)
        self.assertEqual(authoring.REPO_DOCS["vendors"], (("{docs}/vendors.md", "vendors.md"),))
        self.assertIn("vendors", authoring.LIVING_DOCS)
        for where in (config.DOC_KINDS, spec_kinds, required):
            self.assertIn("vendors", where)
        writes = team_registry.roles()["roles"]["delivery-manager"]["writes"]
        self.assertIn("docs/vendors.md", writes)
        self.assertIn("{proposals_dir}", writes)

    def test_the_contract_is_a_base_never_legal_advice(self):
        text = (ASSETS / "contract.md").read_text(encoding="utf-8")
        for section in (
            "## Scope",
            "## Deliverables",
            "## Milestones",
            "## Assumptions and exclusions",
            "## Change control",
            "## Acceptance",
            "## Warranty",
            "## Intellectual property and licensing",
            "## Confidentiality",
        ):
            self.assertIn(section, text, section)
        self.assertIn("not legal advice", text)
        self.assertGreaterEqual(text.count("for a person or a lawyer"), 2)
        self.assertIn("change order", text.split("## Change control", 1)[1].split("\n## ", 1)[0])
        self.assertIn("Acceptance id", text.split("## Scope", 1)[1].split("\n## ", 1)[0])

    def test_the_contract_names_support_targets_by_severity(self):
        text = (ASSETS / "contract.md").read_text(encoding="utf-8")
        support = text.split("## Support and service levels", 1)[1].split("\n## ", 1)[0]
        for item in ("Tiers", "Channels and hours", "Response", "Resolution", "Escalation", "Maintenance windows", "Exclusions", "Reporting"):
            self.assertIn(item, support, item)
        for severity in ("S1", "S2", "S3", "S4"):
            self.assertIn(f"| {severity} |", support, severity)

    def test_the_vendor_register_columns(self):
        text = (ASSETS / "vendors.md").read_text(encoding="utf-8")
        header = next(line for line in text.splitlines() if line.startswith("| Vendor"))
        for column in ("Service", "Data shared", "DPA", "SLA", "Renewal date", "Owner"):
            self.assertIn(column, header, column)
        self.assertIn("data map", text.lower(), "the register points at the data map's processors")

    def test_handover_extends_the_runbook_and_the_acceptance_record(self):
        for name in ("runbook.md", "acceptance.md"):
            text = (ASSETS / name).read_text(encoding="utf-8")
            section = text.split("## Handover", 1)[1].split("\n## ", 1)[0]
            for item in ("Docs index", "Credentials transfer", "Training", "Open issues", "Warranty start"):
                self.assertIn(item, section, (name, item))
            self.assertIn("never a secret", section.lower(), name)

    def test_aidd_new_writes_the_register_and_the_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (path,) = authoring.new_repo_doc(root, kind="vendors")
            self.assertEqual(path.relative_to(root).as_posix(), "docs/vendors.md")
            self.assertNotIn("{{", path.read_text(encoding="utf-8"))
            (root / "proposals" / "PROP-7").mkdir(parents=True)
            (root / "proposals" / "PROP-7" / "proposal.md").write_text("x", encoding="utf-8")
            contract = authoring.new_contract(root, "PROP-7")
            self.assertEqual(contract.relative_to(root).as_posix(), "proposals/PROP-7/contract.md")
            self.assertNotIn("{{", contract.read_text(encoding="utf-8"))

    def test_the_cli_says_where_each_belongs(self):
        code, out = run_cli("new", "vendors", "acme")
        self.assertNotEqual(code, 0)
        self.assertIn("belongs to the repository", out)
        code, out = run_cli("new", "contract")
        self.assertNotEqual(code, 0)
        self.assertIn("proposal id", out)


VENDORS = """# Vendor register: acme

| Vendor | Service | Data shared | DPA | SLA | Renewal date | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| Mailer Inc | Transactional email | customer email | signed 2026-01-10 | 99.9% | {soon} | @ops |
| Hostco | Hosting | everything | signed 2025-05-01 | 99.95% | {later} | @cto |
| TODO | TODO | TODO | TODO | TODO | YYYY-MM-DD | TODO |
"""


class VendorRenewalTests(unittest.TestCase):
    """`aidd validate` warns when a vendor's renewal date is within 30 days, or has passed."""

    TODAY = dt.date(2026, 9, 30)

    def warnings(self, soon: str, later: str = "2027-06-01") -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a", "@b"]\n', encoding="utf-8")
            (root / "specs").mkdir()
            (root / "specs" / "SPEC-1.md").write_text(
                '---\naidd_version: "1.0.0"\nkind: spec\nid: SPEC-1\ntitle: Vendors\n\ndocs:\n  - kind: vendors\n    path: docs/vendors.md\n    frozen: false\n---\n',
                encoding="utf-8",
            )
            (root / "docs").mkdir()
            (root / "docs" / "vendors.md").write_text(VENDORS.format(soon=soon, later=later), encoding="utf-8")
            _, warnings = validation.check_repo(root, today=self.TODAY)
            return [w for w in warnings if "renewal" in w]

    def test_a_renewal_within_30_days_warns(self):
        (w,) = self.warnings("2026-10-20")
        self.assertIn("docs/vendors.md", w)
        self.assertIn("Mailer Inc", w)
        self.assertIn("2026-10-20", w)
        self.assertIn("@ops", w)

    def test_a_passed_renewal_warns(self):
        (w,) = self.warnings("2026-09-01")
        self.assertIn("passed", w)

    def test_a_distant_renewal_and_a_placeholder_do_not(self):
        self.assertEqual(self.warnings("2026-11-15"), [])
        self.assertEqual(due_dates.vendor_renewals("| Vendor | Renewal date |\n| --- | --- |\n| X | soon |\n", self.TODAY), [])


class ClientRolesTests(unittest.TestCase):
    """The delivery manager: registered, wired into flows and handoffs, and never approving."""

    def setUp(self):
        self.data = team_registry.roles()

    def test_the_roster_is_seventeen(self):
        self.assertEqual(len(self.data["order"]), 17)
        self.assertEqual(counts.count("roles"), 17)
        for key in NEW_ROLES:
            self.assertIn(key, self.data["order"])

    def test_the_delivery_manager(self):
        r = self.data["roles"]["delivery-manager"]
        self.assertEqual(r["tier"], "execution")
        self.assertIn("Plan", r["steps"])
        self.assertIn("Ship", r["steps"])
        self.assertFalse(r["in_scope"])
        self.assertIn("{proposals_dir}", r["writes"])
        self.assertNotIn("docs/specs/client/**", r["writes"])
        self.assertNotIn("{scope}", r["writes"])
        self.assertNotIn("{tests}", r["writes"])
        self.assertIn("client-delivery", r["practices"])

    def test_the_agent_files_keep_headroom(self):
        for key in NEW_ROLES:
            text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(text.encode()), 9 * 1024 - 1536, key)
            self.assertIn(f"<!-- aidd:gen role:{key} -->", text)
            for section in ("## Playbook", "## Definition of Done", "## Stop and hand back"):
                self.assertIn(section, text, (key, section))
            self.assertIn("never", text.split("<!-- aidd:end -->", 1)[1].lower())

    def test_the_delivery_manager_never_approves_or_prices(self):
        text = (TEAM / "agents" / "delivery-manager.md").read_text(encoding="utf-8")
        tail = text.split("<!-- aidd:end -->", 1)[1]
        for must in ("aidd digest --client", "change order", "Handover", "price"):
            self.assertIn(must, tail, must)

    def test_the_product_manager_triages_into_suggested_specs(self):
        tail = (TEAM / "agents" / "product-manager.md").read_text(encoding="utf-8").split("<!-- aidd:end -->", 1)[1]
        for must in ("aidd import issues", "feedback log", "support-desk"):
            self.assertIn(must, tail, must)
        # It suggests Specs from incoming issues, and is one of the default proactive roles.
        self.assertIn("product-manager", owners.DEFAULT_PROACTIVE_ROLES)

    def flow(self, command: str) -> dict:
        return next(f for f in self.data["loop"]["flows"] if f["command"] == command)

    def test_propose_starts_with_qualification_and_drafts_the_delivery(self):
        runs = self.flow("propose")["runs"]
        self.assertEqual(runs[0], ["delivery-manager"])
        self.assertTrue(any("delivery-manager" in g and len(g) > 1 for g in runs[1:]), "the delivery section is drafted with the specialists")
        text = (TEAM / "commands" / "propose.md").read_text(encoding="utf-8")
        step1 = text.split("<!-- aidd:end -->", 1)[1].split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        self.assertIn("aidd-team:delivery-manager", step1)
        for word in ("fit", "budget", "authority", "decision process", "qualification"):
            self.assertIn(word, step1, word)
        self.assertIn("## Delivery", text)

    def test_handover_is_a_command_of_its_own(self):
        f = self.flow("handover")
        self.assertEqual({r for g in f["runs"] for r in g}, {"delivery-manager", "tech-writer", "sre"})
        self.assertIn("Ship", f["steps"])
        text = (TEAM / "commands" / "handover.md").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", text)
        for must in ("Handover", "runbook", "acceptance record", "never a secret", "warranty"):
            self.assertIn(must, text, must)
        commands = [x["command"] for x in self.data["loop"]["flows"]]
        self.assertEqual(commands.index("handover"), commands.index("ship") + 1)

    def test_the_retro_is_the_coachs(self):
        self.assertEqual(self.flow("retro")["runs"], [["agile-coach"]])

    def test_both_roles_hand_off_through_files(self):
        senders = {r for h in self.data["loop"]["handoffs"] for r in h["from"]}
        self.assertLessEqual(set(NEW_ROLES), senders)
        to_dm = [h for h in self.data["loop"]["handoffs"] if "delivery-manager" in h["to"]]
        self.assertTrue(to_dm, "the handover docs come back to the delivery manager")

    def test_the_12207_map_names_them(self):
        by = {c["process"]: c["by"] for c in self.data["loop"]["capabilities"]["processes"]}
        self.assertIn("delivery-manager", by["Supply"])
        self.assertIn("delivery-manager", by["Acquisition"])
        self.assertIn("/aidd-team:handover", by["Transition"])
        self.assertIn("delivery-manager", by["Operation"])
        self.assertIn("product-manager", by["Maintenance"])

    def test_the_manifests_and_router_name_them(self):
        router = (TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
        plugin = (TEAM / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        for key in (*NEW_ROLES, "handover"):
            self.assertIn(key, router, key)
            self.assertIn(key, plugin, key)
        self.assertIn(f"<!-- aidd:gen count:roles -->{counts.count('roles')}<!-- aidd:end --> roles", (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8"))


class ClientDocsTests(unittest.TestCase):
    def test_the_how_to_runs_an_engagement_end_to_end(self):
        text = (ROOT / "docs" / "HOW-TO.md").read_text(encoding="utf-8")
        section = text.split("## Run a client engagement end to end", 1)[1].split("\n## ", 1)[0]
        steps = re.findall(r"^\d+\. \*\*([^*]+)\.\*\* (.+)$", section, re.M)
        self.assertEqual([s[0] for s in steps], ["Qualify", "Propose", "Contract", "Start", "Deliver", "Change the scope", "Accept", "Hand over", "Support"])
        musts = [
            "/aidd-team:propose",
            "milestones",
            "aidd new contract",
            "Kickoff",
            "aidd digest",
            "change order",
            "aidd new acceptance",
            "/aidd-team:handover",
            "Support and service levels",
        ]
        for (label, text), must in zip(steps, musts, strict=True):
            self.assertIn(must, text, label)

    def test_the_glossary(self):
        text = (ROOT / "docs" / "GLOSSARY.md").read_text(encoding="utf-8")
        for term in ("RAID log", "Milestone", "Contract (SOW)", "Support SLA", "Handover", "Vendor register", "Qualification"):
            self.assertRegex(text, rf"\|\s*\*?\*?{re.escape(term)}", term)

    def test_the_changelog(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        for must in ("delivery-manager", "fallback", "/aidd-team:handover", "aidd new contract"):
            self.assertIn(must, text, must)

    def test_the_schemas_use_only_supported_keywords(self):
        # The schema itself is well-formed for the validator (no unsupported keyword).
        from helpers import unsupported_keywords

        for name in ("proposal.schema.json", "initiative.schema.json"):
            self.assertEqual(unsupported_keywords(resources.load_json(name)), set(), name)


if __name__ == "__main__":
    unittest.main()
