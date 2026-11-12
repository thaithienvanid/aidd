"""Rename the domain packs to domain skills: the plugin `aidd-packs` becomes `aidd-domains`, and "domain pack" becomes "domain skill".

What it changes, in every tracked text file except the CHANGELOG, which records what each release did under the names it had, and the decision records
under `docs/decisions/`, which name the old words on purpose:

- the plugin's folder, its link inside `plugins/aidd-cli/plugins/`, and the reference page `domain-packs.md`, moved with `git mv`;
- `aidd-packs` becomes `aidd-domains`, and `domain-packs` becomes `domain-skills` (a page name, an anchor, a keyword);
- "domain pack" and "domain packs" become "domain skill" and "domain skills", in any case, also across a line break;
- the config key `agents.domain_packs` becomes `agents.domain_skills`, in the schema, the code, the tests, and the docs;
- the word "pack" that still names a domain skill, where a determiner, a skill's own name, or "or skill" shows it (`PROSE`).

The Python module `aidd.setup.domain_packs`, the generator modules, `schemas/packs.json`, and the command `aidd eval packs` keep
their names. Run it twice and the second run changes nothing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OLD_PLUGIN, NEW_PLUGIN = "aidd-packs", "aidd-domains"
MOVES = (
    (f"plugins/{OLD_PLUGIN}", f"plugins/{NEW_PLUGIN}"),
    ("plugins/aidd-team/skills/aidd-team/references/domain-packs.md", "plugins/aidd-team/skills/aidd-team/references/domain-skills.md"),
)
LINK_OLD, LINK_NEW = f"plugins/aidd-cli/plugins/{OLD_PLUGIN}", f"plugins/aidd-cli/plugins/{NEW_PLUGIN}"

# The files that keep the old names: the changelog, and the scripts that rename what this one renames.
KEPT_FILES = frozenset({"CHANGELOG.md", "tools/rename_packs_to_domain_skills.py"})
# The decision records name the old words on purpose, so the script neither reads nor writes under this folder.
KEPT_FOLDER = "docs/decisions/"


def _domain_pack(match: re.Match[str]) -> str:
    """ "domain pack(s)" in the case and the spacing of the match: `Domain packs`, `domain\\n# pack`."""
    word, gap, pack, plural = match["word"], match["gap"], match["pack"], match["plural"]
    skill = "Skill" if pack[0] == "P" else "skill"
    return f"{word}{gap}{skill}{plural}"


DOMAIN_PACK = re.compile(r"(?P<word>[Dd]omain)(?P<gap>[ \t]*(?:\n[ \t]*(?:(?:#|//|\*)[ \t]*)?)?[ \t]*)(?P<pack>[Pp]ack)(?P<plural>s?)(?![A-Za-z_-])")
# The key `agents.domain_packs`, as a dotted path, a YAML key, a quoted key beside "agents", or the schema's own property.
KEY_PATH = re.compile(r"agents\.domain_packs")
KEY_YAML = re.compile(r"(?<=[\s`])domain_packs(?=:|`)")
KEY_QUOTED = re.compile(r'(?<="agents", )"domain_packs"|(?<=\["agents"\]\["properties"\])\["domain_packs"\]|^(\s*)"domain_packs"(?=: \{)', re.MULTILINE)


# The one test that matches the key's name in an error and in a note.
KEY_IN_TEST = ("tests/test_team_packs.py", '"domain_packs"', '"domain_skills"')


def _key(text: str) -> str:
    text = KEY_PATH.sub("agents.domain_skills", text)
    text = KEY_YAML.sub("domain_skills", text)
    return KEY_QUOTED.sub(lambda m: m[0].replace("domain_packs", "domain_skills"), text)


# A domain skill's slug, as `schemas/packs.json` holds it, for "the payments-and-finance pack", and the short names the evals use.
_SLUGS = sorted({str(p["slug"]) for p in json.loads((ROOT / "schemas" / "packs.json").read_text(encoding="utf-8"))} | {"payments", "commerce"})
_SLUG = "(?:" + "|".join(re.escape(s) for s in _SLUGS) + ")"
_DETERMINERS = r"(?:the|a|an|each|every|its|this|that|no|one|per|any|their|these|those|all|other|another|which|whose|any)"
# Each rule, in order: a pattern and its replacement. Where the word "pack" stands for something else, no rule matches: "npm pack",
# "upload-pack", "the business pack", "a skills pack", `aidd eval packs`, `schemas/packs.json`, the `pack:<slug>` target.
PROSE: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), repl)
    for pattern, repl in (
        (r"<pack or skill>", "<skill>"),
        (r"\bpacks or practice skills\b", "domain or practice skills"),
        (r"\bpack or practice skill\b", "domain or practice skill"),
        (r"\bpacks and practice skills\b", "domain and practice skills"),
        (r"\bpack and practice skill\b", "domain and practice skill"),
        (r"\bpacks, practice skills\b", "domain skills, practice skills"),
        (r"\bpacks and skills\b", "domain and practice skills"),
        (r"\bpack or skill\b", "skill"),
        (r"\bpacks or skills\b", "skills"),
        (r"(aidd-domains:<)pack(>)", r"\1name\2"),
        (rf"(\baidd-domains:{_SLUG}`?) pack\b", r"\1 skill"),
        (rf"(\b{_SLUG}`?) pack\b(?!-)", r"\1 skill"),
        (rf"\b(?i:{_DETERMINERS}) packs?\b(?!-)", None),
    )
)


# Phrases where "pack" has no determiner before it, each rewritten as it stands, longest first.
PHRASES = (
    ("business packs'", "business domain skills'"),
    ("business pack's", "business domain skill's"),
    ("business packs", "business domain skills"),
    ("business pack", "business domain skill"),
    ("a data pack", "a data domain skill"),
    ("the practice skills and packs", "the practice skills and domain skills"),
    ("commands, packs, and practice skills", "commands, domain skills, and practice skills"),
    ("opt-in packs", "opt-in domain skills"),
    ("a skill, pack, agent file", "a skill, agent file"),
    ("its own pack or stack", "its own skill or stack"),
    ("the cloud pack", "the cloud domain skill"),
    ("the AI-agents pack", "the ai-agents-and-tools domain skill"),
    ("regulated or platform pack", "regulated or platform domain skill"),
    ("regulated and platform packs", "regulated and platform domain skills"),
    ("an area's pack is missing", "an area's domain skill is missing"),
    ("a generated pack adds", "a generated domain skill adds"),
    ("every generated block, pack, and agent file", "every generated block, domain skill, and agent file"),
    ("(specialists, packs, policy", "(specialists, domain skills, policy"),
    ("load the same packs", "load the same domain skills"),
    ("-front-end` and `aidd-domains:mobile-apps` packs say", "-front-end` and `aidd-domains:mobile-apps` skills say"),
    ("ai-agents-and-tools` packs say", "ai-agents-and-tools` skills say"),
    ("both packs point to", "both domain skills point to"),
    ("the commerce, games, and children's packs", "the commerce, games, and children's domain skills"),
    ("the privacy pack point", "the privacy domain skill point"),
    ("The list of packs and when each applies", "The list of domain skills and when each applies"),
    ("a role or pack applies", "a role or domain skill applies"),
    ("a role or pack names", "a role or domain skill names"),
    ("The first role, pack, or extension", "The first role, domain skill, or extension"),
    ("`enterprise-controls` # pack)", "`enterprise-controls` # skill)"),
    ("so it loads them: its card then gives", "so it loads them. Its card then gives"),
)


def _prose(text: str, rel: str) -> str:
    # A library standard names its domain skill once, `aidd-domains:<name>`, and then says "the skill": its body has a word cap.
    skill = "skill" if rel.startswith("standards/") else "domain skill"
    for old, new in PHRASES:
        text = text.replace(old, new)
    for pattern, repl in PROSE:
        if repl is None:
            text = pattern.sub(lambda m: m[0].replace("packs", f"{skill}s").replace("pack", skill), text)
        else:
            text = pattern.sub(repl, text)
    return text


def rewrite(text: str, rel: str = "") -> str:
    if rel == KEY_IN_TEST[0]:
        text = text.replace(KEY_IN_TEST[1], KEY_IN_TEST[2])
    text = text.replace(OLD_PLUGIN, NEW_PLUGIN).replace("domain-packs", "domain-skills").replace("domain-pack skills", "domain skills")
    return _prose(_key(DOMAIN_PACK.sub(_domain_pack, text)), rel)


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def _move(old: str, new: str) -> bool:
    if not (ROOT / old).exists() and not (ROOT / old).is_symlink():
        return False
    _git("mv", old, new)
    print(f"moved {old} -> {new}")
    return True


def _relink() -> None:
    """The link inside aidd-cli's folder keeps its place and points at the moved plugin."""
    link = ROOT / LINK_NEW
    if link.is_symlink() and (target := os.readlink(link)).count(OLD_PLUGIN):
        link.unlink()
        link.symlink_to(target.replace(OLD_PLUGIN, NEW_PLUGIN))
        _git("add", LINK_NEW)
        print(f"relinked {LINK_NEW}")


def _refresh_held_out_lock() -> int:
    """The hash of each held-out eval case that these edits changed and nobody has read yet, as the lock's own message says to set it.
    A case whose score was read stays as it is: the lock then fails, and a person decides."""
    sys.path.insert(0, str(ROOT / "src"))
    from aidd.evals import held_out

    path = ROOT / held_out.LOCK_FILE
    text, refreshed = path.read_text(encoding="utf-8"), 0
    cases = held_out.held_out_cases(ROOT)
    for entry in held_out.read_lock(ROOT)["cases"]:
        now = cases.get((entry["suite"], entry["case"]))
        if now and not entry["first_read_on"] and now["sha256"] != entry["content_sha256"]:
            text = text.replace(f'"content_sha256": "{entry["content_sha256"]}"', f'"content_sha256": "{now["sha256"]}"')
            refreshed += 1
    path.write_text(text, encoding="utf-8")
    return refreshed


def main() -> int:
    for old, new in MOVES:
        _move(old, new)
    _move(LINK_OLD, LINK_NEW)
    _relink()
    changed = 0
    for rel in _git("ls-files").splitlines():
        path = ROOT / rel
        if rel in KEPT_FILES or rel.startswith(KEPT_FOLDER) or path.is_symlink() or not path.is_file():
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = rewrite(original, rel)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
    print(f"updated {changed} file(s), and {_refresh_held_out_lock()} held-out hash(es)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
