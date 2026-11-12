"""Every budgeted file with its size, its cap, and its share (B8). One list serves tests/test_budget_headroom.py, so a new
budget joins the headroom line the moment this module reads it.

A share is the size over the cap, without the 3% headroom (`budgets.within` adds that for the caps themselves). The units
are the ones each cap is written in: bytes, estimated tokens, characters, and lines. A file of a class that loads on a signal
has its class limit as its cap and is in CLASS_GROUPS.
"""

import re
from pathlib import Path
from typing import NamedTuple

import budgets
import test_code_shape
from engagement import BLOCK, BLOCK_CAP
from helpers import ROOT

from aidd.docsgen import pack_budget, token_caps
from aidd.knowledge import team_registry
from aidd.setup import doctor_checks

# The groups that load on a signal and have one limit for the class (budgets.REFERENCE_BYTES, budgets.TEMPLATE_BYTES, token_caps).
# They are readability bounds, so the headroom line does not apply to them: a file near its limit is a note to restructure it
# (budgets.near_class_limit), and a file past it fails where the limit is held.
CLASS_GROUPS = frozenset({"reference", "template", "pack skill", "practice skill", "skill reference"})

SKILL = ROOT / ".agents" / "skills" / "aidd"
TEAM = ROOT / "plugins" / "aidd-team"


class Share(NamedTuple):
    group: str
    name: str
    size: float
    cap: float
    unit: str

    @property
    def key(self) -> str:
        return f"{self.group}: {self.name}"

    @property
    def share(self) -> float:
        return self.size / self.cap


def _size(path: Path) -> int:
    return len(path.read_bytes())


def role_start_text() -> dict[str, int]:
    """The bytes a role starts with: its file's body, each skill its front matter preloads, and graph.md where it preloads the
    aidd skill, which says to read graph.md always."""
    sizes = {}
    loop = _size(SKILL / "references" / "graph.md")
    for key in team_registry.roles()["order"]:
        text = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
        head = text.split("---")[1]
        skills = re.findall(r"^  - (.+)$", head.split("\nskills:\n", 1)[1], re.M) if "\nskills:\n" in head else []
        total = len(text[text.index("\n---", 4) + 4 :].encode())
        for name in skills:
            plugin, _, skill = name.partition(":")
            total += _size((SKILL.parent / skill if plugin == "aidd" else TEAM / "skills" / skill) / "SKILL.md")
        sizes[key] = total + (loop if "aidd:aidd" in skills else 0)
    return sizes


def shares() -> list[Share]:
    out = [Share("skill", "SKILL.md", _size(SKILL / "SKILL.md"), budgets.SKILL_BYTES, "bytes")]
    out.append(Share("skill", "references/graph.md", _size(SKILL / "references" / "graph.md"), budgets.LOOP_BYTES, "bytes"))
    refs = sorted(p for p in (SKILL / "references").glob("*.md") if p.name != "graph.md")
    out += [Share("reference", p.name, _size(p), budgets.REFERENCE_BYTES, "bytes") for p in refs]
    out += [Share("template", p.name, _size(p), budgets.TEMPLATE_BYTES, "bytes") for p in sorted((SKILL / "assets").glob("*.md"))]
    out += [Share("role file", f"{k}.md", _size(TEAM / "agents" / f"{k}.md"), budgets.ROLE_FILE_BYTES, "bytes") for k in team_registry.roles()["order"]]
    out += [Share("role start", key, size, budgets.ROLE_START_BYTES, "bytes") for key, size in role_start_text().items()]
    out.append(Share("instructions", "AGENTS.md", _size(ROOT / "AGENTS.md"), doctor_checks.INSTRUCTION_MAX_BYTES, "bytes"))
    out.append(Share("instructions", "the block aidd writes into AGENTS.md", len(BLOCK.encode()), BLOCK_CAP, "bytes"))
    sizes, _ = pack_budget.pack_sizes_and_problems()
    for s in sizes:
        cap = token_caps.PACK_TOKENS if s["type"] == "pack" else token_caps.PRACTICE_TOKENS
        out.append(Share(f"{s['type']} skill", s["name"], s["tokens"], cap, "tokens"))
        out += [Share("skill reference", f"{s['name']}/{ref}", t, token_caps.REFERENCE_TOKENS, "tokens") for ref, t in s["references"].items()]
    for d in pack_budget.pack_descriptions():
        cap = pack_budget.ROUTER_DESCRIPTION_CHARS if d["name"] == "aidd-team" else pack_budget.DESCRIPTION_CHARS
        out.append(Share("description", f"{d['type']} {d['name']}", d["chars"], cap, "characters"))
    src = ROOT / "src"
    for path in sorted((src / "aidd").rglob("*.py")):
        out.append(Share("module", str(path.relative_to(src)), len(path.read_text(encoding="utf-8").splitlines()), test_code_shape.LONG_MODULE, "lines"))
    return out
