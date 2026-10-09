"""Product defaults: what every product gets unless a person turns it off, with the reason, in `[project.defaults] off`.

Light and dark themes, responsive layouts, i18n-ready strings, a performance budget, the public-page basics, API and data
conventions, operability, security headers, legal placeholders, transactional email, and the developer basics. Each is on
unless `off` names it with its reason (the schema refuses an empty one). `aidd init` writes the list (the UI ones off,
with the reason, in a repository with no user interface), `aidd validate` warns about a design spec with no dark column
while dark mode is on, and the packs, the `product-defaults` practice skill, the design templates, and the MVP flow's
Day 0 carry the content.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, git, make_repo, run_cli
from test_design_and_architecture import dtcg_errors, resolve, tokens
from test_linked_docs import spec_text, warnings

from aidd import config, detect, docs, project, repo, resources

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
SKILL = TEAM / "skills" / "product-defaults" / "SKILL.md"
HEAD = 'aidd_version = "1.0.0"\nprofile = "team"\nowners = { approvers = ["@org/leads"] }\n'
KEYS = (
    "dark_mode",
    "responsive",
    "i18n_ready",
    "perf_budget",
    "public_page_basics",
    "api_conventions",
    "data_conventions",
    "operability",
    "security_headers",
    "legal_placeholders",
    "transactional_email",
    "dev_basics",
    "modular_monolith",
)
UI_KEYS = ("dark_mode", "responsive", "perf_budget", "public_page_basics")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load(extra: str = "") -> config.Config:
    return config.load_text(HEAD + extra)


def section(text: str, heading: str) -> str:
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


class SchemaTests(unittest.TestCase):
    def test_off_is_a_closed_map_of_described_keys_to_reasons(self):
        props = resources.load_json("config.schema.json")["properties"]["project"]["properties"]["defaults"]
        self.assertFalse(props["additionalProperties"])
        self.assertEqual(list(props["properties"]), ["off"])
        off = props["properties"]["off"]
        self.assertFalse(off["additionalProperties"])
        self.assertEqual(tuple(off["properties"]), KEYS)
        self.assertEqual(project.DEFAULTS, KEYS)
        for key in KEYS:
            p = off["properties"][key]
            self.assertEqual((p["type"], p["minLength"]), ("string", 1), key)
            self.assertGreater(len(p["description"]), 30, key)

    def test_the_config_accepts_them_and_rejects_a_stranger(self):
        cfg = load('[project.defaults]\noff = { dark_mode = "a print-only report" }\n')
        self.assertFalse(project.defaults(cfg)["dark_mode"])
        self.assertTrue(all(project.defaults(cfg)[k] for k in KEYS if k != "dark_mode"))
        self.assertTrue(all(project.defaults(load()).values()), "every default is on unless off names it")
        self.assertTrue(all(project.defaults(None).values()))
        for bad in (
            '[project.defaults]\noff = { kiosk_mode = "x" }\n',
            '[project.defaults]\noff = { dark_mode = "" }\n',
            "[project.defaults]\ndark_mode = false\n",
            '[project.defaults.reasons]\ndark_mode = "x"\n',
        ):
            with self.assertRaises(config.ConfigError, msg=bad):
                load(bad)


class ValidateTests(unittest.TestCase):
    def test_a_default_off_with_its_reason_is_quiet(self):
        self.assertEqual(project.findings(load('[project.defaults]\noff = { dark_mode = "an e-ink kiosk" }\n')), ([], []))

    def test_aidd_validate_refuses_an_off_without_a_reason(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / ".aidd" / "config.toml"
            cfg.parent.mkdir()
            cfg.write_text(HEAD + '[project.defaults]\noff = { security_headers = "" }\n', encoding="utf-8")
            code, out = run_cli("validate", str(cfg))
            self.assertNotEqual(code, 0, out)
            self.assertIn("security_headers", out)

    def test_a_locked_parent_keeps_a_default_on(self):
        warns: list[str] = []
        merged = project.merge(
            {"defaults": {"off": {"dark_mode": "print"}}},
            {"defaults": {"off": {"dev_basics": "a spike"}}},
            locked=True,
            where="x",
            warnings=warns,
        )
        self.assertEqual(merged["defaults"]["off"], {}, "a child may turn one back on, never turn one off")
        self.assertTrue(any("dev_basics" in w for w in warns), warns)
        merged = project.merge(
            {"defaults": {"off": {"dark_mode": "print", "responsive": "print"}}},
            {"defaults": {"off": {"dark_mode": "kiosk"}}},
            locked=True,
            where="x",
            warnings=[],
        )
        self.assertEqual(merged["defaults"]["off"], {"dark_mode": "kiosk"})
        merged = project.merge(
            {"defaults": {"off": {"dark_mode": "print"}}}, {"defaults": {"off": {"dev_basics": "a spike"}}}, locked=False, where="x", warnings=[]
        )
        self.assertEqual(merged["defaults"]["off"], {"dev_basics": "a spike"})


class InitTests(unittest.TestCase):
    def test_the_block_lists_every_default_commented(self):
        text = repo.config_text("solo", approvers=["@me"])
        block = text.split("# [project.defaults.off]", 1)[1]
        for key in KEYS:
            self.assertRegex(block, rf"(?m)^# {key} = \"", key)
        self.assertIsNone(config.load_text(text).get("project"), "commented: every default is on and nothing is written")

    def test_no_user_interface_turns_the_ui_defaults_off_with_the_reason(self):
        text = repo.config_text("solo", approvers=["@me"], ui=False)
        cfg = config.load_text(text)
        on = project.defaults(cfg)
        for key in KEYS:
            self.assertEqual(on[key], key not in UI_KEYS, key)
        self.assertEqual(cfg.get("project", "defaults", "off"), {k: "no user interface" for k in UI_KEYS})
        self.assertEqual(project.findings(cfg), ([], []))

    def test_uninstall_recognises_a_config_written_with_no_user_interface(self):
        # The UI defaults are written under `[project.defaults.off]`, so uninstall reads them there to rebuild the config
        # init wrote, and removes it as unchanged.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            repo.init(root, profile="team", ci="none", links=[], skill=False, approvers=["@org/leads"], harnesses=[], ui=False)
            config_path = root / ".aidd" / "config.toml"
            self.assertIn("[project.defaults.off]", config_path.read_text(encoding="utf-8"))
            self.assertIn(f"would remove {config_path}", repo.uninstall(root))

    def test_detect_tells_a_cli_or_library_from_a_ui(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text('[project]\nname = "x"\n[project.scripts]\nx = "x:main"\n', encoding="utf-8")
            self.assertTrue(detect.detect(root)["no_ui"])
            (root / "web").mkdir()
            (root / "web" / "App.tsx").write_text("export {}\n", encoding="utf-8")
            self.assertFalse(detect.detect(root)["no_ui"])
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(detect.detect(Path(d))["no_ui"], "an empty repository may still grow a UI")

    def test_aidd_init_writes_the_ui_defaults_off_for_a_cli(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q", "-b", "main")
            (root / "go.mod").write_text("module example.com/tool\n\ngo 1.22\n", encoding="utf-8")
            code, out = run_cli(
                "init", str(root), "--profile", "solo", "--approvers", "email:me@example.com", "--ci", "none", "--harness", "none", "--no-skill"
            )
            self.assertEqual(code, 0, out)
            cfg = config.load_file(".aidd/config.toml", str(root))
            self.assertFalse(project.defaults(cfg)["dark_mode"])
            self.assertEqual(cfg.get("project", "defaults", "off", "responsive"), "no user interface")
            code, out = run_cli("validate", str(root / ".aidd" / "config.toml"))
            self.assertEqual(code, 0, out)


@unittest.skipUnless(shutil.which("git"), "git is required")
class DarkColumnTests(RepoTemplateCase):
    """`aidd validate` warns when a Spec's design spec has no dark column while dark mode is on (a text check)."""

    DS = "docs/specs/SPEC-9/design-spec-cart.md"
    LIGHT_ONLY = "# Design spec\n\nSpec: SPEC-9.\n\n## Screen inventory\n\n| Screen | State | Web 320 |\n| --- | --- | --- |\n| Cart | empty | #empty |\n"
    BOTH = LIGHT_ONLY.replace("| Screen | State | Web 320 |", "| Screen | State | Theme | Web 320 |").replace(
        "| --- | --- | --- |\n| Cart | empty | #empty |", "| --- | --- | --- | --- |\n| Cart | empty | light, dark | #empty |"
    )

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def check(self, body: str, cfg_extra: str = "") -> list[str]:
        if cfg_extra:
            cfg = self.root / ".aidd" / "config.toml"
            cfg.write_text(read(cfg) + cfg_extra, encoding="utf-8")
        (self.root / self.DS).parent.mkdir(parents=True, exist_ok=True)
        (self.root / self.DS).write_text(body, encoding="utf-8")
        p = self.root / "specs" / "SPEC-9.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(spec_text(("design-spec", self.DS)), encoding="utf-8")
        return [w for w in warnings(repo.validate_file(p, "specs/SPEC-9.md")) if "dark" in w]

    def test_no_dark_column_warns(self):
        found = self.check(self.LIGHT_ONLY)
        self.assertEqual(len(found), 1, found)
        self.assertIn(self.DS, found[0])
        self.assertIn("dark_mode", found[0])

    def test_a_dark_column_or_dark_mode_off_is_quiet(self):
        self.assertEqual(self.check(self.BOTH), [])
        self.assertEqual(self.check(self.LIGHT_ONLY, '\n[project.defaults]\noff = { dark_mode = "print only" }\n'), [])

    def test_the_template_passes_its_own_check(self):
        self.assertEqual(self.check(read(ASSETS / "design-spec.md")), [])


def luminance(rgb: list[float]) -> float:
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: list[float], b: list[float]) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class ThemeTests(unittest.TestCase):
    def test_the_tokens_have_a_light_and_a_dark_set_with_the_same_roles(self):
        tree = json.loads(read(ASSETS / "tokens.json"))
        self.assertEqual(dtcg_errors(tree), [])
        light, dark = tree["color"]["light"], tree["color"]["dark"]
        roles = {k for k in light if not k.startswith("$")}
        self.assertEqual(roles, {k for k in dark if not k.startswith("$")})
        self.assertTrue({"surface", "text", "text-muted", "accent", "danger", "focus"} <= roles, roles)
        self.assertIn("Resolver", tree["$description"])

    def test_contrast_holds_in_both_themes(self):
        tree = json.loads(read(ASSETS / "tokens.json"))
        for theme in ("light", "dark"):
            colour = {name.rsplit(".", 1)[1]: resolve(tree, t["$value"])["components"] for name, t, _ in tokens(tree) if name.startswith(f"color.{theme}.")}
            for role, floor in (("text", 4.5), ("text-muted", 4.5), ("danger", 4.5), ("accent", 4.5), ("focus", 3)):
                self.assertGreaterEqual(contrast(colour[role], colour["surface"]), floor, (theme, role))

    def test_design_md_states_the_theme_rules(self):
        text = read(ASSETS / "DESIGN.md")
        themes = section(text, "## Themes")
        for word in ("prefers-color-scheme", "persist", "both themes", "image", "color.light.", "color.dark.", "Resolver Module 2025.10", "dark_mode"):
            self.assertIn(word, themes, word)
        self.assertIn("Dark token", section(text, "## Colors"))

    def test_the_prototype_switches_theme_and_follows_the_system(self):
        ui = read(ASSETS / "prototype.html")
        for testid in (
            "proto-theme-light",
            "proto-theme-dark",
            "proto-theme-system",
            "proto-mode-full",
            "proto-mode-wireframe",
            "proto-state-empty",
            "proto-frame-320",
        ):
            self.assertIn(f'data-testid="{testid}"', ui, testid)
        tokens_css = ui.split('<style id="tokens">', 1)[1].split("</style>", 1)[0]
        self.assertIn("@media (prefers-color-scheme: dark)", tokens_css)
        self.assertIn(':root[data-theme="dark"]', tokens_css)
        self.assertIn(":root:not([data-theme])", tokens_css, "the system scheme applies until a person picks a theme")
        self.assertIn("theme=dark", ui)
        self.assertLess(ui.index('<style id="tokens">'), ui.index('<style id="wireframe">'), "wireframe still wins, after the tokens")
        self.assertNotRegex(ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://", "still one self-contained file")

    def test_the_design_spec_and_the_screenshots_carry_the_theme(self):
        ds = read(ASSETS / "design-spec.md")
        header = next(line for line in section(ds, "## Screen inventory").splitlines() if line.startswith("| Screen"))
        self.assertIn("| Theme |", header)
        self.assertIn("<screen>-<state>-<target>-<theme>.png", ds)
        proto = read(TEAM / "skills" / "prototyping" / "SKILL.md")
        self.assertIn("<screen>-<state>-<target>-<theme>.png", proto)
        self.assertIn("emulateMedia", proto)


class ContentTests(unittest.TestCase):
    """`aidd-team:product-defaults` owns every default, its detail, and its test; a pack keeps one pointer row."""

    def pack(self, slug: str) -> str:
        return read(TEAM / "skills" / slug / "SKILL.md")

    def test_a_pack_points_to_the_defaults_it_builds_in_one_row(self):
        for slug, keys in (
            ("web-front-end", ("dark_mode", "responsive", "i18n_ready", "perf_budget", "public_page_basics", "security_headers")),
            ("apis-and-services", ("api_conventions", "data_conventions", "operability")),
        ):
            rows = [r for r in self.pack(slug).splitlines() if "aidd-team:product-defaults" in r and r.startswith("| Entry")]
            self.assertEqual(len(rows), 1, slug)
            for key in keys:
                self.assertIn(f"`{key}`", rows[0], (slug, key))
            self.assertIn("[project.defaults]", rows[0], slug)

    def test_the_owner_holds_every_default_its_detail_and_its_test(self):
        index = read(SKILL)
        front = docs.practice_front("product-defaults")
        self.assertLessEqual(len(front["description"]), 200)
        refs = sorted((TEAM / "skills" / "product-defaults" / "references").glob("*.md"))
        self.assertEqual([r.name for r in refs], ["services.md", "web.md"])
        for key in KEYS:
            self.assertIn(f"`{key}`", index, key)
        for name in ("api-design", "observability", "secure-coding", "ci-pipeline"):
            self.assertNotIn("## Product defaults", self.pack(name), name)
        text = "\n".join([index, *(read(r) for r in refs)])
        for key in KEYS:
            self.assertIn(f"`{key}`", text, key)
        for word in (
            "prefers-color-scheme",
            "24 by 24",
            "44 by 44 pt",
            "autocomplete",
            "Intl",
            "margin-inline",
            "LCP",
            "INP",
            "CLS",
            "404",
            "500",
            "maintenance",
            "UTC",
            "minor units",
            "UUIDv7",
            "ULID",
            "created_at",
            "deleted_at",
            "cursor",
            "Idempotency-Key",
            "RFC 9457",
            "RateLimit",
            "/healthz",
            "/readyz",
            "trace",
            "SIGTERM",
            "Content-Security-Policy",
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "SameSite",
            "CSRF",
            "privacy policy",
            "person",
            "plain-text",
            "List-Unsubscribe",
            ".editorconfig",
            "pre-commit",
            "Conventional Commits",
            "Dependabot",
            "lhci",
        ):
            self.assertIn(word, text, word)
        self.assertNotRegex(text, r"\]\((?:\.\./){2,}", "the skill links nothing outside its plugin")

    def test_the_roles_that_build_load_it(self):
        roles = resources.roles()["roles"]
        for key in ("developer", "platform-engineer", "product-designer"):
            self.assertIn("product-defaults", roles[key]["practices"], key)


class MvpTests(unittest.TestCase):
    def test_day_0_wires_the_defaults(self):
        text = read(TEAM / "commands" / "mvp.md")
        day0 = text.split("2. **Day 0.**", 1)[1].split("\n3. ", 1)[0]
        for word in ("[project.defaults]", "theme toggle", "security headers", "health endpoint", "error pages", "pre-commit", "formatter", "linter"):
            self.assertIn(word, day0, word)
        flow = next(f for f in resources.roles()["loop"]["flows"] if f["command"] == "mvp")
        self.assertIn("product defaults", flow["stops_at"])


class DocsTests(unittest.TestCase):
    def test_the_docs_name_the_defaults(self):
        self.assertIn("**…turn a product default off?**", read(ROOT / "docs" / "HOW-TO.md"))
        self.assertIn("Product defaults and how to turn one off", read(ROOT / "docs" / "HOW-TO.md"))
        self.assertIn("| Product defaults |", read(ROOT / "docs" / "GLOSSARY.md"))
        self.assertIn("[project.defaults] off", read(ROOT / "docs" / "TROUBLESHOOTING.md"))
        self.assertIn("project.defaults", read(ROOT / "docs" / "CONFIG.md"))
        self.assertRegex(read(ROOT / "CHANGELOG.md"), r"\*\*Product defaults")


if __name__ == "__main__":
    unittest.main()
