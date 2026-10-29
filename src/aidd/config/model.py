"""The config as aidd reads it: `Config`, the merged `.aidd/config.yaml` with its effective gates, and the defaults and value sets its keys take."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from aidd.kernel import globs, resources

CONFIG_PATH = ".aidd/config.yaml"
# The config schema as one file, for an editor's YAML language server (`aidd gen-docs` writes it), and the first line of
# the config `aidd init` writes, which names it at this aidd's release: the editor then completes and explains each key.
EDITOR_SCHEMA = "schemas/editor/config.json"
SCHEMA_MODELINE = re.compile(
    r"(?m)^# yaml-language-server: \$schema=https://raw\.githubusercontent\.com/thaithienvanid/aidd/v[^/\s]+/schemas/editor/config\.json$"
)


def schema_modeline(version: str) -> str:
    """The config's first line: where an editor finds the schema of this aidd's release."""
    return f"# yaml-language-server: $schema=https://raw.githubusercontent.com/thaithienvanid/aidd/v{version}/{EDITOR_SCHEMA}"


ROUTE_KEYS = ("standard", "minor", "normal", "major", "emergency")
MAX_RUNBOOK_AGE_DAYS = 180
MAX_REVIEW_AGE_DAYS = 180


# What a user-facing surface looks like in a Task's scope: web and mobile screens, components, and styles.
UI_PATHS = [
    *(f"**/*.{ext}" for ext in ("tsx", "jsx", "vue", "svelte", "astro", "html", "css", "scss", "swift", "dart", "xib", "storyboard")),
    *(f"**/{d}/**" for d in ("components", "pages", "screens", "views", "ui", "web", "frontend", "layouts", "templates")),
    "**/res/layout/**",
]


# What a device or platform matrix looks like in a Task's scope: native iOS and Android code, and a mobile app folder.
DEVICE_PATHS = [
    *(f"**/*.{ext}" for ext in ("swift", "dart", "xib", "storyboard")),
    *(f"{d}/**" for d in ("ios", "android", "mobile")),
    *(f"**/{d}/**" for d in ("ios", "android", "mobile")),
    "**/res/layout/**",
]


def baseline_rule_paths(name: str) -> list[str]:
    """The paths of the baseline's risk rule `name`, read when first asked, never at import."""
    return next((r["paths"] for r in resources.load_json("baseline.json")["risk_rules"] if r["name"] == name), [])


def auth_paths() -> list[str]:
    """What an authentication or authorization change looks like in a Task's scope: the paths of the `baseline:auth` risk rule."""
    return baseline_rule_paths("baseline:auth")


def secrets_paths() -> list[str]:
    """What a change to secrets and cryptography looks like in a Task's scope: the paths of the `baseline:secrets-crypto` risk rule."""
    return baseline_rule_paths("baseline:secrets-crypto")


def deploy_paths() -> list[str]:
    """What a service or deploy change looks like in a Task's scope: the `baseline:iac` and `baseline:containers` paths,
    and a deploy or release file, such as a CI workflow that deploys."""
    named = ["**/deploy/**", "**/deployment/**", "**/*deploy*.*", "**/*release*.yml", "**/*release*.yaml"]
    return baseline_rule_paths("baseline:iac") + baseline_rule_paths("baseline:containers") + named


def major_conditions() -> list[dict]:
    """The reasons a major change has beyond a protected path, as `any_of` condition sets: a dimension that forces major
    or can take a service down, a type that forces major, an irreversible change, or a service or deploy path. A major
    change with none of them, such as an edit to CI checks or to agent instructions, keeps its security review and its
    specialist approval, and gets no tech spec and no runbook."""
    # The gate's routing.MAJOR_DIMENSIONS and MAJOR_TYPES, listed again because the config sits below the gate;
    # tests/test_gate_rules.py (MajorReasonsTests) keeps the lists in step.
    return [
        {"dimensions": ["data", "security", "privacy", "financial", "compliance", "availability"]},
        {"types": ["data", "security", "compliance"]},
        {"reversible": False},
        {"paths": deploy_paths()},
    ]


@functools.cache
def default_docs_required() -> dict[str, dict]:
    """The required-docs matrix, aidd's own (`docs.required` only turns a kind `off`): what `aidd validate` warns about on
    the routes in `routes`, and what `aidd new spec` only suggests on those in `suggest`. Never a gate rule. Testing lives
    in the Spec's Acceptance and the tech spec's Test strategy; a separate test plan only when a QA owner, a regulator, a
    device matrix, or a client's UAT needs one (`any_of`: one of these condition sets must hold). A major change's tech
    spec and runbook follow its reason (`major_conditions`). Built when first asked, so importing the config reads
    no data file."""
    return {
        "tech-spec": {"routes": ["major"], "any_of": major_conditions()},
        "runbook": {"routes": ["major"], "any_of": major_conditions()},
        "threat-model": {
            "routes": ["normal", "major"],
            "any_of": [{"dimensions": ["security", "privacy", "data"]}, {"compliance": True, "paths": auth_paths() + secrets_paths()}],
        },
        "authz": {"routes": ["normal", "major"], "paths": auth_paths(), "any_of": [{"dimensions": ["security"]}, {"compliance": True}]},
        "design-spec": {"routes": ["major"], "suggest": ["normal"], "types": ["feat"], "paths": UI_PATHS},
        "test-plan": {
            "routes": ["major"],
            "suggest": ["normal"],
            "any_of": [
                {"dimensions": ["compliance"]},
                {"types": ["compliance"]},
                {"profiles": ["audited"]},
                {"paths": DEVICE_PATHS},
                {"uat": True},
                {"min_acceptance": 10},
            ],
        },
        "migration": {"routes": ["major"], "suggest": ["normal"], "any_of": [{"dimensions": ["data"]}, {"types": ["data"]}, {"reversible": False}]},
        "analytics": {"routes": ["normal", "major"], "hypothesis": True},
        # Personal data: the compliance doc holds the DPIA (GDPR Art. 35) the compliance analyst plans, and the data map is
        # the living inventory and records of processing (Art. 30) it keeps.
        "compliance": {"routes": ["normal", "major"], "dimensions": ["privacy"]},
        "data-map": {"routes": [], "suggest": ["normal", "major"], "dimensions": ["privacy"]},
    }


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    raw: dict
    profile: str
    gates: dict
    warnings: list[str] = field(default_factory=list)
    # The repository paths of the parent configs it was built from (`extends: [{path: ...}]`, at any depth): an edit
    # of one changes this config as an edit of the config itself does, so the gate protects them alike.
    parent_paths: tuple[str, ...] = ()

    def get(self, *keys, default=None):
        node = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def approvers(self) -> list[str]:
        return self.get("owners", "approvers", default=[])

    @property
    def specialists(self) -> dict[str, list[str]]:
        """Specialist Approver pools by name (`owners.specialists`)."""
        return dict(self.get("owners", "specialists", default={}) or {})

    @property
    def tenant(self) -> str | None:
        """The tenant this repository belongs to (`tenant`), or None: approvals and records are scoped to it."""
        value = self.get("tenant")
        return str(value) if value else None

    @property
    def specs_dir(self) -> str:
        """Where Specs live (`specs_dir`), in its normal form (globs.normal_dir), as `docs_dir`."""
        return globs.normal_dir(str(self.get("specs_dir", default="specs")))

    @property
    def proposals_dir(self) -> str:
        """Where proposals live (`proposals_dir`), in its normal form (globs.normal_dir), as `docs_dir`."""
        return globs.normal_dir(str(self.get("proposals_dir", default="proposals")))

    @property
    def docs_dir(self) -> str:
        """Where `aidd new` writes linked documents (`docs.dir`), in its normal form (globs.normal_dir): `./custom/` is
        `custom`. The config refuses the repository's top. Build a path or a pattern inside it with globs.under."""
        return globs.normal_dir(str(self.get("docs", "dir", default="docs")))

    @property
    def docs_required(self) -> dict[str, dict]:
        """The required-docs matrix as it binds here: aidd's rules, without each kind `docs.required` sets `off`."""
        levels = dict(self.get("docs", "required", default={}) or {})
        return {kind: rule for kind, rule in default_docs_required().items() if levels.get(kind) != "off"}

    @property
    def standards(self) -> list[dict]:
        """`standards`: the team's own rules and its copies of library standards, each a document that agents in the
        named roles read before a step."""
        return list(self.get("standards", default=[]) or [])

    @property
    def standards_policy(self) -> dict:
        """`standards_policy`: the library standards a company requires, excludes, or replaces, and the stacks it allows."""
        return dict(self.get("standards_policy", default={}) or {})

    @property
    def limits(self) -> dict:
        """`limits`, the work-in-progress limits as they bind here: the profile's, tightened by the parents and this
        config. `aidd list`, `aidd doctor`, and autopilot read them; the gate never does."""
        return dict(self.get("limits", default={}) or {})

    @property
    def max_runbook_age_days(self) -> int:
        """`docs.max_runbook_age_days`: how old a runbook's `tested_on` may be before `aidd doctor` warns."""
        return int(self.get("docs", "max_runbook_age_days", default=MAX_RUNBOOK_AGE_DAYS))

    @property
    def max_review_age_days(self) -> int:
        """`docs.max_review_age_days`: how old a living doc's `reviewed_on` may be before `aidd doctor` warns."""
        return int(self.get("docs", "max_review_age_days", default=MAX_REVIEW_AGE_DAYS))

    @property
    def policy_command(self) -> list[str] | None:
        return self.get("policy", "command")

    @property
    def observe_command(self) -> list[str] | None:
        return self.get("observe", "command")


# The session hooks' level (`hooks.level`), weakest first, and the level each profile starts at. A child config
# cannot lower the level its parent sets or starts at (see _merge), the way gates only tighten. At off no session hook
# speaks; the guard is no session hook, and keeps its rules.
HOOK_LEVELS = ("off", "minimal", "balanced", "strict")
HOOK_LEVEL_DEFAULTS = {"solo": "minimal", "team": "balanced", "org": "balanced", "audited": "strict"}

# The parts of aidd a repository can turn off one by one (`components`). The gate is `mode`; the session hooks are
# `hooks.level`; the team is a plugin; the guard follows the Spec steps (off: only its rules on approving, merging, landing,
# publishing, the default branch, and the config).
COMPONENTS = ("spec_steps", "autopilot")
# A part that cannot run without another: autopilot runs the loop's Spec steps.
COMPONENT_NEEDS = {"autopilot": "spec_steps"}
# The profiles whose guard blocks, rather than allows, when it cannot decide (guard/repo_config.fails_closed, and the
# shell fallbacks of setup/hook_wiring.fail_closed_test): each whose mode enforces, as schemas/profiles.json says, since
# a config only tightens its profile. An organization sets the same with AIDD_HOOK_FAIL_CLOSED=1.
FAIL_CLOSED_PROFILES = ("org", "audited")
# The top-level `mode` that does the same: a repository whose config sets `mode: enforce` also blocks when its guard
# cannot run. Every harness reads this one rule, from the config's own lines (guard/repo_config._FAIL_CLOSED_LINE).
FAIL_CLOSED_MODES = ("enforce",)


def component_on(raw: dict, name: str) -> bool:
    """Whether `components.<name>` leaves that part on (the default), and every part it needs is on too."""
    if (raw.get("components") or {}).get(name) is False:
        return False
    need = COMPONENT_NEEDS.get(name)
    return component_on(raw, need) if need else True


# `agents.delegate`, weakest first, and the mode each profile starts at: whether the main session hands its
# edits of repository content to an aidd-team role (guard.delegate_check). A child config cannot loosen a parent's mode.
DELEGATE_MODES = ("never", "auto", "always")
DELEGATE_DEFAULTS = {"solo": "auto", "team": "auto", "org": "auto", "audited": "always"}


def delegate_mode(raw: dict) -> str:
    """never, auto, or always: `agents.delegate`, or the profile's default (DELEGATE_DEFAULTS)."""
    mode = (raw.get("agents") or {}).get("delegate")
    return mode if mode in DELEGATE_MODES else DELEGATE_DEFAULTS.get(str(raw.get("profile")), "auto")


# `agents.helpers`, looser first: whether a helper (a subagent that is not an aidd-team role) may write where enforce
# mode holds edits. In advisory mode every subagent writes. A child config cannot loosen a parent's value.
HELPER_MODES = ("write", "read")


def helpers_mode(raw: dict) -> str:
    """read or write: `agents.helpers`, else read."""
    mode = (raw.get("agents") or {}).get("helpers")
    return mode if mode in HELPER_MODES else "read"


# `agents.browser_hosts`: the hostnames, beyond the local ones, a browser tool may open (guard.browser_pages). A name that
# is not an exact lowercase hostname is dropped, so a list the guard cannot read opens nothing. A child config cannot add a
# host to a parent's list.
BROWSER_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?)*$")


def browser_hosts(raw: dict) -> tuple[str, ...]:
    """The hostnames `agents.browser_hosts` lists, each an exact lowercase hostname (not an address, a pattern, or a URL)."""
    listed = (raw.get("agents") or {}).get("browser_hosts")
    if not isinstance(listed, list):
        return ()
    return tuple(h for h in listed if isinstance(h, str) and len(h) <= 253 and BROWSER_HOST.match(h))


def delegate_set(raw: dict) -> bool:
    """Whether a (merged) config sets `agents.delegate` itself, or a parent's value binds it, rather than taking its
    profile's default."""
    return (raw.get("agents") or {}).get("delegate") in DELEGATE_MODES


def hook_level(raw: dict) -> str:
    """The session hooks' level a (merged) config sets, or its profile's default."""
    level = (raw.get("hooks") or {}).get("level")
    return level if level in HOOK_LEVELS else HOOK_LEVEL_DEFAULTS.get(str(raw.get("profile")), "balanced")


def effective_mode(configured: str | None, requested: str | None, *, input_trusted: bool, fallback: str = "enforce") -> str:
    """The mode of the gate (and of the guard): the base branch's config wins; else the CI setting, if the CI setting is
    trusted; else `fallback`, the default of the base config's profile (`baseline.profile_mode`), or enforce.

    GitHub's mode comes from the reusable workflow's input, which runs from the base branch. GitLab's
    comes from a variable anyone allowed to run a pipeline can override, so it may not relax the gate.
    """
    if configured in ("enforce", "advisory"):
        return configured
    if input_trusted and requested in ("enforce", "advisory"):
        return requested
    return fallback if fallback in ("enforce", "advisory") else "enforce"


# The kinds of document a Spec links in `docs` (spec.schema.json#/$defs/doc).
DOC_KINDS = (
    "tech-spec",
    "test-plan",
    "design-spec",
    "adr",
    "threat-model",
    "authz",
    "api",
    "runbook",
    "slo",
    "compliance",
    "analytics",
    "migration",
    "acceptance",
    "data-map",
    "vendors",
    "other",
)


# The specialist pool that reviews each major dimension (and each major type, which shares its name).
POOL_OF = {"data": "data", "security": "security", "privacy": "privacy", "financial": "finance", "compliance": "compliance"}


# What an empty owners.approvers means, said the same way by the generated config, `aidd doctor`, `aidd validate`,
# and the gate (gate/rules/declared.py's gate_config fails config.no_approvers, and an empty pool matches nobody): nothing merges.
EMPTY_APPROVERS = "an empty list means no change can merge: the gate fails closed until you name one"
