"""The overfit check: aidd's core names no framework, product, or domain. The opt-in packs and stacks hold them.

aidd never knows what a person builds, so a product's name in the skill, an agent file, a template, a schema, or the code tunes
aidd to one project shape (AGENTS.md, "Generic, for any project"; CONTRIBUTING.md, "Keep aidd generic"). One rule decides, and
every word it reads comes from data the repository already owns:

- A product is a name aidd's knowledge offers or weighs: what a stack adopts, trials, or holds (`project.stack` in stacks/), the
  tool a library standard installs and the alternatives it names (standards/), an option of a pack's open choice, and a
  technology pack's trigger that a stack or the registry also names. An offered name that ends in a format's acronym also goes
  by the rest, so "Tailwind CSS" is also "Tailwind".
- A domain is a law or a sector standard: the name of a registry entry that only business packs cite
  (schemas/industry-standards.json), and its short forms, such as HIPAA in "US health privacy: HIPAA, ..." or KYC and AML in
  "KYC, AML, and sanctions screening".
- A pack's trigger or glossary term alone never bans a word, so a domain's vocabulary, such as "ledger", "SKU", or "VAT", stays
  free (CONTRIBUTING.md: "Never ban a word a domain uses").

A name counts where it reads as a name: in code (a backtick span, a fenced block, a short JSON value, a Python string with no
space, or a YAML or shell line that is no sentence), or in prose when it is capitalized. A capitalized one-word name whose
lowercase form the core's own prose uses, outside code and outside the PLACES files, such as "Go" or "Click", is an ordinary word
when it opens a sentence, so "Go ahead" passes and "a Go service" fails. A lowercase name with a `-`, `/`, `.`, `:`, or digit,
such as dependency-cruiser, cannot be a word, so it counts in prose too.

What the check does not catch, with no dictionary to tell a name from a word (KNOWN_LIMITS holds a seeded case of each):

- A plain lowercase product name in prose, such as "a pytest config", reads the same as "by river", so it passes.
- A lowercase name of four letters or fewer with no mark, such as `go` or `npm`, is too short to tell from a word or a command,
  so the check reads its proper form instead.
- A product name that is also an ordinary word the core's prose never uses, such as Cargo, Unity, or Temporal, fails even where
  it is the word, as in "Cargo ships by river". A name that is also a word fails mid-sentence, as in "Build it with Make".

GENERIC, PLACES, and SKIP are the allowlist, each with its reason, and a test fails on an allowance nothing needs any more.
KNOWN_OVERFIT holds the hits that need a design change, and it only shrinks.
"""

from __future__ import annotations

import functools
import io
import json
import re
import tokenize
import unittest
from collections.abc import Iterator

from helpers import ROOT

from aidd.knowledge import standards as library

# The core: what every adopter gets, whatever they build.
CORE = ("src/aidd/**/*.py", "schemas/**/*.json", ".agents/skills/aidd/**/*", "plugins/aidd-team/agents/*.md", "templates/**/*")
# The opt-in knowledge inside schemas/: the packs and the registry of standards they cite.
NOT_CORE = ("schemas/packs.json", "schemas/industry-standards.json")

# A name the core may use anywhere, because it is aidd's own: its language, its command, and the test report format it reads as
# evidence from any runner. In alphabetical order, ignoring case.
GENERIC: dict[str, str] = {
    "JUnit": "the XML test report format aidd reads as evidence, from any runner",
    "junit": "that format's name, as a runner's flag spells it",
    "Python": "the language aidd itself is written in and runs on",
    "python": "the command that runs aidd itself",
}

# The test runners' JUnit flags, one per ecosystem, as examples of a test command's `report`.
RUNNERS = frozenset({"cargo-nextest", "PHPUnit", "Vitest"})
# A core file that names products for a reason of its own: the closed set of names it may use, or `None` for a file whose job is to
# name every ecosystem a stack covers, and why. In path order.
PLACES: dict[str, tuple[frozenset[str] | None, str]] = {
    ".agents/skills/aidd/assets/DESIGN.md": (frozenset({"Playwright", "Tailwind"}), "examples, marked as examples, of the tools a design build can use"),
    ".agents/skills/aidd/references/example.md": (frozenset({"pytest"}), "the skill's worked example: one made-up project, start to end"),
    ".agents/skills/aidd/references/intents.md": (
        frozenset({"criterion"}),
        "the English word for a measure of success, which is also the name of a Rust benchmark library",
    ),
    ".agents/skills/aidd/references/risk.md": (frozenset({"terraform"}), "an example of a custom action a config adds"),
    ".agents/skills/aidd/references/spec-tests.md": (RUNNERS, "examples of a test command's `report`, one runner per ecosystem"),
    "schemas/common.schema.json": (frozenset({"criterion"}), "the English word for a measure of success, which is also the name of a Rust benchmark library"),
    "schemas/intent.schema.json": (frozenset({"criterion"}), "the English word for a measure of success, which is also the name of a Rust benchmark library"),
    "schemas/languages.json": (None, "the table of languages: a row for each one aidd knows the source files and manifests of"),
    "schemas/lifecycles.json": (frozenset({"criterion"}), "the English word for a measure of success, which is also the name of a Rust benchmark library"),
    "schemas/product-status.schema.json": (
        frozenset({"criterion"}),
        "the English word for a measure of success, which is also the name of a Rust benchmark library",
    ),
    "schemas/status.schema.json": (frozenset({"criterion"}), "the English word for a measure of success, which is also the name of a Rust benchmark library"),
    "schemas/test-runners.json": (
        None,
        "the table of test runners: a row for each one aidd knows by name, with the exits and the related-tests mode its own documentation gives",
    ),
    "src/aidd/config/model.py": (frozenset({"astro"}), "a file extension, in the list of the files a UI is written in"),
    "src/aidd/config/project.py": (frozenset({"PHP"}), "the ISO 4217 currency codes, where PHP is the Philippine peso"),
    "src/aidd/kernel/git.py": (frozenset({"Xcode"}), "why aidd needs a newer git than the one an older macOS toolchain ships"),
    "src/aidd/kernel/secret_patterns.py": (frozenset({"AWS"}), "the key format of a provider whose secrets it detects"),
    "src/aidd/kernel/strict_yaml.py": (frozenset({"C#"}), "an example of a plain YAML value with a `#` in it"),
    "src/aidd/knowledge/command_pins.py": (frozenset({"Go"}), "pins the commands of the library standards' tools"),
    "src/aidd/knowledge/library_checks.py": (
        frozenset({"Go", "TypeScript", "govulncheck", "typescript"}),
        "checks the library standards against their ecosystems",
    ),
    "src/aidd/knowledge/release_feeds.py": (
        frozenset({".NET", "Go", "Maven", "dotnet", "maven"}),
        "reads the package registries the library standards pin versions from",
    ),
    "src/aidd/knowledge/standards.py": (frozenset({"Expo", "Expo (React Native)"}), "an example of the name an open choice's option goes by"),
    "src/aidd/risk/commands.py": (frozenset({"alembic", "prisma"}), "reads the commands of the migration tools the risk rules rate"),
    "src/aidd/risk/harness_rules.py": (frozenset({"Go", "Rust"}), "the languages whose regex engines read the harness rules aidd writes"),
    "src/aidd/setup/config_template.py": (frozenset({"gradle", "maven", "terraform"}), "the config template's test command and paths for each ecosystem"),
    "src/aidd/setup/detection.py": (None, "detects a project's ecosystem from its manifest files, for every ecosystem a stack covers"),
    "src/aidd/setup/manifests.py": (None, "reads each ecosystem's manifest file to find its test command"),
    "src/aidd/views/work_item_detail.py": (frozenset({"Commander"}), "the incident commander, a role in any team, as a field label"),
    "src/aidd/workitems/manifest_sections.py": (frozenset({"turbo", "vitest"}), "reads a package manifest's test script and its runners"),
    "src/aidd/workitems/spec_file.py": (frozenset({"pytest"}), "a pytest node id, one form of test path a Spec's command holds"),
    "templates/github/aidd-security.yml": (None, "the dependency scan, which reads every ecosystem's lockfile"),
}

# Parts of a JSON file in the core whose strings may name products, as JSON paths with `*` for one key, and why. In path order.
REPORT = "examples of a test command's `report`, one runner per ecosystem"
SKIP: dict[str, tuple[tuple[str, ...], str]] = {
    "schemas/common.schema.json": (("/$defs/test_command/properties/report",), REPORT),
    "schemas/config.schema.json": (
        ("/$defs/stack_items", "/properties/standards_policy/properties/replace"),
        "examples of a stack item and a library id, marked `such as`",
    ),
    "schemas/editor/config.json": (
        ("/$defs/common.test_command/properties/report", "/$defs/stack_items", "/properties/standards_policy/properties/replace"),
        "generated from config.schema.json and common.schema.json",
    ),
    "schemas/knowledge.schema.json": (
        ("/$defs/release", "/properties/releases"),
        "the release feeds' format, which names the package registries the library standards pin from",
    ),
    "schemas/risks.json": (
        ("/actions/*/commands", "/actions/*/examples", "/areas/*/paths"),
        "the built-in risk rules, which name each command and path they rate, in every ecosystem",
    ),
    "schemas/roles.json": (
        ("/skills", "/roles/*/extensions", "/roles/*/standards", "/roles/*/toolsets"),
        "the practice skills' knowledge, a role's citations of the registry, and a role's optional third-party tools, each suggested only where its stack or need holds",
    ),
    "schemas/roles.schema.json": (
        ("/properties/domains", "/properties/roles/additionalProperties/properties/extensions"),
        "the format of the packs and of a role's optional tools, with examples from them",
    ),
    "schemas/stack.schema.json": (("/$defs/items",), "the stack format: a stack names the products it adopts"),
    "schemas/standard.schema.json": (
        ("/properties/id", "/properties/lock_command", "/properties/tool"),
        "the library standard format: a standard names its tool, its registry, and its lock command",
    ),
}

# A hit that needs a design change, never a text fix: (path, name), and the change it waits for. It only shrinks.
STORIES = "`aidd work --stories` reads one component catalog's index: move it to the web-front-end pack, or read a format any catalog writes"
TOKENS = "the token mirror writes one CSS framework's and one component library's names: move them into their typescript standards"
KNOWN_OVERFIT: dict[tuple[str, str], str] = {
    ("src/aidd/cli/commands/work.py", "Storybook"): STORIES,
    ("src/aidd/cli/grammar.py", "Storybook"): STORIES,
    ("src/aidd/views/design_tokens.py", "Tailwind"): TOKENS,
    ("src/aidd/views/design_tokens.py", "shadcn/ui"): TOKENS,
}

MARKED = re.compile(r"[-/.:0-9]")  # a lowercase name with one of these cannot be an ordinary word
WORD_NAME = re.compile(r"^[A-Z][a-z]+(?:[A-Z][a-z]+)*$")  # a capitalized word, not an acronym: Go, Kubernetes, AppExchange
ACRONYM = re.compile(r"^[A-Z0-9][A-Za-z0-9-]*[A-Z][A-Za-z0-9-]*$")  # two capitals or more, such as HIPAA, PSD2, or ViDA


def _json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _words(text: str) -> set[str]:
    return set(re.findall(r"(?<![\w-])[\w][\w.+#-]*(?<![.-])", text))


def _aliases(name: str) -> list[str]:
    """A name that ends in a format's acronym also goes by the rest: "Tailwind CSS" is also "Tailwind"."""
    head, _, tail = name.rpartition(" ")
    return [head] if WORD_NAME.match(head) and tail.isupper() and len(tail) >= 2 else []


def _short_forms(name: str) -> list[str]:
    """A registry name's short forms: the name before a colon or a parenthesis when it holds an acronym or a number, a
    parenthesized acronym, a leading acronym, and each acronym listed after a colon."""
    out = []
    lead = re.split(r":| \(|, ", name, maxsplit=1)[0].strip()
    if len(lead.split()) <= 5 and any(ACRONYM.match(w) or w[:1].isdigit() for w in lead.split()):
        out.append(lead)
    out += [m for m in re.findall(r"\(([^(),:\s]+)\)", name) if ACRONYM.match(m) and len(m) >= 3]
    for first in re.split(r",\s*", name):  # a leading list of acronyms: "KYC, AML, and sanctions screening"
        first = first.split()[0] if first.split() else ""
        if not (ACRONYM.match(first) and len(first) >= 3):
            break
        out.append(first)
    if ":" in name:
        out += [w for w in re.split(r",\s*(?:and\s+)?|\s+and\s+", name.split(":", 1)[1]) if ACRONYM.match(w.strip()) and len(w.strip()) >= 3]
    return [s.strip() for s in out]


@functools.cache
def named_things() -> dict[str, str]:
    """Each product or domain name the repository's opt-in data holds, and where it comes from."""
    found: dict[str, str] = {}

    def add(name: object, source: str, *, product: bool = True, alias: bool = True) -> None:
        text = str(name).strip()
        if len(text) < 2 or (not re.search(r"[A-Z]", text) and (" " in text or (len(text) < 5 and not MARKED.search(text)))):
            return
        for each in (text, *(_aliases(text) if product and alias else [])):
            found.setdefault(each, source)

    stack_items: set[str] = set()
    for stack, data in library.stacks().items():
        for items in ((data.get("project") or {}).get("stack") or {}).values():
            stack_items.update(str(i) for i in items)
            for item in items:
                add(item, f"stack {stack}")
    for sid, standard in library.standards_library().items():
        add((standard.meta.get("tool") or {}).get("name", ""), f"standard {sid}")
        for alternative in standard.meta.get("alternatives") or []:
            if re.search(r"[A-Z]", str(alternative)) and len(str(alternative).split()) <= 3:
                add(alternative, f"standard {sid} alternative", alias=False)
    packs = _json("schemas/packs.json")
    registry = _json("schemas/industry-standards.json")
    cited: dict[str, set[str]] = {}
    for pack in packs:
        for ref in pack.get("standards", []):
            cited.setdefault(ref if isinstance(ref, str) else ref["id"], set()).add(pack["type"])
        for choice in pack.get("open_choices", []):
            for option in choice.get("options", []):
                for name in re.split(r"\s*\(|\)\s*", option):
                    if name.strip() and len(name.split()) <= 3 and re.search(r"[A-Z]", name):
                        add(name, f"pack {pack['slug']} option")
    inside = {w for entry in registry.values() for w in _words(" ".join(entry["name"].split()[1:]))}
    for pack in packs:
        for trigger in pack["triggers"] if pack["type"] == "technology" else []:
            if trigger in stack_items or (WORD_NAME.match(trigger) and trigger in inside):
                add(trigger, f"pack {pack['slug']} trigger, named by a stack or the registry")
    others = " ".join(e["name"] for sid, e in registry.items() if cited.get(sid) != {"business"})
    for sid, entry in registry.items():
        if cited.get(sid) == {"business"}:
            for form in _short_forms(entry["name"]):
                if form == entry["name"].split(":")[0].strip() or not re.search(rf"(?<!\w){re.escape(form)}(?!\w)", others):
                    add(form, f"registry {sid}", product=False)
    return found


@functools.cache
def core_lowercase_words() -> frozenset[str]:
    """Every lowercase word the core's own prose uses, outside code and backticks, and outside the files whose job is to name
    products (PLACES): the data that says a name is also an ordinary word."""
    words: set[str] = set()
    for rel in core_files():
        if rel in PLACES:
            continue
        for _, unit, mode in text_units(rel, (ROOT / rel).read_text(encoding="utf-8")):
            if mode == "prose":
                words.update(re.findall(r"(?<![\w-])[a-z][a-z0-9]*(?![\w-])", re.sub(r"`[^`]*`", " ", unit)))
    return frozenset(words)


def ordinary(name: str) -> bool:
    """A capitalized word, such as Go, whose lowercase form the core uses too. An acronym such as HIPAA is never one."""
    return bool(WORD_NAME.match(name)) and name.lower() in core_lowercase_words()


def name_pattern(names) -> re.Pattern[str]:
    """One pattern for every name, longest first, matched whole: no letter, digit, `_`, `-`, `.`, or `#` touches it."""
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w.#-])(?:{alternatives})(?![\w#-]|\.\w)")


def _json_strings(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _json_strings(key, f"{path}/{key}")
            yield from _json_strings(item, f"{path}/{key}")
    elif isinstance(value, list):
        for n, item in enumerate(value):
            yield from _json_strings(item, f"{path}/{n}")


def under(prefix: str, where: str) -> bool:
    """Whether the JSON path `where` is `prefix` or under it; a `*` in `prefix` stands for one key."""
    return bool(re.match("^" + re.escape(prefix).replace(r"\*", "[^/]+") + "(/|$)", where))


def _skipped(rel: str, where: str) -> bool:
    return any(under(prefix, where) for prefix in SKIP.get(rel, ((), ""))[0])


def _sentence(text: str) -> bool:
    """A JSON string reads as prose when it is a sentence: it ends with a stop, or it runs past six words."""
    return " " in text and (text.rstrip().endswith((".", "?", "!")) or len(text.split()) > 6)


def _python_units(text: str) -> Iterator[tuple[str, str, str]]:
    """A Python file's comments and strings, its prose; its names and operators name no product."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        yield from ((str(n), line, "prose") for n, line in enumerate(text.splitlines(), 1))
        return
    middle = getattr(tokenize, "FSTRING_MIDDLE", -1)
    for tok in tokens:
        if tok.type in (tokenize.COMMENT, tokenize.STRING, middle):
            body = tok.string.lstrip("#") if tok.type == tokenize.COMMENT else re.sub(r"^[rbfuRBFU]*('''|\"\"\"|'|\")|('''|\"\"\"|'|\")$", "", tok.string)
            mode = "code" if tok.type != tokenize.COMMENT and body and not re.search(r"\s", body) else "prose"
            for n, line in enumerate(body.splitlines() or [""], tok.start[0]):
                yield str(n), line, mode


def text_units(rel: str, text: str) -> Iterator[tuple[str, str, str]]:
    """(where, text, mode) for each piece of a file, where mode is `prose` or `code`."""
    if rel.endswith(".py"):
        yield from _python_units(text)
        return
    if rel.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            for where, value in _json_strings(data):
                if not _skipped(rel, where):
                    yield where, value, "prose" if _sentence(value) else "code"
            return
    fenced = False
    for n, line in enumerate(text.splitlines(), 1):
        if rel.endswith(".md"):
            if line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
                continue
            yield str(n), line, "code" if fenced else "prose"
        else:
            value = line.split(": ", 1)[1] if ": " in line else ""
            yield str(n), line, "prose" if line.lstrip().startswith(("#", "//", "<!--")) or _sentence(value) else "code"


def _in_backticks(unit: str, pos: int) -> bool:
    return unit.count("`", 0, pos) % 2 == 1


def opens_sentence(unit: str, pos: int) -> bool:
    """Whether the text before `pos` ends a sentence, or holds only markup: a heading, a list mark, a table bar, a quote."""
    before = re.sub(r"\[[ xX]\]", "", unit[:pos]).rstrip(" \t\"'(*_>")
    return not before.strip(" #>|-*0123456789.\t") or before.endswith((".", "!", "?", ":", ";", "|"))


def reads_as_name(name: str, unit: str, pos: int, mode: str) -> bool:
    if mode == "code" or _in_backticks(unit, pos):
        return True
    if name.lower() == name:
        return bool(MARKED.search(name))
    return not (ordinary(name) and opens_sentence(unit, pos))


def hits_in(rel: str, text: str, pattern: re.Pattern[str], *, allow: bool = True) -> list[tuple[str, str]]:
    """(where, name) for each name `text` holds where it reads as a name. With `allow`, GENERIC and PLACES are left out."""
    allowed, _ = PLACES.get(rel, (frozenset(), ""))
    out = []
    for where, unit, mode in text_units(rel, text):
        for m in pattern.finditer(unit):
            name = m.group(0)
            if not reads_as_name(name, unit, m.start(), mode):
                continue
            if allow and (name in GENERIC or allowed is None or name in allowed):
                continue
            out.append((where, name))
    return out


@functools.cache
def core_files() -> tuple[str, ...]:
    seen = {str(p.relative_to(ROOT)) for pattern in CORE for p in ROOT.glob(pattern) if p.is_file()}
    return tuple(sorted(rel for rel in seen if rel not in NOT_CORE and "__pycache__" not in rel and not rel.endswith((".png", ".ico"))))


def core_hits(*, allow: bool = True) -> dict[str, list[tuple[str, str]]]:
    """Each core file's hits, as `hits_in` gives them; KNOWN_OVERFIT's are left out when `allow` holds."""
    pattern = name_pattern(named_things())
    out = {}
    for rel in core_files():
        found = hits_in(rel, (ROOT / rel).read_text(encoding="utf-8"), pattern, allow=allow)
        found = [hit for hit in found if not allow or (rel, hit[1]) not in KNOWN_OVERFIT]
        if found:
            out[rel] = found
    return out


def skipped_hits() -> dict[str, set[str]]:
    """For each SKIP prefix, the names its strings hold where they read as names: what each skip lets through."""
    pattern = name_pattern(named_things())
    out: dict[str, set[str]] = {}
    for rel, (prefixes, _) in SKIP.items():
        for where, value in _json_strings(_json(rel)):
            for prefix in prefixes:
                if under(prefix, where):
                    mode = "prose" if _sentence(value) else "code"
                    out.setdefault(f"{rel} {prefix}", set()).update(
                        m.group(0) for m in pattern.finditer(value) if reads_as_name(m.group(0), value, m.start(), mode)
                    )
    return out


# Seeded cases: (file, text, the names the check finds). The first find a product or a domain; the rest pass. In that order.
SEEDS: dict[str, tuple[str, str, list[str]]] = {
    "a framework in the skill": (".agents/skills/aidd/references/routes.md", "Run the Next.js dev server first.", ["Next.js"]),
    "a platform in a template": ("templates/REVIEW.md", "Deploy it to Kubernetes.", ["Kubernetes"]),
    "a platform that opens a sentence": ("templates/REVIEW.md", "Kubernetes runs each service.", ["Kubernetes"]),
    "a framework that opens a sentence": ("templates/REVIEW.md", "Django settings hold the secret key.", ["Django"]),
    "a standard's alternative": ("templates/REVIEW.md", "Write the handler as a Flask route.", ["Flask"]),
    "a package in the loop": (".agents/skills/aidd/references/graph.md", "Lint with dependency-cruiser.", ["dependency-cruiser"]),
    "a runner in a Python string": ("src/aidd/testing/runner.py", 'RUNNER = "vitest"', ["vitest"]),
    "a tool in a Python string": ("src/aidd/risk/levels.py", 'TOOL = "flyway"', ["flyway"]),
    "a health law in an agent file": ("plugins/aidd-team/agents/developer.md", "Check the HIPAA rule first.", ["HIPAA"]),
    "a payments standard in the code": ("src/aidd/risk/levels.py", "# Card data falls under PCI DSS here.", ["PCI DSS"]),
    "a finance regime": ("templates/REVIEW.md", "Screen each customer under KYC and AML rules.", ["KYC", "AML"]),
    "a product in a schema's text": ("schemas/spec.schema.json", '{"description": "a Flutter widget"}', ["Flutter"]),
    "a language whose name is a word": ("templates/REVIEW.md", "Write it as a Go service.", ["Go"]),
    "a framework by its short name": ("templates/REVIEW.md", "Style it with Tailwind.", ["Tailwind"]),
    "a tool in a command": ("templates/REVIEW.md", "Run `prisma migrate dev` before you push.", ["prisma"]),
    "a domain's vocabulary": (".agents/skills/aidd/references/routes.md", "Add the SKU and its VAT to each invoice line.", []),
    "a ledger and an order": (".agents/skills/aidd/references/routes.md", "Post the refund to the ledger, then close the order.", []),
    "a button's label": ("templates/REVIEW.md", "Click Save to keep the draft.", []),
    "an ordinary word that opens a sentence": ("templates/REVIEW.md", "Go ahead: the next node is yours.", []),
    "an ordinary word that opens a task's prompt": ("templates/evals/tasks/examples.yaml", "    prompt: It fails. Make it pass by fixing calc.py.", []),
    "a name inside a longer word": ("templates/REVIEW.md", "Keep it reactive, never Reactor-bound.", []),
    "aidd's own language": ("src/aidd/kernel/text.py", "# A Python str.casefold folds the case.", []),
    "a word that opens a message": ("src/aidd/workitems/steps.py", 'STEP = "Go on with the next Task."', []),
}
# What the check does not catch, as the module's docstring says: each label says whether the check misses a name or flags a word.
KNOWN_LIMITS: dict[str, tuple[str, str, list[str]]] = {
    "missed: a lowercase product name in prose": (".agents/skills/aidd/assets/spec.md", "# (a Makefile target, a pytest config)", []),
    "flagged: an ordinary word the core's prose never uses, at a sentence start": ("templates/REVIEW.md", "Cargo ships by river.", ["Cargo"]),
    "flagged: another such word": ("templates/REVIEW.md", "Unity of purpose matters.", ["Unity"]),
    "flagged: a name that is also a word, mid-sentence": ("templates/REVIEW.md", "Build it with Make on every push.", ["Make"]),
}


class OverfitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.names = named_things()
        cls.pattern = name_pattern(cls.names)

    def test_the_core_names_no_framework_product_or_domain(self):
        hits = [f"{rel}:{where}: {name}" for rel, found in core_hits().items() for where, name in found]
        self.assertEqual(
            hits,
            [],
            "say it in generic words, or move the text into its pack or stack. A name aidd itself must use goes in PLACES, with its reason",
        )

    def test_the_words_come_from_the_stacks_the_standards_the_choices_and_the_registry(self):
        expected = {
            "Next.js": "stack",
            "Go": "stack",
            "Flutter": "stack",
            "dependency-cruiser": "stack",
            "Tailwind": "stack",
            "Click": "pack apis-and-services option",
            "Kubernetes": "pack cloud-and-infrastructure trigger",
            "HIPAA": "registry",
            "PCI DSS": "registry",
            "IEC 61508": "registry",
            "ViDA": "registry",
        }
        for name, source in expected.items():
            with self.subTest(name):
                self.assertIn(name, self.names)
                self.assertTrue(self.names[name].startswith(source), self.names[name])

    def test_no_pack_trigger_or_term_is_banned_unless_other_data_names_it_too(self):
        """A domain's vocabulary stays free: a pack's trigger or glossary term bans a word only when the registry or a stack names it
        too, or a library standard or an open choice offers it as a product."""
        registry = " ".join(e["name"] for e in _json("schemas/industry-standards.json").values())
        stacks = {str(i) for d in library.stacks().values() for items in ((d.get("project") or {}).get("stack") or {}).values() for i in items}
        for pack in _json("schemas/packs.json"):
            for word in [*pack["triggers"], *(t["term"] for t in pack.get("terms", []))]:
                if word in self.names:
                    with self.subTest(pack=pack["slug"], word=word):
                        named = word in stacks or re.search(rf"(?<!\w){re.escape(word)}(?!\w)", registry)
                        self.assertTrue(named or self.names[word].startswith("standard") or self.names[word].endswith(" option"), self.names[word])

    def test_a_seeded_name_fails_and_a_generic_sentence_passes(self):
        for label, (rel, text, expected) in {**SEEDS, **KNOWN_LIMITS}.items():
            with self.subTest(label):
                self.assertEqual([name for _, name in hits_in(rel, text, self.pattern)], expected)

    def test_each_known_limit_says_what_it_misses_or_flags(self):
        for label, (_, _, expected) in KNOWN_LIMITS.items():
            self.assertTrue(label.startswith(("missed: ", "flagged: ")), label)
            self.assertEqual(label.startswith("flagged: "), bool(expected), label)

    def test_each_allowance_has_a_reason_and_is_still_needed(self):
        raw = core_hits(allow=False)
        used = {name for found in raw.values() for _, name in found}
        for name, reason in GENERIC.items():
            with self.subTest(name):
                self.assertTrue(reason.strip())
                self.assertIn(name, used, f"no core file names {name} any more: remove it from GENERIC")
        for rel, (names, reason) in PLACES.items():
            with self.subTest(rel):
                self.assertTrue(reason.strip())
                there = {name for _, name in raw.get(rel, [])} - set(GENERIC)
                self.assertTrue(there, f"{rel} names nothing it needs an allowance for: remove it from PLACES")
                self.assertEqual(sorted((names or there) - there), [], f"{rel} no longer names these: remove them from PLACES")
        let_through = skipped_hits()
        for rel, (prefixes, reason) in SKIP.items():
            for prefix in prefixes:
                with self.subTest(f"{rel} {prefix}"):
                    self.assertTrue(reason.strip())
                    self.assertTrue(let_through.get(f"{rel} {prefix}"), f"nothing under {prefix} names a product: remove it from SKIP")
        for (rel, name), reason in KNOWN_OVERFIT.items():
            with self.subTest(f"{rel} {name}"):
                self.assertTrue(reason.strip())
                self.assertIn(name, {n for _, n in raw.get(rel, [])}, f"{rel} no longer names {name}: remove it from KNOWN_OVERFIT")

    def test_the_lists_keep_their_order(self):
        self.assertEqual(list(PLACES), sorted(PLACES))
        self.assertEqual(list(SKIP), sorted(SKIP))
        self.assertEqual(list(KNOWN_OVERFIT), sorted(KNOWN_OVERFIT))


if __name__ == "__main__":
    unittest.main()
