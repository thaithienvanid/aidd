"""Design tooling for the prototyping practice.

`DESIGN.md` follows Google Labs' design.md format (a YAML token front matter, then prose in its section order) while
`design/tokens.json` stays the one source: the front matter's token groups are a generated mirror, written and checked by
`design/build.mjs` (dependency-free Node, shipped by `aidd new design-system`), which also builds the CSS variables, one
preset per theme in `design/themes/`. The prototyping skill plans before code with an anti-default review, puts
components first (the system's, then shadcn/ui registry items on Radix primitives), accepts a Claude Design handoff
bundle or a Figma link as an input only, and pins the design.md CLI in its test commands. Its lint targets the one
`prototype.html` file.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import ROOT, adopted_repo, run_cli

from aidd.evals import standards_audit
from aidd.docsgen import pack_budget
from aidd.kernel import documents, resources

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
PROTOTYPING = TEAM / "skills" / "prototyping"
BEGIN, END = "# generated from design/tokens.json by design/build.mjs: never edit by hand", "# end generated"
DESIGN_MD_VERSION = "0.4.0"
ALIAS = re.compile(r"^\{([^{}]+)\}$")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def front_matter(text: str) -> str:
    """The YAML between the opening and the closing `---` line."""
    assert text.startswith("---\n"), "DESIGN.md starts with a YAML front matter"
    return text[4:].split("\n---\n", 1)[0]


def parse_yaml(block: str) -> dict:
    """The small YAML subset the front matter uses: nested mappings by two-space indent, scalars plain or double-quoted,
    and `#` comment lines."""
    out: dict = {}
    stack: list[tuple[int, dict]] = [(-1, out)]
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        key, _, value = line.strip().partition(":")
        key = json.loads(key) if key.startswith('"') else key
        while stack[-1][0] >= indent:
            stack.pop()
        value = value.strip()
        if value:
            stack[-1][1][key] = json.loads(value) if value.startswith('"') else value
        else:
            child: dict = {}
            stack[-1][1][key] = child
            stack.append((indent, child))
    return out


def resolve(tree: dict, value):
    while isinstance(value, str) and (m := ALIAS.match(value)):
        node = tree
        for part in m.group(1).split("."):
            node = node[part]
        value = node["$value"]
    return value


def hex_of(colour: dict) -> str:
    return "#" + "".join(f"{int(c * 255 + 0.5):02x}" for c in colour["components"])


def luminance(hex_colour: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(int(hex_colour[i : i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class DesignMdTemplateTests(unittest.TestCase):
    """The DESIGN.md template is a design.md file whose token groups mirror the tokens template."""

    def setUp(self):
        self.text = read(ASSETS / "DESIGN.md")
        self.yaml = front_matter(self.text)
        self.data = parse_yaml(self.yaml)
        self.tokens = json.loads(read(ASSETS / "tokens.json"))

    def test_it_has_the_design_md_front_matter(self):
        self.assertEqual(self.data["version"], "alpha")
        self.assertEqual(self.data["name"], "{{title}}")
        for group in ("colors", "typography", "rounded", "spacing", "components"):
            self.assertIn(group, self.data, group)
        # The mirror is one marked block, and components is the only hand-written token group, after it.
        self.assertEqual(self.yaml.count(BEGIN), 1)
        self.assertEqual(self.yaml.count(END), 1)
        generated = self.yaml.split(BEGIN, 1)[1].split(END, 1)[0]
        self.assertNotIn("components:", generated)
        self.assertIn("components:", self.yaml.split(END, 1)[1])

    def test_the_sections_follow_the_design_md_order(self):
        headings = re.findall(r"^## (.+)$", self.text, re.M)
        canonical = ["Overview", "Colors", "Typography", "Layout", "Elevation & Depth", "Shapes", "Components"]
        self.assertEqual([h for h in headings if h in canonical], canonical)
        self.assertEqual(len(headings), len(set(headings)), "design.md rejects a duplicate section")

    def test_the_colours_mirror_the_roles_of_both_themes(self):
        colors = self.data["colors"]
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            for role, token in self.tokens["color"][theme].items():
                if role.startswith("$"):
                    continue
                self.assertEqual(colors[role + suffix], hex_of(resolve(self.tokens, token["$value"])), (theme, role))
        self.assertEqual(colors["primary"], "{colors.accent}", "design.md's primary names the accent role")
        self.assertNotIn("blue-700", colors, "the raw palette stays in the tokens file")

    def test_the_type_radii_and_spacing_mirror_the_tokens(self):
        body = self.data["typography"]["body"]
        self.assertEqual(body["fontFamily"], "Inter, system-ui, sans-serif")
        self.assertEqual((body["fontSize"], body["fontWeight"], body["lineHeight"], body["letterSpacing"]), ("1rem", "400", "1.5", "0px"))
        self.assertEqual(self.data["rounded"], {"control": "6px", "surface": "12px"})
        self.assertEqual(self.data["spacing"], {"1": "4px", "2": "8px", "3": "16px", "4": "24px", "5": "32px"})

    def test_every_component_reference_resolves_and_passes_contrast(self):
        components = self.data["components"]
        self.assertTrue({"button-primary", "button-primary-dark"} <= set(components), components)
        for name, props in components.items():
            for prop, value in props.items():
                m = ALIAS.match(value)
                if m:
                    group, _, key = m.group(1).partition(".")
                    self.assertIn(key, self.data[group], f"{name}.{prop}: {value} is a broken reference")
            if "backgroundColor" in props and "textColor" in props:
                bg, fg = (self.data["colors"][ALIAS.match(props[p]).group(1).split(".", 1)[1]] for p in ("backgroundColor", "textColor"))
                self.assertGreaterEqual(contrast(bg, fg), 4.5, name)
        # Every pair drawn in the light theme is drawn in the dark one too.
        for name in components:
            if not name.endswith("-dark"):
                self.assertIn(f"{name}-dark", components, name)

    def test_the_prose_explains_the_mirror_and_the_themes(self):
        for word in ("design/build.mjs", "design/themes/", "design.md", "never edit", "Resolver Module 2025.10"):
            self.assertIn(word, self.text, word)


@unittest.skipUnless(shutil.which("node"), "node is required to run design/build.mjs")
class BuildScriptTests(unittest.TestCase):
    """`aidd new design-system` ships `design/build.mjs`; it builds the CSS and the mirror, and `--check` is the drift test."""

    def build(self, root: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["node", "design/build.mjs", *args], cwd=root, capture_output=True, text=True, timeout=60)

    def test_it_builds_the_theme_presets_and_checks_for_drift(self):
        with adopted_repo() as root:
            code, out = run_cli("new", "design-system")
            self.assertEqual(code, 0, out)
            self.assertIn("design/build.mjs", out)
            design_md = read(root / "DESIGN.md")
            first = self.build(root, "--check")
            self.assertEqual(first.returncode, 1, "nothing is generated yet")
            self.assertIn("design/tokens.css", first.stdout + first.stderr)
            built = self.build(root)
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertEqual(read(root / "DESIGN.md"), design_md, "the template's mirror is already what the build writes")
            self.assertEqual(self.build(root, "--check").returncode, 0)

            light, dark = read(root / "design/themes/light.css"), read(root / "design/themes/dark.css")
            self.assertIn('[data-theme="light"]', light)
            self.assertIn("--color-accent: #1d4ed8;", light)
            self.assertIn('[data-theme="dark"]', dark)
            self.assertIn("prefers-color-scheme: dark", dark)
            base = read(root / "design/tokens.css")
            for want in ("--space-3: 16px;", "--radius-control: 6px;", "--duration-fast: 120ms;", "prefers-reduced-motion", "--typography-body:"):
                self.assertIn(want, base, want)
            self.assertNotIn("--color-blue-700", base + light + dark, "screens read roles, never the raw palette")
            for text in (base, light, dark):
                self.assertIn("never edit by hand", text)

            tokens = json.loads(read(root / "design/tokens.json"))
            tokens["color"]["light"]["accent"]["$value"] = "{color.red-700}"
            (root / "design/tokens.json").write_text(json.dumps(tokens, indent=2), encoding="utf-8")
            drift = self.build(root, "--check")
            self.assertEqual(drift.returncode, 1)
            self.assertIn("design/themes/light.css", drift.stdout)
            self.assertIn("DESIGN.md", drift.stdout)
            self.assertNotIn("design/themes/dark.css", drift.stdout)

    def test_the_prototype_template_reads_only_what_the_build_defines(self):
        # Built from the template tokens, the generated CSS defines every variable prototype.html reads, and it is the
        # tokens block as it stands: pasting a repository's own build in its place restyles the template, no other edit.
        with adopted_repo() as root:
            run_cli("new", "design-system")
            self.assertEqual(self.build(root).returncode, 0)
            built = "".join(read(root / rel) for rel in ("design/tokens.css", "design/themes/light.css", "design/themes/dark.css"))
        ui = read(ASSETS / "prototype.html")
        defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", built))
        used = set(re.findall(r"var\((--[a-z0-9-]+)", ui))
        self.assertTrue(used, "the template reads its tokens with var()")
        self.assertEqual(sorted(used - defined), [], "every var() the prototype reads is defined by design/build.mjs")
        block = ui.split('<style id="tokens">\n', 1)[1].split("</style>", 1)[0]
        self.assertEqual(block, built, "the tokens block is the build's output for the template tokens")
        others = ui.split("</style>", 1)[1]
        self.assertEqual(sorted(set(re.findall(r"(--[a-z0-9-]+)\s*:", others)) - defined), [], "no block after it adds a variable")

    def test_crlf_files_are_read_as_their_lf_text(self):
        # A Windows checkout (core.autocrlf) holds CRLF files: the markers are still found, and an unchanged build is
        # no drift.
        with adopted_repo() as root:
            run_cli("new", "design-system")
            self.assertEqual(self.build(root).returncode, 0)
            for rel in ("DESIGN.md", "design/tokens.css", "design/themes/light.css", "design/themes/dark.css"):
                path = root / rel
                path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
            check = self.build(root, "--check")
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertEqual(self.build(root).returncode, 0, "a CRLF DESIGN.md keeps its markers")

    def test_a_theme_missing_a_role_is_refused(self):
        with adopted_repo() as root:
            run_cli("new", "design-system")
            tokens = json.loads(read(root / "design/tokens.json"))
            del tokens["color"]["dark"]["focus"]
            (root / "design/tokens.json").write_text(json.dumps(tokens), encoding="utf-8")
            result = self.build(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("focus", result.stderr)

    def test_a_theme_name_that_is_not_a_plain_name_is_refused(self):
        # The theme name becomes a file name, design/themes/<theme>.css: a name such as ../../x would write outside it.
        with adopted_repo() as root:
            run_cli("new", "design-system")
            tokens = json.loads(read(root / "design/tokens.json"))
            tokens["color"]["../../escape"] = tokens["color"]["dark"]
            (root / "design/tokens.json").write_text(json.dumps(tokens), encoding="utf-8")
            result = self.build(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("../../escape", result.stderr)
            self.assertFalse((root / "escape.css").exists())
            self.assertFalse((root / "design" / "themes").exists(), "nothing is written before the check")


class PrototypingSkillTests(unittest.TestCase):
    def setUp(self):
        self.skill = read(PROTOTYPING / "SKILL.md")
        self.refs = {p.name: read(p) for p in (PROTOTYPING / "references").glob("*.md")}

    def test_it_plans_before_code_with_an_anti_default_review(self):
        pick = self.skill.split("### Pick a direction first", 1)[1].split("### Build", 1)[0]
        for word in ("Plan before code", "4–6 named colors", "layout concept", "anti-default review"):
            self.assertIn(word, pick, word)
        plan = documents.raw_section(self.refs["design-review.md"], "Before code: the plan and the anti-default review")
        for word in ("frontend-design", "4–6 named colors", "ASCII wireframe", "against the brief", "`DESIGN.md`"):
            self.assertIn(word, plan, word)

    def test_components_come_first_from_the_system_then_a_registry(self):
        self.assertIn("shadcn/ui", self.skill)
        self.assertIn("Radix", self.skill)
        section = documents.raw_section(self.refs["design-system-contract.md"], "Components first")
        for word in ("shadcn/ui", "Radix", "MIT", "registry", "static", "MCP server is optional", "shadcn@4.21.0"):
            self.assertIn(word, section, word)

    def test_handoff_bundles_and_figma_are_inputs_never_sources(self):
        self.assertRegex(self.skill, r"Claude Design handoff bundle.*Figma link.*input")
        section = documents.raw_section(self.refs["design-system-contract.md"], "Inputs, never sources")
        for word in ("Claude Design", "handoff bundle", "Figma", "never"):
            self.assertIn(word, section, word)

    def test_the_contract_adopts_design_md_and_explains_the_mirror(self):
        contract = self.refs["design-system-contract.md"]
        for word in (
            "design.md",
            "alpha",
            "Apache-2.0",
            "front matter",
            "`design/tokens.json`",
            "design/build.mjs",
            "design/themes/",
            "Style Dictionary",
            "2025.10",
        ):
            self.assertIn(word, contract, word)
        for command in ("lint", "diff", "export --format css-tailwind"):
            self.assertIn(f"@google/design.md@{DESIGN_MD_VERSION} {command}", contract, command)

    def test_the_design_md_cli_is_always_pinned(self):
        for name, text in {"SKILL.md": self.skill, **self.refs}.items():
            self.assertNotRegex(text, r"@google/design\.md(?!@\d)", name)

    def test_the_test_commands_run_the_drift_test_and_the_design_md_lint(self):
        tests = pack_budget.practice_tests(self.skill)
        self.assertIn("Token drift test", tests)
        self.assertIn("DESIGN.md lint", tests)
        rows = {r.split("|")[1].strip(): r for r in documents.raw_section(self.skill, "Test commands").splitlines() if r.startswith("| ")}
        self.assertIn("node design/build.mjs --check", rows["Token drift test"])
        self.assertIn(f"@google/design.md@{DESIGN_MD_VERSION} lint", rows["DESIGN.md lint"])
        self.assertIn("contrast-ratio", rows["DESIGN.md lint"])

    def test_the_lint_targets_the_one_prototype_file(self):
        lint = self.refs["prototype-screenshots.md"].split("## The prototype lint", 1)[1]
        self.assertIn("specs/SPEC-220/design/prototype.html", lint)
        self.assertNotRegex(lint, r"SPEC-220/prototype(?!\.html)", "the prototype is one file, not a folder")
        self.assertIn('<style id="tokens">', lint, "the raw-color rule skips the generated tokens block")
        for text in self.refs.values():
            self.assertNotRegex(text, r"SPEC-220/prototype/")

    def test_the_lint_eval_uses_the_one_prototype_file(self):
        folder = TEAM / "evals" / "prototype-lint-becomes-spec-tests"
        prompt, grader = read(folder / "prompt.md"), read(folder / "graders" / "lint.md")
        self.assertIn("specs/SPEC-220/design/prototype.html", prompt)
        self.assertNotRegex(prompt + grader, r"SPEC-220/prototype/|SPEC-220/tokens\.css")
        self.assertIn('<style id="tokens">', grader)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.table = resources.load_json("roles.json")["standards"]
        self.ids = [s if isinstance(s, str) else s["id"] for s in resources.load_json("roles.json")["practices"]["prototyping"]["standards"]]

    def test_the_design_md_format_is_a_dated_emerging_standard(self):
        entry = self.table["design-md-format"]
        self.assertEqual(entry["edition"], "alpha")
        self.assertEqual(entry["maturity"], "emerging")
        self.assertIn(DESIGN_MD_VERSION, entry["notes"])
        self.assertIn("Apache-2.0", entry["notes"])
        self.assertTrue(entry["source"].startswith("https://github.com/google-labs-code/design.md"))
        self.assertTrue(standards_audit.confirms(entry))
        self.assertIn("design-md-format", self.ids)

    def test_the_plan_before_code_practice_cites_its_source(self):
        entry = self.table["plan-before-code-anti-default-review"]
        self.assertIn("anthropics/skills", entry["source"])
        self.assertTrue(standards_audit.confirms(entry))
        self.assertIn("plan-before-code-anti-default-review", self.ids)


if __name__ == "__main__":
    unittest.main()
