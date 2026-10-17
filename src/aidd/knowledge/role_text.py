"""Role and practice text from the team registry: what a role writes, its area and loop steps, and the practice skills
with their standards."""

from __future__ import annotations

import json
import re

from aidd import config
from aidd.kernel import resources
from aidd.kernel import text as kernel_text
from aidd.knowledge import team_registry

_PLACEHOLDERS = {
    "{specs_dir}": "the work items",
    "{proposals_dir}": "the proposals folder",
    "{spec}": "the active Spec",
    "{tests}": "its test files",
    "{design}": "its design files",
    "{explorations}": "its explorations",
    "{docs}": "its frozen docs",
    **{f"{{docs:{k}}}": f"its {k} docs" for k in config.DOC_KINDS},
    "{scope}": "the scope of its Tasks",
    "{skeleton}": "its walking-skeleton Tasks",
}


def role_writes(writes: list[str]) -> str:
    """A role's write area in words; its linked-doc kinds (`{docs:<kind>}`) as one phrase where the first one stands."""
    kinds = [w[len("{docs:") : -1] for w in writes if w.startswith("{docs:")]
    words = []
    for w in writes:
        if not w.startswith("{docs:"):
            words.append(_PLACEHOLDERS.get(w, f"`{w}`"))
        elif w[len("{docs:") : -1] == kinds[0]:
            words.append(f"its {kernel_text.series(kinds, 'and')} docs")
    return ", ".join(words) or "nothing (read-only)"


def role_area(r: dict) -> str:
    """The write area with the Spec rule that also binds it: files that ship must sit inside the scope."""
    if r.get("in_scope"):
        if r["writes"] == ["{scope}"]:
            return "its Tasks' scope"
        specs = "the work items, and " if "{specs_dir}" in r["writes"] else ""
        proposals = ", and the proposals folder" if "{proposals_dir}" in r["writes"] else ""
        rest = [w for w in r["writes"] if w not in ("{specs_dir}", "{proposals_dir}")]
        return f"{specs}{role_writes(rest)} inside the change's scope{proposals}"
    own = [w for w in r["writes"] if w in _PLACEHOLDERS]
    paths = [w for w in r["writes"] if w not in _PLACEHOLDERS]
    text = role_writes(own) if own else ""
    if paths:
        text += (", and " if text else "") + f"{role_writes(paths)} once a Task's scope covers them, after Spec approval"
    return text or role_writes([])


def role_loop(r: dict) -> str:
    return f"{', '.join(r['steps'])} ({', '.join(r['lanes'])} lane{'s' if len(r['lanes']) > 1 else ''})"


def practice_names() -> list[str]:
    """The practice skills, in the order the roles first name them."""
    return list(dict.fromkeys(x for k in team_registry.roles()["order"] for x in team_registry.roles()["roles"][k]["practices"]))


def practice_front(name: str) -> dict:
    """The front matter of a practice skill: `name`, `description`, and `checked` (from `metadata`)."""
    text = (resources.data_dir("team") / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"practice skill {name!r} has no front matter")
    front: dict = {}
    for line in text[4 : text.index("\n---", 4)].splitlines():
        m = re.match(r"^\s*([\w-]+): (.+)$", line)
        if m:
            value = m.group(2).strip()
            front[m.group(1)] = json.loads(value) if value.startswith('"') else value
    if not {"name", "description", "checked"} <= set(front):
        raise ValueError(f"practice skill {name!r} needs name, description, and metadata.checked in its front matter")
    return front


# Where an agent file finds its role's standards and practice skills: the team skill's roles reference in the plugin.
# `aidd init --team` installs no plugin, so it writes the reference to the repository and points there instead.
ROLE_REFERENCE = "the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`)"


# The skill every role preloads: the aidd skill, the rulebook each agent file tells the role to follow. In the aidd
# plugin its name is `aidd:aidd`; `aidd init --team` writes it as the project skill `aidd`.
CORE_SKILL = "aidd:aidd"
