"""One builder for the facts of a loop case: the files, and a scratch git repository that holds them.

A reader of any package starts from `build(facts, root)`, so no reader interprets a case in its own way. The facts are the
vocabulary of tests/graph_cases.py. This builder writes what they say and validates nothing: a file in the shape of a package that
has not landed is still written, and the reader of that package reads it.

- `spec` (the Spec SPEC-1 on the branch) and `specs` (more Specs, an id for each) are written with the front matter the facts give
  over a valid Spec. `trunk` says what the default branch holds: `spec` or `specs`, null for none, and `merged_at`.
- `intent`, `intents`, `scope`, `releases`, `postmortems`, `docs`, `records`, and `evidence` are written as the files they are.
  `releases` are written in the order given, which need not be the order of `released_at`.
- An Intent has a history of its fields (`IntentHistory`): the default branch first holds it without each field a commit names, as
  `product/intents/INTENT-1.md#approval`, and that commit writes the field, with the facts' value or, for a field the facts leave
  out, a value of its own. An Intent whose `approval` no commit names gets it as a person's approval commit holds it: alone, on the
  branch, with `Approved-by:` and `Approves:` (A.12 and C.2 assume an approval that holds unless the row says otherwise).
- `git.commits` are made in order, each `{name, on, holds, trailers, changes}`: `holds` lists the Specs the tree holds at that
  commit, `trailers` are the commit message's trailer lines, and `changes` are paths that the commit touches (`path#field` names a
  field of a file). A commit's `name` stands for its id wherever a fact names a commit, and the builder puts the real id there.
  `git.tags`, `git.deleted_tags`, `git.remote`, and `git.shallow` make the refs and the clone.
- `told` (what a person said) and `day` are no file, so the builder does not write them.
"""

from __future__ import annotations

import copy
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple

import helpers

BASE_SPEC = {
    "type": "spec",
    "id": "SPEC-1",
    "title": "Add a percentage discount",
    "change_type": "feat",
    "route": "normal",
    "confidence": "high",
    "risk": {"summary": "Shoppers with a code pay less at checkout.", "dimensions": [], "irreversible": False},
    "rollback": "revert the commit",
    "tasks": [{"id": "T1", "title": "Apply the discount at checkout", "scope": ["src/checkout/"], "risk": "low", "proof": "test `discount`"}],
    "tests": {
        "files": ["tests/test_discount.py"],
        "commands": [{"name": "discount", "command": ["python3", "-m", "unittest", "tests.test_discount"], "new_behavior": True, "covers": ["A1"]}],
    },
}
SPEC_BODY = helpers.SAMPLE_SPEC.split("\n---\n", 1)[1]
BASE_INTENT = {"type": "intent", "id": "INTENT-1", "title": "Let guests book online"}
INTENT_BODY = "\n## Problem\n\nGuests cannot book online.\n"
INTENTS = "product/intents/"
SAFE = re.compile(r"^[A-Za-z0-9_./ @:<>+-]+$")


class Built(NamedTuple):
    root: Path
    shas: dict[str, str]
    specs: dict[str, str]


def scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def emit(value, indent: int = 0) -> str:
    """Block YAML for a mapping, a list, and scalars: the front matter of a file."""
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        for key, sub in value.items():
            if isinstance(sub, (dict, list)) and sub:
                lines.append(f"{pad}{key}:\n{emit(sub, indent + 1)}")
            else:
                lines.append(f"{pad}{key}: {scalar(sub) if not isinstance(sub, (dict, list)) else ('{}' if isinstance(sub, dict) else '[]')}")
    else:
        for sub in value:
            if isinstance(sub, dict) and sub:
                first, *rest = emit(sub, indent + 1).split("\n")
                lines.append(f"{pad}- {first.lstrip()}")
                lines.extend(rest)
            elif isinstance(sub, (dict, list)):
                lines.append(f"{pad}- {'{}' if isinstance(sub, dict) else '[]'}")
            else:
                lines.append(f"{pad}- {scalar(sub)}")
    return "\n".join(lines)


def named(value, shas: dict[str, str]):
    """The value with each commit name replaced by the id of the commit it stands for."""
    if isinstance(value, str):
        return shas.get(value, value)
    if isinstance(value, list):
        return [named(v, shas) for v in value]
    if isinstance(value, dict):
        return {k: named(v, shas) for k, v in value.items()}
    return value


def front_matter(fields: dict, body: str = "") -> str:
    return f"---\n{emit(fields)}\n---\n{body}"


def spec_file(spec_id: str, facts: dict, shas: dict[str, str], notes: list[dict]) -> tuple[str, str]:
    """The path and the text of a Spec: a valid one, with the facts laid over it."""
    fields = copy.deepcopy(BASE_SPEC)
    fields["id"] = spec_id
    own = {k: v for k, v in facts.items() if k not in ("placeholder", "path", "tasks")}
    for task in facts.get("tasks", []):
        mine = next((t for t in fields["tasks"] if t["id"] == task["id"]), None)
        if mine is None:
            fields["tasks"].append(dict(task))
        else:
            mine.update(task)
    fields.update(named(own, shas))
    body = SPEC_BODY.replace("The checkout totals the cart", "TODO: the checkout totals the cart") if facts.get("placeholder") else SPEC_BODY
    for note in notes:
        body += f"\n```aidd-handoff\ndone: a handoff note\nnext_role: reviewer\nneeds: none\nstopped_at: none\nrole: {note['role']}\nhead: {shas.get(note['head'], note['head'])}\nby: {note['by']}\n```\n"
    return facts.get("path", f"specs/{spec_id}.md"), front_matter(fields, body)


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def specs_of(facts: dict, key: str = "spec") -> dict[str, dict]:
    """The Specs a facts block names, an id for each: `spec` is SPEC-1, and `specs` adds the others."""
    found = {}
    if facts.get(key):
        found["SPEC-1"] = facts[key]
    found.update(facts.get(f"{key}s") or {})
    return found


class IntentHistory:
    """The fields of each Intent as the tree holds them, commit by commit: what a commit's `changes` name is written there, and the
    rest from the first commit on."""

    def __init__(self, facts: dict, commits: list[dict]):
        self.facts: dict[str, dict] = dict(facts.get("intents") or {})
        if facts.get("intent"):
            self.facts.setdefault(facts["intent"].get("id", "INTENT-1"), facts["intent"])
        self.named = {iid: {f for c in commits for f in self.fields_of(c, iid)} for iid in self.facts}
        self.now = {
            iid: {k: v for k, v in fields.items() if k not in self.named[iid] and k != "approval" and k != "placeholder"} for iid, fields in self.facts.items()
        }

    @staticmethod
    def fields_of(commit: dict, iid: str) -> list[str]:
        """The fields of the Intent `iid` that a commit's `changes` name."""
        return [c.partition("#")[2] for c in commit.get("changes", []) if c.partition("#")[0] == f"{INTENTS}{iid}.md" and c.partition("#")[2]]

    def text(self, iid: str, shas: dict[str, str]) -> str:
        return front_matter({**BASE_INTENT, "id": iid, **named(self.now[iid], shas)}, INTENT_BODY)

    def write_all(self, root: Path, shas: dict[str, str]) -> None:
        for iid in self.facts:
            write(root, f"{INTENTS}{iid}.md", self.text(iid, shas))

    def apply(self, root: Path, name: str, commit: dict, shas: dict[str, str]) -> list[str]:
        """Write each Intent field the commit names, and give back the changes it did not write."""
        rest = []
        for change in commit.get("changes", []):
            rel, _, field = change.partition("#")
            iid = rel.removeprefix(INTENTS).removesuffix(".md")
            if field and rel.startswith(INTENTS) and iid in self.facts:
                self.now[iid][field] = self.facts[iid].get(field, f"{field} as the commit {name} wrote it")
                write(root, rel, self.text(iid, shas))
            else:
                rest.append(change)
        return rest

    def unnamed_approvals(self) -> list[str]:
        """The Intents whose facts hold an `approval` that no commit names."""
        return [iid for iid, fields in self.facts.items() if isinstance(fields.get("approval"), dict) and "approval" not in self.named[iid]]

    def approve(self, root: Path, iid: str, shas: dict[str, str]) -> None:
        """The commit that holds the Intent's approval: it changes only `approval`, with the person's two lines."""
        approval = self.facts[iid]["approval"]
        self.now[iid]["approval"] = approval
        write(root, f"{INTENTS}{iid}.md", self.text(iid, shas))
        commit(root, f"approve {iid}", {"trailers": {"Approved-by": approval.get("by", ""), "Approves": iid}}, shas)


def commit(root: Path, name: str, spec: dict, shas: dict[str, str], history: IntentHistory | None = None) -> None:
    """One commit of the history: its trailers in the message, and its changes in the tree."""
    changes = history.apply(root, name, spec, shas) if history else spec.get("changes", [])
    for change in changes:
        path = root / change.split("#")[0]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            out.write(f"\n<!-- {name}: {change} -->\n" if path.suffix == ".md" else f"\n# {name}\n")
    trailers = "\n".join(f"{k}: {v}" for k, v in spec.get("trailers", {}).items())
    message = f"{name}\n\n{trailers}" if trailers else name
    helpers.git(root, "add", "-A")
    helpers.git(root, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", message)
    shas[name] = helpers.git(root, "rev-parse", "HEAD").strip()


def holds(root: Path, held: list[str], contents: dict[str, dict], shas: dict[str, str]) -> None:
    """Make the tree hold exactly the Specs `held`, each with the content the facts give."""
    for spec_id in sorted({*held, *contents}):
        target = root / "specs" / f"{spec_id}.md"
        if spec_id not in held and target.exists():
            target.unlink()
        elif spec_id in held:
            rel, text = spec_file(spec_id, contents.get(spec_id) or {}, shas, [])
            write(root, rel, text)


def build(facts: dict, root: Path) -> Built:
    """The files and the scratch repository of one case, at `root`: the default branch with its history and the trunk, then a branch."""
    helpers.make_repo(root, branch=None)
    shas: dict[str, str] = {}
    git = facts.get("git") or {}
    config = facts.get("config") or {}
    if config:
        text = (root / ".aidd" / "config.yaml").read_text(encoding="utf-8")
        extra = {k: v for k, v in config.items() if not re.search(rf"(?m)^{k}:", text)}
        write(root, ".aidd/config.yaml", text.rstrip("\n") + "\n" + emit(extra) + "\n")
    trunk = facts.get("trunk")
    contents = specs_of(trunk) if trunk else {}
    commits = git.get("commits", [])
    history = IntentHistory(facts, commits)
    if history.facts:
        history.write_all(root, shas)
        helpers.git(root, "add", "-A")
        helpers.git(root, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "the Intents as planned")
    for spec in (c for c in commits if c.get("on", "main") == "main"):
        if "holds" in spec:
            holds(root, spec["holds"], contents, shas)
        commit(root, spec["name"], spec, shas, history)
    if trunk:
        for spec_id, content in contents.items():
            rel, text = spec_file(spec_id, content, shas, [])
            write(root, rel, text)
        for rel, text in side_files(facts, shas, evidence=False, history=history):
            write(root, rel, text)
        helpers.git(root, "add", "-A")
        helpers.git(root, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "the trunk's tip")
    helpers.git(root, "checkout", "-q", "-b", "feat")
    branch(root, facts, commits, shas, history)
    for tag in git.get("tags", []):
        helpers.git(root, "tag", "-f", tag["name"], shas.get(tag["commit"], "HEAD"))
    for tag in git.get("deleted_tags", []):
        helpers.git(root, "tag", "-d", tag)
    if git.get("remote"):
        remote = Path(tempfile.mkdtemp(prefix="origin-", dir=root.parent)) / "origin.git"
        helpers.git(root.parent, "init", "-q", "--bare", str(remote))
        helpers.git(root, "remote", "add", "origin", str(remote))
        helpers.git(root, "push", "-q", "origin", "main")
    if git.get("shallow"):
        shallow = root.parent / f"{root.name}-shallow"
        helpers.git(root.parent, "clone", "-q", "--depth", "1", f"file://{root}", str(shallow))
        return Built(shallow, shas, {})
    return Built(root, shas, {})


def side_files(facts: dict, shas: dict[str, str], evidence: bool = True, history: IntentHistory | None = None) -> list[tuple[str, str]]:
    """The files that are no Spec: Intents, a product scope file, release files, postmortems, linked documents, and the evidence. An
    Intent is written as its history holds it now, when there is one."""
    out: list[tuple[str, str]] = []
    intents = dict(facts.get("intents") or {})
    if facts.get("intent"):
        intents.setdefault(facts["intent"].get("id", "INTENT-1"), facts["intent"])
    for intent_id, fields in intents.items():
        if history is not None and intent_id in history.now:
            out.append((f"{INTENTS}{intent_id}.md", history.text(intent_id, shas)))
            continue
        own = {k: v for k, v in fields.items() if k != "placeholder"}
        out.append((f"{INTENTS}{intent_id}.md", front_matter({**BASE_INTENT, "id": intent_id, **named(own, shas)}, INTENT_BODY)))
    scope = facts.get("scope")
    if scope:
        out.append((scope["path"], front_matter({k: v for k, v in scope.items() if k != "path"}, "\n## Objectives\n")))
    for n, release in enumerate(facts.get("releases", []), 1):
        day = release["released_at"][:10]
        name = release.get("file") or f"docs/releases/{release['environment']}-{day}-{n}.md"
        fields = {"type": "release", **{k: v for k, v in release.items() if k != "file"}}
        out.append((name, front_matter(named(fields, shas), "\nRelease notes.\n")))
    for pm in facts.get("postmortems", []):
        out.append((f"docs/postmortems/{pm['id']}.md", front_matter({"type": "postmortem", **pm}, "\nWhat happened.\n")))
    for doc in facts.get("docs", []):
        out.append((doc["path"], front_matter({"type": doc["type"]}, "\n| Id | Accepted | By | Date |\n| --- | --- | --- | --- |\n| A1 |  |  |  |\n")))
    for record in facts.get("records", []):
        out.append((f".git/aidd/records/2026/11/{record['id']}.json", json.dumps(record)))
    ran = facts.get("evidence") if evidence else None
    if ran:
        passed = ran.get("passed", True)
        sha = shas.get(ran["commit"], ran["commit"])
        out.append((".aidd/evidence/evidence.json", json.dumps({"head_sha": sha, "base_sha": sha, "passed": passed, "results": [], "specs": ["SPEC-1"]})))
    return out


def branch(root: Path, facts: dict, commits: list[dict], shas: dict[str, str], history: IntentHistory | None = None) -> None:
    """The branch: each commit made on it, then each Intent's approval that no commit names, then the files of the case, which name
    those commits, then their own commit."""
    for spec in (c for c in commits if c.get("on", "main") != "main"):
        if spec["on"] != "feat":
            helpers.git(root, "checkout", "-q", "-B", spec["on"], "main")
        if "holds" in spec:
            holds(root, spec["holds"], specs_of(facts.get("trunk") or {}) or specs_of(facts), shas)
        commit(root, spec["name"], spec, shas, history)
        if spec["on"] != "feat":
            helpers.git(root, "checkout", "-q", "feat")
    for iid in history.unnamed_approvals() if history else []:
        history.approve(root, iid, shas)
    notes = facts.get("notes", [])
    for spec_id, content in specs_of(facts).items():
        rel, text = spec_file(spec_id, content, shas, notes if spec_id == "SPEC-1" else [])
        write(root, rel, text)
    for rel, text in side_files({k: v for k, v in facts.items() if k != "trunk"}, shas, history=history):
        if not rel.startswith("docs/releases/") or not facts.get("trunk"):
            write(root, rel, text)
    helpers.git(root, "add", "-A")
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "the branch's files"], cwd=root, check=False, capture_output=True)
    for name, held in (facts.get("branches") or {}).items():
        helpers.git(root, "checkout", "-q", "-B", name, "main")
        holds(root, list(held.get("specs", {})), held.get("specs", {}), shas)
        helpers.git(root, "add", "-A")
        helpers.git(root, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", f"{name} holds its Specs")
        helpers.git(root, "checkout", "-q", "feat")
