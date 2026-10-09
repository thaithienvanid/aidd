"""A ratchet on sentence length, so a newcomer reads each sentence once.

The rule: over the prose, without front matter, code blocks, tables, headings, HTML, and inline code, no sentence is
over 35 words, and at least 90% are 25 words or fewer. Every page in LOCKED must meet it, and so must each table column
in LOCKED_COLUMNS, one paragraph a cell. The other ASD-STE100 (Simplified Technical English) sentence rules, such as
one instruction per sentence and the active voice, are applied by review.

The ratchet only tightens. To lock a page:

1. Run `STE_REPORT=1 python3 -m unittest discover -s tests -p test_plain_language.py -k report`. It prints every
   other Markdown page. Without STE_REPORT=1 the test only checks that the report runs, and prints nothing. (The
   name has no AIDD_ prefix: the test helpers remove AIDD_ variables to keep the suite hermetic.)
2. Pick a page the report marks `meets`, or rewrite one until it does.
3. Add its path, relative to the repository root, to LOCKED, in the same change.

Never remove a page from LOCKED to make a change pass: shorten the sentence instead.

One exemption: QUOTED holds fixed external wording, such as the BCP 14 (RFC 8174) boilerplate, which is never
paraphrased. The measure skips a sentence only when it matches a QUOTED entry exactly.
"""

import os
import re
import unittest

from helpers import ROOT, repo_files

# The pages that must meet the rule. Add a page once it does; never take one out.
# The templates' own prose (their guidance comments are not measured); postmortem.md and spec.md hold none outside
# comments, so the measure finds nothing to lock.
LOCKED = (
    "README.md",
    "docs/INSTALL.md",
    "docs/QUICKSTART.md",
    "docs/RATIONALE.md",
    "docs/CONFIG.md",
    "docs/PLATFORMS.md",
    "docs/HOW-TO.md",
    "llms.txt",
    "llms-install.md",
    "CHANGELOG.md",
    "plugins/aidd-team/commands/autopilot.md",
    "plugins/aidd-team/commands/explore.md",
    "plugins/aidd-team/commands/fix.md",
    "plugins/aidd-team/commands/implement.md",
    "plugins/aidd-team/commands/mvp.md",
    "plugins/aidd-team/commands/onboard.md",
    "plugins/aidd-team/commands/postmortem.md",
    "plugins/aidd-team/commands/propose.md",
    "plugins/aidd-team/commands/refine.md",
    "plugins/aidd-team/commands/review.md",
    "plugins/aidd-team/commands/ship.md",
    "plugins/aidd-team/commands/specify.md",
    "plugins/aidd-team/commands/sweep.md",
    "plugins/aidd-team/commands/verify.md",
    ".agents/skills/aidd/assets/acceptance.md",
    ".agents/skills/aidd/assets/adr.md",
    ".agents/skills/aidd/assets/api.md",
    ".agents/skills/aidd/assets/architecture.md",
    ".agents/skills/aidd/assets/authz-matrix.md",
    ".agents/skills/aidd/assets/change-order.md",
    ".agents/skills/aidd/assets/change-request.md",
    ".agents/skills/aidd/assets/compliance.md",
    ".agents/skills/aidd/assets/contract.md",
    ".agents/skills/aidd/assets/data-map.md",
    ".agents/skills/aidd/assets/design-spec.md",
    ".agents/skills/aidd/assets/DESIGN.md",
    ".agents/skills/aidd/assets/epic.md",
    ".agents/skills/aidd/assets/exploration.md",
    ".agents/skills/aidd/assets/glossary.md",
    ".agents/skills/aidd/assets/feedback.md",
    ".agents/skills/aidd/assets/initiative.md",
    ".agents/skills/aidd/assets/migration-plan.md",
    ".agents/skills/aidd/assets/module-readme.md",
    ".agents/skills/aidd/assets/proposal.md",
    ".agents/skills/aidd/assets/release-notes.md",
    ".agents/skills/aidd/assets/runbook.md",
    ".agents/skills/aidd/assets/slo.md",
    ".agents/skills/aidd/assets/spec-short.md",
    ".agents/skills/aidd/assets/tech-spec.md",
    ".agents/skills/aidd/assets/test-plan.md",
    ".agents/skills/aidd/assets/threat-model.md",
    ".agents/skills/aidd/assets/tracking-plan.md",
    ".agents/skills/aidd/assets/vendors.md",
    "docs/GLOSSARY.md",
    "docs/FAQ.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "templates/AGENTS.snippet.md",
    "docs/rfcs/0000-template.md",
    "docs/ADOPTION.md",
    "docs/CLI.md",
    "docs/STANDARDS.md",
    "plugins/aidd-team/agents/architect.md",
    "plugins/aidd-team/agents/data-engineer.md",
    "plugins/aidd-team/agents/delivery-manager.md",
    "plugins/aidd-team/agents/ml-engineer.md",
    "plugins/aidd-team/agents/platform-engineer.md",
    "plugins/aidd-team/agents/product-designer.md",
    "plugins/aidd-team/agents/reviewer.md",
    "plugins/aidd-team/agents/tech-writer.md",
    "plugins/aidd-team/commands/plan.md",
    "plugins/aidd-team/skills/ai-evals/references/statistics.md",
    "plugins/aidd-team/skills/aidd-team/references/domain-packs.md",
    "plugins/aidd-team/skills/aidd-team/references/extensions.md",
    "plugins/aidd-team/skills/aidd-team/references/flows.md",
    "plugins/aidd-team/skills/aidd-team/references/practice-skills.md",
    "plugins/aidd-team/skills/api-design/references/graphql-grpc-webhooks.md",
    "plugins/aidd-team/skills/client-delivery/references/client-documents.md",
    "plugins/aidd-team/skills/client-delivery/references/verify-what-exists.md",
    "plugins/aidd-team/skills/cloud-and-infrastructure/references/cost-and-performance.md",
    "plugins/aidd-team/skills/debugging/references/hypotheses.md",
    "plugins/aidd-team/skills/dependency-upgrade/references/codemods.md",
    "plugins/aidd-team/skills/dependency-upgrade/references/sizing.md",
    "plugins/aidd-team/skills/desktop-apps/references/distribution.md",
    "plugins/aidd-team/skills/enterprise-controls/references/controls.md",
    "plugins/aidd-team/skills/enterprise-controls/references/readiness.md",
    "plugins/aidd-team/skills/estimation/references/speed-band.md",
    "plugins/aidd-team/skills/extensions-and-marketplace-apps/references/hosts.md",
    "plugins/aidd-team/skills/incident-response/references/breach-clocks.md",
    "plugins/aidd-team/skills/incident-response/references/updates.md",
    "plugins/aidd-team/skills/mobile-apps/references/store-review.md",
    "plugins/aidd-team/skills/observability/references/redaction.md",
    "plugins/aidd-team/skills/observability/references/telemetry-cost.md",
    "plugins/aidd-team/skills/package-publishing/references/registries.md",
    "plugins/aidd-team/skills/performance/references/database.md",
    "plugins/aidd-team/skills/plain-language/SKILL.md",
    "plugins/aidd-team/skills/privacy-by-default/references/rights-and-records.md",
    "plugins/aidd-team/skills/product-defaults/references/services.md",
    "plugins/aidd-team/skills/product-defaults/references/web.md",
    "plugins/aidd-team/skills/product-discovery/references/job-stories-and-ears.md",
    "plugins/aidd-team/skills/product-discovery/references/spikes.md",
    "plugins/aidd-team/skills/prototyping/references/design-review.md",
    "plugins/aidd-team/skills/prototyping/references/design-system-contract.md",
    "plugins/aidd-team/skills/prototyping/references/prototype-screenshots.md",
    "plugins/aidd-team/skills/release-rollout/references/flags-and-experiments.md",
    "plugins/aidd-team/skills/modular-monolith/references/boundaries.md",
    "plugins/aidd-team/skills/modular-monolith/references/events-and-data.md",
    "plugins/aidd-team/skills/modular-monolith/references/migrate-and-extract.md",
    "plugins/aidd-team/skills/resilience/references/recovery.md",
    "plugins/aidd-team/skills/secure-coding/references/authentication.md",
    "plugins/aidd-team/skills/secure-coding/references/configuration.md",
    "plugins/aidd-team/skills/secure-coding/references/least-privilege.md",
    "plugins/aidd-team/skills/test-design/references/real-dependencies.md",
    "plugins/aidd-team/skills/test-design/references/test-value.md",
    "docs/TEAM-REFERENCE.md",
    "plugins/aidd-team/agents/agile-coach.md",
    "plugins/aidd-team/agents/compliance-analyst.md",
    "plugins/aidd-team/agents/developer.md",
    "plugins/aidd-team/agents/product-manager.md",
    "plugins/aidd-team/agents/security-engineer.md",
    "plugins/aidd-team/agents/sre.md",
    "plugins/aidd-team/agents/tester.md",
    "plugins/aidd-team/agents/verifier.md",
    "plugins/aidd-team/commands/handover.md",
    "plugins/aidd-team/commands/retro.md",
    "plugins/aidd-team/commands/secure.md",
    "plugins/aidd-team/skills/aidd-team/references/roles.md",
    "plugins/aidd-team/skills/ai-agents-and-tools/SKILL.md",
    "plugins/aidd-team/skills/ai-features/SKILL.md",
    "plugins/aidd-team/skills/apis-and-services/SKILL.md",
    "plugins/aidd-team/skills/cloud-and-infrastructure/SKILL.md",
    "plugins/aidd-team/skills/data-and-analytics/SKILL.md",
    "plugins/aidd-team/skills/desktop-apps/SKILL.md",
    "plugins/aidd-team/skills/embedded-automotive-industrial/SKILL.md",
    "plugins/aidd-team/skills/enterprise-controls/SKILL.md",
    "plugins/aidd-team/skills/extensions-and-marketplace-apps/SKILL.md",
    "plugins/aidd-team/skills/health/SKILL.md",
    "plugins/aidd-team/skills/internationalization/SKILL.md",
    "plugins/aidd-team/skills/mobile-apps/SKILL.md",
    "plugins/aidd-team/skills/multi-tenant-saas/SKILL.md",
    "plugins/aidd-team/skills/package-publishing/SKILL.md",
    "plugins/aidd-team/skills/payments-and-finance/SKILL.md",
    "plugins/aidd-team/skills/privacy-by-default/SKILL.md",
    "plugins/aidd-team/skills/products-for-children/SKILL.md",
    "plugins/aidd-team/skills/public-sector/SKILL.md",
    "plugins/aidd-team/skills/web-front-end/SKILL.md",
    "plugins/aidd-team/skills/diagrams/SKILL.md",
    "plugins/aidd-team/skills/secure-coding/SKILL.md",
    "plugins/aidd-team/skills/test-design/SKILL.md",
    "plugins/aidd-team/skills/threat-model/SKILL.md",
    "plugins/aidd-team/skills/accessible-ui/SKILL.md",
    "plugins/aidd-team/skills/ai-evals/SKILL.md",
    "plugins/aidd-team/skills/api-design/SKILL.md",
    "plugins/aidd-team/skills/ci-pipeline/SKILL.md",
    "plugins/aidd-team/skills/client-delivery/SKILL.md",
    "plugins/aidd-team/skills/code-review/SKILL.md",
    "plugins/aidd-team/skills/debugging/SKILL.md",
    "plugins/aidd-team/skills/decision-record/SKILL.md",
    "plugins/aidd-team/skills/dependency-upgrade/SKILL.md",
    "plugins/aidd-team/skills/estimation/SKILL.md",
    "plugins/aidd-team/skills/incident-response/SKILL.md",
    "plugins/aidd-team/skills/modular-monolith/SKILL.md",
    "plugins/aidd-team/skills/observability/SKILL.md",
    "plugins/aidd-team/skills/performance/SKILL.md",
    "plugins/aidd-team/skills/product-defaults/SKILL.md",
    "plugins/aidd-team/skills/product-discovery/SKILL.md",
    "plugins/aidd-team/skills/proposal/SKILL.md",
    "plugins/aidd-team/skills/prototyping/SKILL.md",
    "plugins/aidd-team/skills/release-rollout/SKILL.md",
    "plugins/aidd-team/skills/resilience/SKILL.md",
    "plugins/aidd-team/skills/schema-migration/SKILL.md",
    "plugins/aidd-team/skills/support-desk/SKILL.md",
    "plugins/aidd-team/skills/technical-writing/SKILL.md",
    ".agents/skills/aidd/SKILL.md",
    ".agents/skills/aidd/references/config.md",
    ".agents/skills/aidd/references/containers.md",
    ".agents/skills/aidd/references/emergency.md",
    ".agents/skills/aidd/references/example.md",
    ".agents/skills/aidd/references/gate.md",
    ".agents/skills/aidd/references/handoff.md",
    ".agents/skills/aidd/references/loop.md",
    ".agents/skills/aidd/references/observe-learn.md",
    ".agents/skills/aidd/references/profiles.md",
    ".agents/skills/aidd/references/routes.md",
    ".agents/skills/aidd/references/scale.md",
    ".agents/skills/aidd/references/security.md",
    ".agents/skills/aidd/references/spec.md",
    ".agents/skills/aidd/references/state.md",
    "docs/METHOD.md",
    "docs/TEAM.md",
    "plugins/aidd-team/README.md",
    "plugins/README.md",
    "SECURITY.md",
    "RELEASING.md",
    "GOVERNANCE.md",
    "REVIEW.md",
    "docs/CONTROLS.md",
    "docs/ENTERPRISE.md",
    "docs/ORCA.md",
    "docs/TROUBLESHOOTING.md",
    "specs/README.md",
    "templates/REVIEW.md",
    "templates/specs-README.md",
    "templates/evals/README.md",
    "AGENTS.md",
    "plugins/aidd-team/skills/aidd-team/SKILL.md",
)
# Tables the rule also measures, one column each: (page, column index). The prose measure skips tables, so a page
# whose content is a table, such as the glossary, needs its column named here. Never take one out.
LOCKED_COLUMNS = (("docs/GLOSSARY.md", 1),)
# Fixed external wording, never paraphrased: each entry is one sentence as `sentences()` yields it (links as their text).
# The measure skips a sentence only on an exact match, so a changed copy is measured like any other sentence.
QUOTED = (
    'The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", '
    '"NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in BCP 14 (RFC 2119, '
    "RFC 8174) when, and only when, they appear in all capitals, as shown here.",
)
# Not ours to rewrite: other tools' sample files that the import tests read.
UNREPORTED = ("tests/fixtures/",)
MAX_WORDS = 35
SHORT_WORDS = 25
SHORT_SHARE = 0.9

# Front matter: a `---` (YAML) or `+++` (TOML) block at the very top, skipped only when a line in it is a key (`key:` or
# `key =`), so a page that opens with a horizontal rule is still measured.
FRONT_MATTER = re.compile(r"\A(---|\+\+\+)[ \t]*\n(.*?\n)?\1[ \t]*(?:\n|\Z)", re.S)
FRONT_MATTER_KEY = re.compile(r"^[A-Za-z_][\w.-]*(?::(?:[ \t]|$)|[ \t]*=)", re.M)
LIST_ITEM = re.compile(r"^(?:[-*]|\d+\.)\s+")
WORD = re.compile(r"[A-Za-z0-9][\w'’.+/-]*")
# A code fence: three or more backticks, closed by the same run, so a longer fence can show a shorter one inside it.
FENCE = re.compile(r"(`{3,}).*?\1", re.S)
TABLE_RULE = re.compile(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?")
# A sentence ends at `.`, `!`, or `?`, with any closing quote or bracket after it, before a space; never after e.g. or i.e.
SENTENCE_END = re.compile(r"""(?<!\be\.g\.)(?<!\bi\.e\.)(?<=[.!?])\s+|(?<=[.!?]["”’')\]])\s+""")


def without_code(text: str) -> str:
    """The page without its code blocks and HTML comments."""
    text = FENCE.sub("\n\n", text)
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def table_cells(text: str, column: int) -> list[str]:
    """One column of every table on a page, without the header rows and the rule rows (`| --- |`). A cell ends at
    each `|` that no backslash escapes, as in GitHub's tables."""
    lines = [ln.strip() for ln in without_code(text).splitlines()]
    cells = []
    for i, s in enumerate(lines):
        if not s.startswith("|") or TABLE_RULE.fullmatch(s) or (i + 1 < len(lines) and TABLE_RULE.fullmatch(lines[i + 1])):
            continue
        row = [c.strip() for c in re.split(r"(?<!\\)\|", s.strip("|"))]
        if column < len(row) and row[column]:
            cells.append(row[column])
    return cells


def column_prose(text: str, column: int) -> str:
    """One column of a page's tables as prose, one paragraph a cell, for the same measure as a page."""
    return "\n\n".join(table_cells(text, column))


def prose_units(text: str) -> list[str]:
    """The prose of a Markdown page as paragraphs and list items, without its YAML or TOML front matter (metadata, not
    prose: its keys and values would join into one sentence), code blocks, comments, tables, headings, and HTML lines. A
    blockquote counts as prose, without its marker and its alert label (`[!IMPORTANT]`)."""
    front = FRONT_MATTER.match(text)
    if front and FRONT_MATTER_KEY.search(front.group(2) or ""):
        text = text[front.end() :]
    text = without_code(text)
    units: list[str] = []
    para: list[str] = []
    quoted = False

    def close() -> None:
        if para:
            units.append(" ".join(para))
            para.clear()

    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "|", "<")):
            close()
            continue
        if s.startswith(">") != quoted:
            close()
            quoted = not quoted
        s = re.sub(r"^>\s*(?:\[![A-Z]+\]\s*)?", "", s)
        if LIST_ITEM.match(s):
            close()
            s = LIST_ITEM.sub("", s)
        if s:
            para.append(s)
    close()
    return units


def sentences(text: str) -> list[tuple[int, str]]:
    """Every prose sentence with its word count. Inline code, HTML tags, and bold or italic marks are removed, a link
    keeps its text, and a sentence ends as SENTENCE_END says."""
    out = []
    for unit in prose_units(text):
        unit = re.sub(r"`[^`]*`", " ", unit)
        unit = re.sub(r"\*+", "", unit)
        unit = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", unit)
        unit = re.sub(r"<[^>]+>", " ", unit)
        for sentence in SENTENCE_END.split(unit):
            words = WORD.findall(sentence)
            if words:
                out.append((len(words), sentence.strip()))
    return out


class MeasureTests(unittest.TestCase):
    def test_it_skips_code_tables_headings_and_inline_code(self):
        text = (
            "# A heading with many many words in it\n\n"
            "Run `aidd init --profile solo --approvers email:you@example.com` first. Then check it.\n\n"
            "| a | b |\n| --- | --- |\n| one two three | four |\n\n"
            "```sh\naidd doctor and many more words here\n```\n\n"
            "- A list item, [with a link](docs/X.md#anchor).\n"
            "> [!IMPORTANT]\n> **Pre-release.** Two words.\n"
        )
        self.assertEqual(
            sentences(text),
            [(2, "Run   first."), (3, "Then check it."), (6, "A list item, with a link."), (1, "Pre-release."), (2, "Two words.")],
        )

    def test_it_skips_a_leading_front_matter(self):
        """Front matter is data (TOML between +++ lines, YAML between --- lines), never prose; a later --- is a rule."""
        for fence in ("+++", "---"):
            with self.subTest(fence=fence):
                text = f'{fence}\nkind = "spec"\ntitle = "a title with a great many words in it"\n{fence}\n\nRun the tests first.\n'
                self.assertEqual(sentences(text), [(4, "Run the tests first.")])
        self.assertEqual(sentences("Run it.\n\n---\n\nThen check it.\n"), [(2, "Run it."), (3, "Then check it.")])

    def test_a_longer_fence_hides_a_shorter_one_inside_it(self):
        text = "Before the block.\n\n````markdown\nA sample:\n\n```sh\naidd doctor\n```\n\nNot prose at all here.\n````\n\nAfter the block.\n"
        self.assertEqual(sentences(text), [(3, "Before the block."), (3, "After the block.")])

    def test_a_table_column_is_measured_cell_by_cell(self):
        text = (
            "Some prose.\n\n| Term | Meaning |\n| --- | :--- |\n| Gate | The program that decides. It posts a status. |\n"
            "| Run | One `a \\| b` pass. |\n\n```\n| Code | Not a row. |\n```\n"
        )
        self.assertEqual(table_cells(text, 1), ["The program that decides. It posts a status.", "One `a \\| b` pass."])
        self.assertEqual([n for n, _ in sentences(column_prose(text, 1))], [4, 4, 2])

    def test_a_sentence_ends_before_a_closing_quote_or_bracket(self):
        cases = {
            '."': 'Type "yes." Then wait.',
            ".)": "Run it (once.) Then wait.",
            '?"': 'Ask "why?" Then wait.',
            "!)": "Stop it (now!) Then wait.",
        }
        for end, text in cases.items():
            with self.subTest(end=end):
                self.assertEqual([s for _, s in sentences(text)], [text[: text.index(end) + 2], "Then wait."])

    def test_it_skips_the_front_matter_only_at_the_top(self):
        text = '---\ndescription: "A long description, with many words that would join the keys"\nname: x\n---\n\nRun it.\n\n---\n\nThen wait.\n'
        self.assertEqual([s for _, s in sentences(text)], ["Run it.", "Then wait."])

    def test_it_skips_toml_front_matter_too(self):
        text = '+++\ntitle = "A long title, with many words that would join the keys"\ndraft = false\n+++\n\nRun it.\n'
        self.assertEqual([s for _, s in sentences(text)], ["Run it."])

    def test_a_page_that_opens_with_a_horizontal_rule_is_still_measured(self):
        for rule in ("---", "+++"):
            with self.subTest(rule=rule):
                text = f"{rule}\n\nRun it, then read the result.\n\n{rule}\n\nThen wait.\n"
                self.assertEqual([s for _, s in sentences(text)], ["Run it, then read the result.", "Then wait."])

    def test_e_g_and_i_e_end_no_sentence(self):
        text = "Pick a tool, e.g. this one. Pick the first, i.e. the oldest one."
        self.assertEqual([n for n, _ in sentences(text)], [6, 7])


def measured(text: str) -> list[tuple[int, str]]:
    """The sentences the rule measures: every sentence but an exact QUOTED one."""
    return [(n, s) for n, s in sentences(text) if s not in QUOTED]


def page_findings(text: str) -> list[str]:
    """Why a page does not meet the rule, or [] when it does."""
    found = measured(text)
    if not found:
        return ["the measure found no prose"]
    out = []
    long = [s for n, s in found if n > MAX_WORDS]
    if long:
        out.append(f"split each sentence over {MAX_WORDS} words: {long}")
    short = sum(1 for n, _ in found if n <= SHORT_WORDS)
    if short / len(found) < SHORT_SHARE:
        out.append(f"{short} of {len(found)} sentences are {SHORT_WORDS} words or fewer; the longest: {sorted(found, reverse=True)[:5]}")
    return out


def report() -> str:
    """One line per Markdown page outside LOCKED: its sentence count, the sentences over MAX_WORDS, the share of
    sentences of SHORT_WORDS or fewer, and whether it meets the rule. Pages that meet it come first: lock them next."""
    rows = []
    for rel in sorted(f for f in repo_files() if f.endswith(".md") and f not in LOCKED and not f.startswith(UNREPORTED)):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        found = measured(text)
        over = sum(1 for n, _ in found if n > MAX_WORDS)
        share = sum(1 for n, _ in found if n <= SHORT_WORDS) / len(found) if found else 0.0
        rows.append((not page_findings(text) and found, rel, len(found), over, share))
    rows.sort(key=lambda r: (not r[0], r[1]))
    lines = [f"{'meets' if ok else '-----'}  {n:5d} sentences  {over:4d} over {MAX_WORDS}  {share:6.1%} short  {rel}" for ok, rel, n, over, share in rows]
    met = sum(1 for r in rows if r[0])
    return "\n".join([f"Plain-language report: {met} of {len(rows)} unlocked pages meet the rule.", *lines])


class RuleTests(unittest.TestCase):
    def test_a_page_meets_the_rule_or_says_why_not(self):
        short = "Run the tests first. " * 9
        self.assertEqual(page_findings(short), [])
        self.assertEqual(page_findings("```sh\nonly code\n```\n"), ["the measure found no prose"])
        (finding,) = page_findings(short + " ".join(["word"] * 36) + ".")
        self.assertTrue(finding.startswith(f"split each sentence over {MAX_WORDS} words"), finding)
        (finding,) = page_findings(short + (" ".join(["word"] * 30) + ". ") * 2)
        self.assertTrue(finding.startswith("9 of 11 sentences are 25 words or fewer"), finding)


class QuotedTests(unittest.TestCase):
    def test_the_measure_skips_only_an_exact_quoted_sentence(self):
        short = "Run the tests first. " * 9
        (quote,) = QUOTED
        self.assertEqual(page_findings(short + quote), [])
        for changed in (
            quote.replace("as shown here", "as you see here"),
            quote.replace("The key words", "Note that the key words"),
            quote[:-1] + " and nowhere else.",
        ):
            with self.subTest(changed=changed[:40]):
                (finding,) = page_findings(short + changed)
                self.assertTrue(finding.startswith(f"split each sentence over {MAX_WORDS} words"), finding)

    def test_every_quoted_sentence_is_on_a_page(self):
        """An entry no page quotes is stale: take it out, so the exemption never grows."""
        pages = [(ROOT / rel).read_text(encoding="utf-8", errors="replace") for rel in repo_files() if rel.endswith(".md")]
        for quote in QUOTED:
            with self.subTest(quote=quote[:40]):
                self.assertTrue(any(quote in [s for _, s in sentences(p)] for p in pages), quote)


class StyleTests(unittest.TestCase):
    def test_the_measure_finds_the_prose(self):
        for rel in ("README.md", "docs/INSTALL.md", "CHANGELOG.md"):
            with self.subTest(page=rel):
                self.assertGreater(len(sentences((ROOT / rel).read_text(encoding="utf-8"))), 40, "the measure found almost no prose")

    def test_every_locked_page_meets_the_rule(self):
        for rel in LOCKED:
            with self.subTest(page=rel):
                self.assertEqual(page_findings((ROOT / rel).read_text(encoding="utf-8")), [], rel)

    def test_every_locked_column_meets_the_rule(self):
        for rel, column in LOCKED_COLUMNS:
            with self.subTest(page=rel, column=column):
                prose = column_prose((ROOT / rel).read_text(encoding="utf-8"), column)
                self.assertGreater(len(sentences(prose)), 40, "the measure found almost no cells")
                self.assertEqual(page_findings(prose), [], f"{rel}, column {column}")


class ReportTests(unittest.TestCase):
    def test_report_every_other_page(self):
        """The report runs and names every other page. It prints only with STE_REPORT=1, and never fails on a page."""
        text = report()
        self.assertTrue(text.startswith("Plain-language report: "), text[:200])
        others = [f for f in repo_files() if f.endswith(".md") and f not in LOCKED and not f.startswith(UNREPORTED)]
        self.assertTrue(others)
        for rel in others:
            self.assertIn(f"  {rel}\n", text + "\n", rel)
        if os.environ.get("STE_REPORT") == "1":
            print("\n" + text)


if __name__ == "__main__":
    unittest.main()
