"""A practice skill cites every standard it lists, by its id, in its own text or its references.

A listed standard has two costs, and each has the check that tracks it. Its row costs about 40 estimated tokens in every load of
the skill, and the skill's size limit bounds that (`token_caps.PRACTICE_TOKENS`). It is also read again at each review date in
the standards check, and a row that no rule cites buys nothing for that review: this file holds that every listed standard is
cited. No count limits the list.

Many practice skills name some of their standards in words and cite no id for them. UNCITED names each such id, skill by skill.
Every other listed id is cited, so a standard that a skill gains is cited where its rule is written. UNCITED only shrinks, and
UNCITED_COUNT holds that.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT

from aidd.kernel import resources

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"
GENERATED = re.compile(r"<!-- aidd:gen [^>]*-->.*?<!-- aidd:end -->", re.S)
# The listed standards that a skill's text names in words and cites by no id, sorted by the skill's name. Remove an id in the
# change that cites it as `[id]` beside the rule that rests on it. Never add one: a standard that a skill gains is cited.
UNCITED: dict[str, frozenset[str]] = {
    name: frozenset(listed.split())
    for name, listed in {
        "accessible-ui": "apca-contrast wcag-3-working-draft wai-aria en-301-549 w3c-act-rules-as-the-machine apple-human-interface-guidelines-and-material",
        "adr": "madr-architecture-decision-records iso-iec-ieee-42010-stakeholders-concerns arc42-structure evolutionary-architecture-fitness-functions-as-executable",
        "ai-evals": "evals-with-golden-datasets-and-model ml-test-score evaluation-beyond-accuracy-calibration-robustness-and adversarial-ml-taxonomy-for-red-team cost-and-latency-budgets-per-request retrieval-and-agent-evaluation-rag-metrics eval-statistics-intervals-and-pass-k owasp-ai-testing-guide",
        "caching": "rfc-9111-http-caching rfc-5861-stale-content rfc-9213-targeted-cache-control rfc-9110-http-semantics",
        "ci-pipeline": "slsa cyclonedx least-privilege-ci-oidc-federation-over twelve-factor-app cis-benchmarks dora-capabilities-for-deployment-automation-and platform-as-a-product-an-internal",
        "client-delivery": "apmp-body-of-knowledge raid-log written-change-control",
        "code-review": "google-engineering-practices-the-code-review conventional-comments-labels diff-discipline-every-changed-line-traces owasp-code-review-guide ai-assisted-coding-verify-every-generated",
        "concurrency": "go-race-detector thread-sanitizer python-asyncio-task-groups nodejs-dont-block-the-event-loop",
        "data-access": "postgresql-transaction-isolation postgresql-row-locks-skip-locked rfc-9110-http-semantics",
        "debugging": "scientific-debugging agans-debugging-rules",
        "dependency-upgrade": "semantic-versioning osv-vulnerability-database openssf-scorecard slsa dependency-release-age-cooldown cvss cisa-kev-catalog coordinated-vulnerability-disclosure",
        "diagrams": "c4-model-diagrams stride-threat-modeling-with-data-flow iso-iec-ieee-42010-stakeholders-concerns",
        "estimation": "three-point-estimation reference-class-forecasting cone-of-uncertainty monte-carlo-forecasting-from-throughput",
        "incident-response": "google-sre-managing-incidents nist-sp-800-61 gdpr nis2 eu-cyber-resilience-act eu-digital-operational-resilience-act hipaa-privacy-and-security-rules sec-cybersecurity-incident-disclosure",
        "legacy-modernization": "strangler-fig-and-legacy-displacement characterization-tests-before-legacy-change expand-and-contract-parallel-change-for data-migration-reconciliation cloud-migration-strategies-7-rs",
        "maintainable-code": "comments-explain-why-not-what refactoring-catalog deep-modules linter-complexity-rules old-pattern-ratchet",
        "modular-monolith": "shopify-deconstructing-the-monolith cloudevents spring-modulith-application-events transactional-outbox dora-metrics walking-skeleton",
        "naming": "naming-as-a-process conventional-commits cloudevents opentelemetry-for-traces-metrics-and-logs iso-4217",
        "observability": "slis-slos-and-error-budgets-google the-four-golden-signals-and-the opentelemetry-for-traces-metrics-and-logs opentelemetry-genai-semconv owasp-logging-cheat-sheet twelve-factor-app post-incident-review-action-items-are",
        "performance": "the-four-golden-signals-and-the core-web-vitals-lcp-inp-cls query-plans-reviewed-for-new-queries partitioning-clustering-and-retention-tiering-conventions aws-serverless-lens use-the-index-luke postgresql-using-explain aws-wa-performance-efficiency",
        "plain-language": "asd-ste100 iso-24495-plain-language docs-under-test-every-code-sample",
        "product-defaults": "wcag core-web-vitals-lcp-inp-cls rfc-9457-problem-details idempotency-keys-and-rate-limits rfc-9562-uuid owasp-cheat-sheet-series-xss-csrf twelve-factor-app conventional-commits",
        "product-discovery": "jobs-to-be-done okrs-for-outcomes opportunity-solution-trees-and-assumption-mapping slicing-over-estimation-invest-small-means wsjf-or-moscow-prioritization product-analytics-a-measurable-key-result ears-requirements-syntax dmn-decision-tables",
        "proposal": "apmp-body-of-knowledge five-case-business-case interpretations-before-design-an-ambiguous-request",
        "prototyping": "prototype-fidelity-matched-to-the-decision plan-before-code-anti-default-review wcag design-tokens-w3c-design-tokens-format design-md-format nielsen-s-ten-usability-heuristics every-state-a-reviewer-cannot-navigate an-interactive-prototype-consumes-the-real",
        "release-rollout": "progressive-delivery-canary-blue-green-feature trunk-based-development openfeature semantic-versioning keep-a-changelog dora-metrics a-tracking-plan-for-product-analytics controlled-experiments-a-power-and-sample",
        "resilience": "timeouts-retries-backoff-jitter addressing-cascading-failures transactional-outbox integration-patterns-channel-endpoint-and-the chaos-engineering-principles-for-resilience",
        "retrospective": "inspect-and-adapt-the-retrospective-on retrospective-action-items-are-tracked-to flow-metrics-for-a-team-of kanban-flow-for-agent-teams-wip theory-of-constraints-improve-the-bottleneck five-whys-and-a3-problem-solving psychological-safety-as-the-precondition-for agent-team-operations-wip-limits-on",
        "schema-migration": "expand-and-contract-parallel-change-for reversible-migrations-tested-up-and-down migration-tooling-conventions-for-the-tool open-data-contract-standard gdpr open-table-format-for-lakehouse-tables data-observability-in-the-pipeline-freshness idempotent-restartable-pipelines-with-exactly-once",
        "secure-coding": "owasp-top-10-cwe-top-25 owasp-asvs owasp-cheat-sheet-series-xss-csrf nist-ssdf owasp-secure-coding-practices-quick-reference secrets-outside-the-repository-and-scanned rfc-9700-oauth-security-bcp nist-sp-800-63-4",
        "support-desk": "itil-4-service-desk knowledge-centered-service goodhart-s-law-a-metric-that",
        "system-design": "quality-attribute-scenarios atam-architecture-tradeoff-analysis iso-iec-25010 pre-mortems-on-major-changes-assume madr-architecture-decision-records evolutionary-architecture-fitness-functions-as-executable team-topologies-cognitive-load-and-team",
        "technical-writing": "di-taxis-tutorial-how-to-reference google-developer-documentation-style-guide keep-a-changelog docs-as-code-reviewed-versioned-generated wcag agents-md-and-agent-skills-conventions docs-for-machine-readers-an-llms",
        "test-design": "istqb-test-design-techniques-equivalence-partitioning iso-iec-ieee-29119-test-conditions bdd-and-atdd-with-gherkin the-test-pyramid-with-consumer-driven first-principles-fast-isolated-repeatable-self property-based-testing-and-fuzzing-for mutation-testing-to-judge-test-strength pairwise-combinatorial-testing-nist-sp-800-142",
        "threat-model": "stride-threat-modeling-with-data-flow owasp-asvs owasp-top-10-cwe-top-25 owasp-llm-top-10 nist-ssdf",
    }.items()
}
# How many ids UNCITED holds. An added id raises the count and fails, so the table only shrinks: lower this number in the change
# that cites an id, and never raise it.
UNCITED_COUNT = 202


def ids(entry: dict) -> list[str]:
    return [ref if isinstance(ref, str) else ref["id"] for ref in entry["standards"]]


def own_text(name: str) -> str:
    """A practice skill's hand-written text: its SKILL.md and its references, without the generated blocks, which name each
    standard by its title and would cite nothing."""
    files = [SKILLS / name / "SKILL.md", *sorted((SKILLS / name / "references").glob("*.md"))]
    return "\n".join(GENERATED.sub("", path.read_text(encoding="utf-8")) for path in files if path.exists())


def uncited(listed: list[str], text: str) -> list[str]:
    """The listed ids that `text` never cites. An id inside a longer id is no citation of it."""
    return [i for i in listed if not re.search(rf"(?<![\w-]){re.escape(i)}(?![\w-])", text)]


def findings(practices: dict, exempt: dict[str, frozenset[str]], text_of) -> list[str]:
    """Each place where the listed standards, the skills' text, and the exemptions disagree, one line each with its fix."""
    out: list[str] = []
    for name, entry in practices.items():
        missing = set(uncited(ids(entry), text_of(name)))
        allowed = exempt.get(name, frozenset())
        out += [
            f"{name}: cite `[{i}]` beside the rule that rests on it, or take it off the skill's list in schemas/roles.json" for i in sorted(missing - allowed)
        ]
        out += [f"{name}: `{i}` is cited now, or the skill no longer lists it: remove it from UNCITED" for i in sorted(allowed - missing)]
    out += [f"{name}: no practice skill has this name: remove it from UNCITED" for name in sorted(set(exempt) - set(practices))]
    return out


def count(exempt: dict[str, frozenset[str]]) -> int:
    return sum(len(listed) for listed in exempt.values())


class PracticeStandardsTests(unittest.TestCase):
    def setUp(self):
        self.practices = resources.load_json("roles.json")["skills"]

    def test_a_practice_cites_every_standard_it_lists_but_the_ones_named_as_uncited(self):
        self.assertEqual(findings(self.practices, UNCITED, own_text), [])

    def test_the_uncited_table_only_shrinks(self):
        self.assertEqual(list(UNCITED), sorted(UNCITED))
        self.assertEqual(count(UNCITED), UNCITED_COUNT, "an id left UNCITED: lower UNCITED_COUNT to match. An id joined it: cite the standard instead")

    def test_the_check_tells_a_cited_id_from_an_uncited_one(self):
        text = "A count ends in `_count`. [aip-141]\nOne owner. [relational-normal-forms, aip-180]"
        cases = {
            "nothing listed": ([], []),
            "one, cited": (["aip-141"], []),
            "one, never cited": (["aip-216"], ["aip-216"]),
            "many, one missing": (["aip-141", "aip-180", "scxml"], ["scxml"]),
            "an id that is only the start of a cited one": (["aip-14"], ["aip-14"]),
            "an id that is only the end of a cited one": (["normal-forms"], ["normal-forms"]),
        }
        for name, (listed, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(uncited(listed, text), want)

    def test_each_way_the_list_the_text_and_the_table_can_disagree_is_found(self):
        """Seeded skills: `text` cites `a` only. Each row is the skill's list, its exempt ids, and how many findings it must give."""
        text = {"one": "A rule. [a]", "two": "No citation here."}
        cases = {
            "nothing listed, nothing exempt": ({"one": []}, {}, 0),
            "every listed id cited": ({"one": ["a"]}, {}, 0),
            "an uncited id that is exempt": ({"two": ["b"]}, {"two": frozenset({"b"})}, 0),
            "a new uncited id beside an exempt one": ({"two": ["b", "c"]}, {"two": frozenset({"b"})}, 1),
            "a new uncited id on a skill with no exemption": ({"one": ["a", "c"]}, {}, 1),
            "an added exemption for an id the text cites": ({"one": ["a"]}, {"one": frozenset({"a"})}, 1),
            "an added exemption for an id the skill does not list": ({"two": ["b"]}, {"two": frozenset({"b", "z"})}, 1),
            "an exemption for a skill that does not exist": ({"one": ["a"]}, {"gone": frozenset({"z"})}, 1),
        }
        for name, (listed, exempt, want) in cases.items():
            with self.subTest(name):
                practices = {skill: {"standards": refs} for skill, refs in listed.items()}
                self.assertEqual(len(findings(practices, exempt, text.__getitem__)), want)

    def test_on_the_real_files_a_new_uncited_standard_and_an_added_exemption_both_fail(self):
        """The controls on the real files. A standard added to a skill with no citation is found, whether or not the skill has
        exempt ids. An exemption added for it passes that check and fails the count, so nothing joins the table quietly."""
        for name in ("data-model-design", "naming"):
            with self.subTest(name):
                grown = {**self.practices, name: {"standards": [*ids(self.practices[name]), "scientific-debugging"]}}
                found = findings(grown, UNCITED, own_text)
                self.assertEqual(len(found), 1, found)
                self.assertIn("scientific-debugging", found[0])
                widened = {**UNCITED, name: UNCITED.get(name, frozenset()) | {"scientific-debugging"}}
                self.assertEqual(findings(grown, widened, own_text), [])
                self.assertEqual(count(widened), UNCITED_COUNT + 1)
        cited = {**UNCITED, "naming": UNCITED["naming"] | {"aip-216"}}
        self.assertEqual(len(findings(self.practices, cited, own_text)), 1)


if __name__ == "__main__":
    unittest.main()
