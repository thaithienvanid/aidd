"""The config as aidd reads it: `Config`, the merged `.aidd/config.yaml` with its effective gates, and the defaults and value sets its keys take."""

from __future__ import annotations

import functools
from dataclasses import dataclass, field

from aidd.kernel import globs, resources

CONFIG_PATH = ".aidd/config.yaml"
ROUTE_KEYS = ("standard", "minor", "normal", "major", "emergency")
RUNBOOK_MAX_AGE_DAYS = 180
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


@functools.cache
def default_docs_required() -> dict[str, dict]:
    """The required-docs matrix by default (`docs.required` replaces a kind's rule): what `aidd validate` warns about on
    the routes in `routes`, and what `aidd new spec` only suggests on those in `suggest`. Never a gate rule. Testing lives
    in the Spec's Acceptance and the tech spec's Test strategy; a separate test plan only when a QA owner, a regulator, a
    device matrix, or a client's UAT needs one (`any_of`: one of these condition sets must hold). Built when first asked,
    so importing the config reads no data file."""
    return {
        "tech-spec": {"routes": ["major"]},
        "runbook": {"routes": ["major"]},
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
        # the living inventory and records of processing (Art. 30) it and the data engineer keep.
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
        """The required-docs matrix: the defaults, with each kind `docs.required` sets replaced."""
        return default_docs_required() | dict(self.get("docs", "required", default={}) or {})

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
    def runbook_max_age_days(self) -> int:
        return int(self.get("runbook_max_age_days", default=RUNBOOK_MAX_AGE_DAYS))

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
# cannot lower the level its parent sets or starts at (see _merge), the way gates only tighten.
HOOK_LEVELS = ("minimal", "balanced", "strict")
HOOK_LEVEL_DEFAULTS = {"solo": "minimal", "team": "balanced", "org": "balanced", "audited": "strict"}
HOOK_SWITCHES = ("session_start", "stop_check", "compact_note", "prompt_hint")

# The parts of aidd a repository can turn off one by one (`components`). The gate is `mode`; the team is a plugin; the
# guard follows the loop (off: only its rules on approving, merging, shipping, the default branch, and the config).
COMPONENTS = ("hooks", "loop", "autopilot")
# A part that cannot run without another: autopilot runs the loop.
COMPONENT_NEEDS = {"autopilot": "loop"}
# The profiles whose guard blocks, rather than allows, when it cannot decide (guard/repo_config.fails_closed, and the
# shell fallbacks of setup/hook_wiring.fail_closed_test). An organization sets the same with AIDD_HOOK_FAIL_CLOSED=1.
FAIL_CLOSED_PROFILES = ("audited",)


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


def delegate_set(raw: dict) -> bool:
    """Whether a (merged) config sets `agents.delegate` itself, or a parent's value binds it, rather than taking its
    profile's default."""
    return (raw.get("agents") or {}).get("delegate") in DELEGATE_MODES


def hook_level(raw: dict) -> str:
    """The session hooks' level a (merged) config sets, or its profile's default."""
    level = (raw.get("hooks") or {}).get("level")
    return level if level in HOOK_LEVELS else HOOK_LEVEL_DEFAULTS.get(str(raw.get("profile")), "balanced")


def effective_mode(configured: str | None, requested: str | None, *, input_trusted: bool) -> str:
    """The gate's mode: the base branch's config wins; else the CI setting, if the CI setting is trusted.

    GitHub's mode comes from the reusable workflow's input, which runs from the base branch. GitLab's
    comes from a variable anyone allowed to run a pipeline can override, so it may not relax the gate.
    """
    if configured in ("enforce", "advisory"):
        return configured
    if input_trusted and requested in ("enforce", "advisory"):
        return requested
    return "enforce"


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
