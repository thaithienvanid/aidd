"""The size limits the agent-facing text keeps (AGENTS.md, Rules: a feature pays for what every session loads). A limit tracks a
cost, and the cost is what a session holds: a harness's own limit is in `config.SIZES` (tests/test_harness_sizes.py), text every
session or role loads has a budget here, and text a step loads on a signal has one limit for its class.

Nothing here is a snapshot of a file's size. Each cap in CAPS says what it bounds, who loads the text, and its cost in bytes,
estimated tokens, and share of a 200,000-token window, and tests/test_budget_headroom.py fails a cap whose cost disagrees with
its number. A cap rises only with its cost written beside it, measured, in a change of its own. A file near its limit is
restructured by topic, and never reworded to fit."""

import math
from typing import NamedTuple

# A budget holds with HEADROOM over its cap, so a fix a few bytes over never stops a change.
HEADROOM = 1.03

# The headroom line: after a change, text that is always loaded sits at or under this
# share of its cap, so the next honest edit has room and nobody trims a rule to fit. tests/test_budget_headroom.py holds it, and
# ABOVE_THE_LINE, at the end of this file, lists the files above it, each with the real limit it is near.
LINE = 0.90

# The smallest context window a documented model has (code.claude.com/docs/en/memory, "200K context window"). A larger window
# only adds room, so every share below is the worst case. Tokens are estimated at four bytes a token (token_caps.estimate_tokens).
WINDOW_TOKENS = 200_000


def tokens(size: float) -> int:
    """Estimated tokens in `size` bytes: four a token, rounded up."""
    return math.ceil(size / 4)


class Cap(NamedTuple):
    number: int  # bytes
    bounds: str  # what it bounds
    loaded: str  # who loads the text, and when
    cost: str  # the cost it tracks, with the arithmetic: bytes, estimated tokens, and the share of the window


# The caps that several tests and the headroom test read, one row each. A row states its cost, and the test holds the row's
# tokens and share to its number, so a number raised without its cost fails. A measured size is never a reason itself.
SKILL_BYTES = 18 * 1024
LOOP_BYTES = 12 * 1024
ROLE_FILE_BYTES = 16 * 1024
ROLE_START_BYTES = 56_000
REFERENCE_BYTES = 20_000
TEMPLATE_BYTES = 24 * 1024

CAPS: dict[str, Cap] = {
    "skill": Cap(
        SKILL_BYTES,
        "the aidd skill's SKILL.md",
        "every session that reads the skill, and every role that preloads it",
        "18,432 bytes is 4,608 estimated tokens, 2.3% of a 200,000-token window, and 92% of the 5,000-token body the Agent Skills "
        "specification advises (agentskills.io/specification). It holds the hard rules once, so a role pays it on every turn it reads. "
        "It also holds the handoff note's required keys and the rule for two texts that disagree, so an agent that stops needs no second file",
    ),
    "loop": Cap(
        LOOP_BYTES,
        "references/loop.md",
        "every session that reads the skill: the skill says to read it always",
        "12,288 bytes is 3,072 estimated tokens, 1.5% of a 200,000-token window. With SKILL.md the pair is 7,680 tokens, 3.8% of the "
        "window, and under 60% of a role's 14,000-token start total",
    ),
    "role file": Cap(
        ROLE_FILE_BYTES,
        "one role's agent file",
        "the role, at the start of every run: the generated hard rules and loop contract take 3.4 to 8.2 KB of it",
        "16,384 bytes is 4,096 estimated tokens, 2.0% of a 200,000-token window. The only vendor figure for an agent file is 30,000 "
        "characters (GitHub Copilot, config.SIZES). Every role with tools carries the loop contract in its file: the rule that sizes each "
        "check to the change and names what never scales down, the status line, the review request in `open_decisions`, and the rule "
        "that a fix is read once",
    ),
    "role start": Cap(
        ROLE_START_BYTES,
        "what one role starts with: its file's body, every skill it preloads, and loop.md where it preloads the aidd skill",
        "the role, at the start of every run, in a Claude Code subagent that starts with no other history",
        "56,000 bytes is 14,000 estimated tokens, 7.0% of a 200,000-token window and 1.4% of a 1,000,000-token one. It replaces a "
        "mean over roles, which let one heavy role grow while the others shrank. The heaviest role, the product designer, preloads "
        "three skills, and each role that preloads the aidd skill loads loop.md with it",
    ),
    # The two classes below are not budgets: no harness limits a file that loads on a signal ("no practical limit on bundled
    # content", platform.claude.com/docs/en/agents-and-tools/agent-skills/overview). Each is one limit for the class, a readability
    # bound that tracks one load, so the headroom line does not apply and no file is capped at its own size. A file near the limit is
    # restructured by topic, as spec.md was on 2026-11-10: a short main file, with each detail in a file its step loads.
    "reference": Cap(
        REFERENCE_BYTES,
        "each reference of the aidd skill",
        "once, in the session that reaches the step its row in SKILL.md's load table names",
        "20,000 bytes is 5,000 estimated tokens, 2.5% of a 200,000-token window, and the 5,000 tokens the Agent Skills specification "
        "advises for a skill's instructions (agentskills.io/specification)",
    ),
    "template": Cap(
        TEMPLATE_BYTES,
        "each Markdown template of the aidd skill, the document `aidd new` writes",
        "once, in the session that writes that document with `aidd new`",
        "24,576 bytes is 6,144 estimated tokens, 3.1% of a 200,000-token window. A template's length follows the standard it applies, "
        "and the agent reads the document `aidd new` wrote, once",
    ),
}


def cost_of(name: str) -> str:
    """The cap's cost line, for a failure message."""
    cap = CAPS[name]
    return f"{cap.bounds}: {cap.cost}"


# What a size failure says to do next. The limit is a cost or a readability bound, never a number to fit: restructure by
# topic, or raise the limit with its cost written beside it, and never reword to fit.
MAKE_ROOM = (
    "Restructure by topic: a short main file, with each detail in a reference that the step needing it loads. Or raise the "
    "limit, with the cost it tracks written beside it in tests/budgets.py, in a change of its own. Never reword, shorten, merge, or "
    "drop a rule, a stop, a case, or a fact to fit a number. Remove repetition only where the same reader always loads the other text"
)


def within(size: float, cap: float) -> bool:
    """Whether `size` keeps to `cap`, with HEADROOM."""
    return size <= cap * HEADROOM


def past_a_harness_limit(name: str, size: float, limit) -> str:
    """The failure message of a limit a coding agent imposes (a `config.SIZES` row): empty while `size` keeps to it. The limit is
    the vendor's, so the next step is to say less, never to raise a cap here."""
    if size <= limit.number:
        return ""
    return (
        f"{name} is {size:,.0f} {limit.unit}, past {limit.harness}'s documented {limit.number:,} for {limit.what} "
        f"({limit.source}, read {limit.read}). The coding agent sets this limit, so no cap of ours raises it: say less"
    )


def make_room(name: str, size: float, cap: float, unit: str = "bytes", cost: str = "") -> str:
    """The failure message of a budget: which file, how far past its cap, what the cap costs, and the ways to make room."""
    past = size - cap
    where = f"{past:,.0f} {unit} past its cap of {cap:,.0f}" if past > 0 else f"within its cap of {cap:,.0f} {unit} but above the {LINE:.0%} line"
    return f"{name} is {size:,.0f} {unit}, {where} ({size / cap:.1%}). {cost + '. ' if cost else ''}{MAKE_ROOM}"


def near_class_limit(references, templates) -> list[str]:
    """A note for each reference in the folder `references` and each template in `templates` that is above LINE of its class
    limit, such as `spec.md (92% of 20,000 bytes)`: the file passes, and it is the signal to restructure it by topic before the
    next addition. A class limit is a readability bound, so no other file is named and the note stays quiet while every file is
    well under it."""
    notes = []
    for folder, cap, skip in ((references, REFERENCE_BYTES, "loop.md"), (templates, TEMPLATE_BYTES, "")):
        for path in sorted(folder.glob("*.md")):
            if path.name != skip and (size := len(path.read_bytes())) > cap * LINE:
                notes.append(f"{path.name} ({size / cap:.0%} of {cap:,} bytes)")
    return notes


# The unit of readable length is a section, not a file: a reader holds one section at a time. Under an H2 heading the median section
# of the references, templates, packs, and practice skills is 125 estimated tokens and the 90th percentile 439, so a section past
# SECTION_TOKENS is named in the test report as one to split by topic. It is a report: no harness limits it, and a long table that
# aidd generates may be the honest answer.
SECTION_TOKENS = 1_200


def long_sections(files, root) -> list[str]:
    """A note for each section under an H2 heading, in `files`, that is past SECTION_TOKENS, such as
    `references/spec.md ## Spec (3,486 tokens)`. Fenced code does not start a section. Only a section past the line is named."""
    notes = []
    for path in files:
        heading, size, fence = "", 0, False
        for line in [*path.read_text(encoding="utf-8").splitlines(), "## "]:
            if line.strip().startswith(("```", "~~~")):
                fence = not fence
            if not fence and line.startswith("## "):
                if heading and (tokens_in := math.ceil(size / 4)) > SECTION_TOKENS:
                    notes.append(f"{path.relative_to(root)} ## {heading} ({tokens_in:,} tokens)")
                heading, size = line[3:].strip(), 0
            else:
                size += len(line) + 1
    return notes


def signal_files(root) -> list:
    """The Markdown files that load on a signal: the aidd skill's references and templates, and each team skill's SKILL.md and
    references, but not the aidd-team router, whose roles reference is one generated table of every role."""
    skill, team = root / ".agents" / "skills" / "aidd", root / "plugins" / "aidd-team" / "skills"
    files = [*sorted((skill / "references").glob("*.md")), *sorted((skill / "assets").glob("*.md"))]
    for folder in sorted(p for p in team.iterdir() if p.is_dir() and p.name != "aidd-team"):
        files += [*sorted(folder.glob("SKILL.md")), *sorted((folder / "references").glob("*.md"))]
    return files


# The work-items page's script (src/aidd/views/work_item_page.js), in KiB (R377): it only shows and hides views, folds search
# text, moves focus, copies, and keeps the state in the URL, so it stays small enough to read in one sitting.
WORK_PAGE_SCRIPT_KIB = 8

# The design system of aidd's built-in pages (R392): the tokens' CSS and the shared components, comments stripped, as
# `system_css()` writes them, in KiB.
SYSTEM_CSS_KIB = 23

# The work-items page's own CSS (src/aidd/views/work_item_page.css), in KiB, after it moved onto the system (R392): it
# only lays out the Board, its team rows, the Tree, the item page, and Search.
WORK_PAGE_CSS_KIB = 21

# The exploration page's own CSS (src/aidd/views/exploration_page.css), in KiB, after it moved onto the system: it only
# lays out the contents, the directions, the rounds' pairs, and the Markdown.
EXPLORE_PAGE_CSS_KIB = 2

# The prototype viewer's own chrome CSS (the `<style id="viewer">` block of plugins/aidd-team/tools/prototype/viewer.html),
# in KiB, after it moved onto the system: it lays out the review column, the preview, the Board, System, and the
# comments, and holds the drawn device. The cap is a target to shrink, starting with rules that repeat a shared component's.
# It also holds the Board's state rings, each drawn from the thumbnail it marks: its edge, its halo, a second ring for keyboard
# focus, and a glow for the current cell.
VIEWER_CHROME_CSS_KIB = 53.5


class Near(NamedTuple):
    limit: str  # the real limit it is near, and whose it is
    relief: str  # what would relieve it


# The files above the headroom line (LINE) today, each with the real limit it is near and what would relieve it. The line applies to
# text that is always loaded and to code; a file that loads on a signal has one limit for its class (REFERENCE_BYTES,
# TEMPLATE_BYTES, token_caps), and a file near that limit is a signal to restructure it by topic.
# tests/test_budget_headroom.py holds two things: a budget above the line is listed here, and a listed budget that came under
# the line leaves the list, so this list only shrinks. A new budget starts under the line. Never add a file to get a change
# past the test: make room (MAKE_ROOM), and remove an entry in the change that brings its file under the line.
_MODULE = Near(
    "the 700-line ceiling of code shape (LONG_MODULE in tests/test_code_shape.py), which is aidd's own bound on how much one module asks a reader to hold",
    "split the module along a seam it already has, as a refactor of its own, green before and after (CONTRIBUTING.md, Code and imports)",
)
ABOVE_THE_LINE: dict[str, Near] = {
    **{
        f"module: {name}": _MODULE
        for name in (
            "aidd/cli/grammar.py aidd/config/loading.py aidd/kernel/git.py aidd/kernel/strict_yaml.py aidd/risk/commands.py "
            "aidd/risk/harness_rules.py aidd/setup/adoption.py aidd/setup/detection.py aidd/testing/runner.py aidd/views/work_views.py"
        ).split()
    },
    "instructions: AGENTS.md": Near(
        "doctor's 12 KiB bound for an instruction file (doctor_checks.INSTRUCTION_MAX_BYTES, aidd's own). It tracks Claude Code's advice of 200 lines, "
        "which the file keeps well under, and stays under Antigravity's cut of one rule file at 24,000 bytes and Codex's 32 KiB for the whole chain "
        "(config.SIZES). 12 KiB is about 3,072 estimated tokens, 1.5% of a 200,000-token window, in every session and in every subagent of this repository",
        "move a rule that only some changes need into CONTRIBUTING.md or a skill this file links, or raise the doctor bound with that cost written beside it",
    ),
    "instructions: the block aidd writes into AGENTS.md": Near(
        "the BLOCK_CAP of tests/engagement.py (aidd's own). The block loads in every session of every harness that reads AGENTS.md, so each byte is a "
        "quarter of a token for every adopter; a harness's own cut of the file is far above it (config.SIZES)",
        "none is needed while the block holds the first command and where the skill is; a longer block raises the cap with that cost written beside it",
    ),
    "description: skill aidd": Near(
        "the DESCRIPTION_CHARS cap of 250 (aidd's own). The real limits are the 1,024 characters the Agent Skills specification allows and the "
        "listing budget Claude Code applies to all descriptions together (config.SIZES)",
        "say less: the description names only when to load the skill, and its body says the rest",
    ),
}
