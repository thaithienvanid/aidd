"""The fidelity pass's shots: the views a pass takes, sized to the change, as the prototyping skill's design review says.

This file sits beside `prototype.py` and belongs to the same tool. It uses the standard library only. It reads a design that
`design_checks.read_design` read, and the device table, and returns each view to capture: its screen, state, frame, theme,
text size, and direction, why it is taken, its deep link in the viewer, and its screenshot's name.

- A new screen or flow, or a whole design: the full matrix of its screens. Every state at the full pass's frames, in both
  themes, then one view at 200% text and one right to left, on each screen's fullest state.
- A change to one component: each screen it appears on first, as a person sees it, at the overview frame and the light
  theme. Then its interaction states once on each variant, in both themes, which the state check reads. Then one view at
  the narrowest frame and one at 200% text.

It never selects nothing: a component or a screen the design does not have is a problem, with the names it has.
"""

from __future__ import annotations

from typing import Protocol
from urllib.parse import quote

# The full pass's frames: 320, a phone, and 1024, by their ids in the device table. A product that ships other frames names them.
FULL_FRAMES = ("320", "ios", "1024")
# The frame a person sees first: the viewer's own default frame (DEFAULT_FRAME in viewer.html), else the first frame named.
OVERVIEW_FRAME = "1024"
THEMES = ("light", "dark")


class Design(Protocol):
    """What the selection reads from a design: `design_checks.DesignReader` has it."""

    screens: list
    components: list[tuple[str, str, str, str]]
    state_sizes: dict[tuple[str, str], int]


def _shot(
    screen: str, state: str, frame: str, theme: str, purpose: str, *, text: str = "100", direction: str = "ltr", part: tuple[str, str] | None = None
) -> dict:
    """One view: its fields, its deep link in the viewer at actual size, and its screenshot's name. A product screen
    `<flow>:<screen>` names its image `<flow>-<screen>`, since a colon breaks Windows."""
    query = f"theme={theme}&frame={frame}&zoom=actual" + ("&text=200" if text == "200" else "") + ("&dir=rtl" if direction == "rtl" else "")
    name = "-".join([screen.replace(":", "-"), state, frame, theme] + (["text-200"] if text == "200" else []) + (["rtl"] if direction == "rtl" else []))
    shot = {"screen": screen, "state": state, "frame": frame, "theme": theme, "text": text, "dir": direction, "purpose": purpose}
    if part:
        shot |= {"component": part[0], "variant": part[1]}
        name += f"-{part[0]}-{part[1]}"
    return shot | {"link": f"#{quote(screen, safe='')}/{quote(state, safe='')}?{query}", "file": f"{name}.png"}


def _fullest(design: Design, screen) -> str:
    """The screen's state with the most elements in the design, the first such in its order: where text at 200% and right
    to left are likeliest to break."""
    return max(screen.states, key=lambda state: design.state_sizes.get((screen.id, state), 0))


def _overview(frames: tuple[str, ...]) -> str:
    return OVERVIEW_FRAME if OVERVIEW_FRAME in frames else frames[0]


def matrix(design: Design, screen_ids: list[str], frames: tuple[str, ...]) -> list[dict]:
    """The full pass of these screens: every state at each frame in both themes, then 200% text and right to left on each
    screen's fullest state, at the overview frame."""
    out = []
    for screen in (s for s in design.screens if s.id in screen_ids and s.states):
        out += [_shot(screen.id, state, frame, theme, "matrix") for state in screen.states for frame in frames for theme in THEMES]
        fullest = _fullest(design, screen)
        out.append(_shot(screen.id, fullest, _overview(frames), "light", "text-200", text="200"))
        out.append(_shot(screen.id, fullest, _overview(frames), "light", "rtl", direction="rtl"))
    return out


def component_pass(design: Design, name: str, frames: tuple[str, ...], widths: dict[str, int]) -> list[dict]:
    """A change to one component: each screen it appears on, then each variant's states in both themes, then the narrowest
    frame and 200% text where it first appears. A component in the chrome, on every screen, is seen on the first."""
    opening = {s.id: s.opens_in() for s in design.screens if s.states}
    places: dict[str, tuple[str, str]] = {}  # screen: (its state that shows the component, the variant there)
    variants: dict[str, tuple[str, str]] = {}  # variant: (screen, state) where it first shows
    for component, variant, screen, state in design.components:
        where = screen or next(iter(opening), "")
        if component != name or where not in opening:
            continue
        place = (where, state or opening[where] or "")
        places.setdefault(where, (place[1], variant))
        variants.setdefault(variant, place)
    overview = _overview(frames)
    out = [_shot(screen, state, overview, "light", "overview") for screen, (state, _) in places.items()]
    out += [_shot(screen, state, overview, theme, "states", part=(name, variant)) for variant, (screen, state) in variants.items() for theme in THEMES]
    if places:
        screen, (state, _) = next(iter(places.items()))
        narrowest = min(frames, key=lambda f: widths.get(f, 0))
        if narrowest != overview:
            out.append(_shot(screen, state, narrowest, "light", "narrow"))
        out.append(_shot(screen, state, overview, "light", "text-200", text="200"))
    return out


def shots(design: Design, frames_table: dict[str, dict], *, components: list[str], screen_ids: list[str], frames: list[str]) -> tuple[list[dict], list[str]]:
    """The views a fidelity pass takes, and the problems: (shots, problems). No component and no screen named: the full matrix
    of every screen. A screen named: its full matrix. A component named: its pass. Both: each, once."""
    known_screens = [s.id for s in design.screens]
    known_components = sorted({c[0] for c in design.components})
    problems = [f"the frame {f!r} is not in the device table: name one of {', '.join(frames_table)}" for f in frames if f not in frames_table]
    problems += [f"the design has no screen {s!r}: name one of {', '.join(known_screens) or 'none'}" for s in screen_ids if s not in known_screens]
    problems += [f"no screen shows the component {c!r}: name one of {', '.join(known_components) or 'none'}" for c in components if c not in known_components]
    if problems or not frames:
        return [], problems or ["name at least one frame"]
    chosen = tuple(frames)
    found = matrix(design, screen_ids or ([] if components else known_screens), chosen)
    widths = {k: f["width"] for k, f in frames_table.items()}
    for name in components:
        found += component_pass(design, name, chosen, widths)
    unique = list({shot["file"]: shot for shot in found}.values())
    return unique, [] if unique else ["the design has no state to capture: give each screen a data-state"]
