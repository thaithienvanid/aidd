"""A step loads every file that loads on a signal: the guard that replaces a per-file size cap.

A reference or a template that nothing names is a file no step reads, so its size costs nothing and its rules reach no one. When
text moves into a reference to restructure a large file by topic, this is the check that matters: the new file is named where
the step that needs it reads.

- Each reference of the aidd skill is named by SKILL.md's load table, or by a file that table reaches (a file one reference
  points to counts), and every name the skill gives is a file on disk.
- Each template is loaded by a step: the skill names it, or `aidd new` writes it (a row of schemas/item-types.json, by its
  `templates` or by the type's own name), or a team skill, command, or role names it.
- Every Markdown link in the skill's files resolves.
- Each practice skill is listed by at least one role.

The helpers are plain functions, so each check also runs on a skill folder built to break it.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import knowledge
from aidd.knowledge import team_registry

SKILL = ROOT / ".agents" / "skills" / "aidd"
TEAM = ROOT / "plugins" / "aidd-team"
NAMED = re.compile(r"(?:references|assets)/[\w.-]+\.(?:md|json|yaml|mjs)")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)\s]*)?\)")
# A file the skill reads without a step naming it: the always-loaded one, which SKILL.md names in its first row.
ALWAYS = {"references/graph.md"}


def named_in(text: str) -> set[str]:
    """The `references/...` and `assets/...` paths a text names, relative to the skill's folder."""
    return set(NAMED.findall(text))


def linked_in(text: str, folder: str) -> set[str]:
    """The files a text links relative to `folder` (`references` or `assets`), as paths relative to the skill's folder."""
    out = set()
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        parts = [p for p in f"{folder}/{target}".split("/") if p != "."]
        while ".." in parts:
            i = parts.index("..")
            parts = parts[: max(i - 1, 0)] + parts[i + 1 :]
        out.add("/".join(parts))
    return out


def reached(skill: Path) -> set[str]:
    """Every file the load table of `skill`/SKILL.md names, and each file those name, as paths relative to `skill`."""
    start = (skill / "SKILL.md").read_text(encoding="utf-8")
    found = named_in(start) | ALWAYS
    todo = sorted(found)
    while todo:
        rel = todo.pop()
        path = skill / rel
        if path.suffix == ".md" and path.is_file():
            text = path.read_text(encoding="utf-8")
            new = (named_in(text) | linked_in(text, rel.split("/")[0])) - found
            found |= new
            todo += sorted(new)
    return found


def unloaded(skill: Path, folder: str, loaded_elsewhere=lambda name: False) -> list[str]:
    """The Markdown files in `skill`/`folder` that no step loads: not reached from SKILL.md, and not loaded elsewhere."""
    seen = reached(skill)
    files = sorted(p.name for p in (skill / folder).glob("*.md"))
    return [f"{folder}/{n}" for n in files if f"{folder}/{n}" not in seen and not loaded_elsewhere(n)]


def missing_names(skill: Path) -> list[str]:
    """The paths SKILL.md names that are not files."""
    return sorted(n for n in named_in((skill / "SKILL.md").read_text(encoding="utf-8")) if not (skill / n).exists())


def broken_links(skill: Path) -> list[str]:
    """Each Markdown link in the skill's files whose target is not a file or folder, as `file -> target`."""
    out = []
    for path in [skill / "SKILL.md", *sorted((skill / "references").glob("*.md")), *sorted((skill / "assets").glob("*.md"))]:
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if not target.startswith(("http://", "https://", "mailto:")) and not (path.parent / target).exists():
                out.append(f"{path.relative_to(skill)} -> {target}")
    return out


def made_skill(root: Path, skill_md: str, references: dict[str, str], assets: dict[str, str] | None = None) -> Path:
    skill = root / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "assets").mkdir()
    (skill / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (skill / "references" / "graph.md").write_text("loop", encoding="utf-8")
    for name, text in references.items():
        (skill / "references" / name).write_text(text, encoding="utf-8")
    for name, text in (assets or {}).items():
        (skill / "assets" / name).write_text(text, encoding="utf-8")
    return skill


def item_type_templates() -> set[str]:
    """The template file of each type `aidd new` writes: its `templates` values and the template of each of its `files`, else the type's own name."""
    types = json.loads((ROOT / "schemas" / "item-types.json").read_text(encoding="utf-8"))["types"]
    named = {v for t in types.values() for v in t.get("templates", {}).values()} | {f["template"] for t in types.values() for f in t.get("files", [])}
    return named | {f"{name}.md" for name, t in types.items() if "templates" not in t}


def team_corpus() -> str:
    """The text of the team's skills, commands, and agents, and the two registries a step reads."""
    files = [*TEAM.rglob("*.md"), ROOT / "schemas" / "roles.json", ROOT / "schemas" / "item-types.json"]
    return "\n".join(p.read_text(encoding="utf-8") for p in files)


class TheCheckFindsWhatNothingLoads(unittest.TestCase):
    def test_a_reference_no_step_names_is_found_and_one_a_reached_file_links_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = made_skill(
                Path(tmp),
                "| A level | `references/risk.md` |\n| Always | `references/graph.md` |\n",
                {"risk.md": "See [the routes](routes.md) and `references/state.md`.", "routes.md": "x", "state.md": "x", "orphan.md": "x"},
            )
            self.assertEqual(unloaded(skill, "references"), ["references/orphan.md"])
            self.assertEqual(missing_names(skill), [])

    def test_a_name_the_skill_gives_that_is_not_a_file_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = made_skill(Path(tmp), "Read `references/gone.md` and `references/graph.md`.", {})
            self.assertEqual(missing_names(skill), ["references/gone.md"])

    def test_a_link_that_does_not_resolve_is_found_and_an_external_one_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = made_skill(Path(tmp), "x `references/a.md`", {"a.md": "[b](b.md) [web](https://example.org/x.md) [up](../SKILL.md)"})
            self.assertEqual(broken_links(skill), ["references/a.md -> b.md"])

    def test_a_template_another_step_loads_is_not_an_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill = made_skill(Path(tmp), "x `references/a.md`", {"a.md": "x"}, {"t.md": "x", "u.md": "x"})
            self.assertEqual(unloaded(skill, "assets", lambda n: n == "u.md"), ["assets/t.md"])


class EveryFileOfTheSkillIsLoadedByAStep(unittest.TestCase):
    def test_each_reference_is_named_by_the_load_table_or_by_a_file_it_reaches(self):
        self.assertEqual(unloaded(SKILL, "references"), [], "name the reference in SKILL.md's load table, or link it from a reference that is")

    def test_each_template_is_loaded_by_a_step(self):
        types, corpus = item_type_templates(), team_corpus()
        found = unloaded(SKILL, "assets", lambda n: n in types or f"assets/{n}" in corpus)
        self.assertEqual(found, [], "name the template in the load table, give it a row in schemas/item-types.json, or name it where a step reads")

    def test_each_name_the_skill_gives_is_a_file(self):
        self.assertEqual(missing_names(SKILL), [])

    def test_each_markdown_link_in_the_skills_files_resolves(self):
        self.assertEqual(broken_links(SKILL), [])

    def test_the_always_loaded_file_is_named_in_the_first_row(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if line.startswith("| Always |"))
        self.assertIn("references/graph.md", row)

    def test_each_practice_skill_is_listed_by_a_role(self):
        listed = set()
        for role in team_registry.roles()["roles"].values():
            listed |= set(role.get("skills", [])) | set(role.get("preload", []))
        self.assertEqual(sorted(set(knowledge.practice_names()) - listed), [], "a practice skill no role lists is loaded by no step")


if __name__ == "__main__":
    unittest.main()
