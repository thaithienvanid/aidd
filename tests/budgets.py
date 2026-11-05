"""The size budgets the agent-facing text keeps (AGENTS.md, Rules: a feature pays for its own bytes). A budget holds
with HEADROOM over its cap, so a fix a few bytes over never stops a change; past it, the change makes room by tightening
other words, and a cap rises only with a reason."""

HEADROOM = 1.03


def within(size: float, cap: float) -> bool:
    """Whether `size` keeps to `cap`, with HEADROOM."""
    return size <= cap * HEADROOM


# Each reference of the aidd skill loads when its signal comes, so each keeps a budget too (R323), set on 2026-11-05 at
# about its size then, rounded up to the half KiB. A new reference names its cap here.
REFERENCE_KIB = {
    "config.md": 12.5,
    "delegation.md": 3.5,
    "emergency.md": 2,
    "example.md": 7,
    "handoff.md": 4.5,
    "intents.md": 12,
    "observe-learn.md": 6,
    "profiles.md": 4.5,
    "risk.md": 8.5,
    "routes.md": 8,
    "scale.md": 7,
    "security.md": 3,
    "spec.md": 33,
    "state.md": 5,
}


def references_past_cap(folder) -> list[str]:
    """A note for each reference in `folder` that is past its cap in REFERENCE_KIB, such as `spec.md (33.2 of 33 KiB)`:
    it still passes on the headroom, and the next addition would fail. Only a reference past its cap is named, so the
    note stays quiet while every reference keeps to its cap."""
    notes = []
    for name, kib in REFERENCE_KIB.items():
        path = folder / name
        if path.is_file() and (size := len(path.read_bytes())) > kib * 1024:
            notes.append(f"{name} ({size / 1024:.1f} of {kib:g} KiB)")
    return notes


# The work-items page's script (src/aidd/views/work_item_page.js), in KiB (R377): it only shows and hides views, folds search
# text, moves focus, copies, and keeps the state in the URL, so it stays small enough to read in one sitting. It was
# 8,240 bytes after R392a, inside the headroom.
WORK_PAGE_SCRIPT_KIB = 8

# The design system of aidd's built-in pages (R392): the tokens' CSS and the shared components, comments stripped, as
# `system_css()` writes them, in KiB. It was 23,495 bytes (22.9 KiB) after R392a's confirm review, under its cap.
SYSTEM_CSS_KIB = 23

# The work-items page's own CSS (src/aidd/views/work_item_page.css), in KiB, after it moved onto the system (R392): it
# only lays out the Board, the lanes, the Tree, the item page, and Search. It was 20,791 bytes (20.3 KiB) after R392a.
WORK_PAGE_CSS_KIB = 21

# The exploration page's own CSS (src/aidd/views/exploration_page.css), in KiB, after it moved onto the system: it only
# lays out the contents, the directions, the rounds' pairs, and the Markdown. It was 2,034 bytes when it moved.
EXPLORE_PAGE_CSS_KIB = 2

# The prototype viewer's own chrome CSS (the `<style id="viewer">` block of plugins/aidd-team/tools/prototype/viewer.html),
# in KiB, after it moved onto the system (R392a): it lays out the review column, the preview, the Board, System, and the
# comments, and holds the drawn device. It was 51,123 bytes (49.9 KiB) after R392a's confirm review, no smaller than before
# the move, so R392b sets a target to shrink it, starting with rules that repeat a shared component's.
VIEWER_CHROME_CSS_KIB = 50
