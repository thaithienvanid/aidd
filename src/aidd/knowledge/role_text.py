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
    **{f"{{docs:{k}}}": f"its {k} docs" for k in config.DOC_TYPES},
    "{scope}": "the scope of its Tasks",
    "{scope:assigned}": "the scope of the Tasks assigned to it by name",
    "{skeleton}": "its walking-skeleton Tasks",
    "{living}": "its product-level work (`graph.documents`)",
}


def role_writes(writes: list[str]) -> str:
    """A role's write area in words; its linked-doc types (`{docs:<type>}`) as one phrase where the first one stands."""
    doc_types = [w[len("{docs:") : -1] for w in writes if w.startswith("{docs:")]
    words = []
    for w in writes:
        if not w.startswith("{docs:"):
            words.append(_PLACEHOLDERS.get(w, f"`{w}`"))
        elif w[len("{docs:") : -1] == doc_types[0]:
            words.append(f"its {kernel_text.series(doc_types, 'and')} docs")
    return ", ".join(words) or "nothing (read-only)"


def role_area(role: dict) -> str:
    """The write area with the Spec rule that also binds it, and the extra areas it writes where no Spec froze them."""
    area = _spec_area(role)
    unfrozen = role.get("writes_unfrozen")
    if not unfrozen:
        return area
    return f"{area}, and {role_writes(unfrozen)} on a change with no Spec or on the emergency route, where nothing is frozen"


def _spec_area(role: dict) -> str:
    """The write area with the Spec rule that also binds it: files that ship must sit inside the scope."""
    if role.get("in_scope"):
        if role["writes"] == ["{scope}"]:
            return "its Tasks' scope"
        specs = "the work items, and " if "{specs_dir}" in role["writes"] else ""
        proposals = ", and the proposals folder" if "{proposals_dir}" in role["writes"] else ""
        rest = [w for w in role["writes"] if w not in ("{specs_dir}", "{proposals_dir}")]
        return f"{specs}{role_writes(rest)} inside the change's scope{proposals}"
    own = [w for w in role["writes"] if w in _PLACEHOLDERS]
    paths = [w for w in role["writes"] if w not in _PLACEHOLDERS and not w.startswith(".aidd/")]
    output = [w for w in role["writes"] if w.startswith(".aidd/")]
    text = role_writes(own) if own else ""
    if paths:
        text += (", and " if text else "") + f"{role_writes(paths)} once a Task's scope covers them, after Spec approval"
    if output:
        text += (", and " if text else "") + f"{role_writes(output)} (aidd's git-ignored output)"
    return text or role_writes([])


def role_loop(role: dict) -> str:
    """A role's loop steps, and the routes it works in as a person reads them, such as "Implement (no Spec, Spec first)": a word
    once, though two routes share it."""
    words = config.route_words()
    return f"{', '.join(role['steps'])} ({', '.join(dict.fromkeys(words[route] for route in role['routes']))})"


def practice_names() -> list[str]:
    """The practice skills, in the order the roles first name them."""
    return list(dict.fromkeys(x for k in team_registry.roles()["order"] for x in team_registry.roles()["roles"][k]["skills"]))


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
# `aidd init --aidd-team` installs no plugin, so it writes the reference to the repository and points there instead.
ROLE_REFERENCE = "the aidd-team roles reference (`references/roles.md` in `aidd-team:aidd-team`)"


# The skill every role preloads: the aidd skill, the rulebook each agent file tells the role to follow. In the aidd
# plugin its name is `aidd:aidd`; `aidd init --aidd-team` writes it as the project skill `aidd`.
CORE_SKILL = "aidd:aidd"
