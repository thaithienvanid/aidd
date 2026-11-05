"""The config as aidd reads it: `Config`, the merged `.aidd/config.yaml`, and the defaults and value sets its keys take."""

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


# The routes, in order of ceremony: a route is advice about how much of the loop a change needs.
ROUTE_KEYS = ("minor", "normal", "major", "emergency")
ROUTE_RANK = {"minor": 0, "normal": 1, "major": 2, "emergency": 3}
PROFILES = ("solo", "team")
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


def area_paths(name: str) -> list[str]:
    """The paths of the built-in risk area `name` (schemas/risks.json), read when first asked, never at import."""
    area = resources.load_json("risks.json")["areas"].get(name) or {}
    return list(area.get("paths", []))


def deploy_paths() -> list[str]:
    """What a service or deploy change looks like in a Task's scope: the `infra` area's paths, and a deploy or release file."""
    named = ["**/deploy/**", "**/deployment/**", "**/*deploy*.*", "**/*release*.yml", "**/*release*.yaml"]
    return area_paths("infra") + named


def major_conditions() -> list[dict]:
    """The reasons a major change needs a tech spec and a runbook, as `any_of` condition sets: a dimension that can harm
    data, people, money, or a service, a type that forces major, an irreversible change, or a service or deploy path."""
    return [
        {"dimensions": ["data", "security", "privacy", "financial", "compliance", "availability"]},
        {"change_types": ["data", "security", "compliance"]},
        {"reversible": False},
        {"paths": deploy_paths()},
    ]


@functools.cache
def default_docs_required() -> dict[str, dict]:
    """The documents a Spec should link, by route and condition: what `aidd validate` warns about on the routes in
    `routes`, and what `aidd new spec` only suggests on those in `suggest` (`any_of`: one of these condition sets must
    hold). `docs.required` turns a type `off`. Built when first asked, so importing the config reads no data file."""
    auth, secrets = area_paths("auth"), area_paths("secrets")
    return {
        "tech-spec": {"routes": ["major"], "any_of": major_conditions()},
        "runbook": {"routes": ["major"], "any_of": major_conditions()},
        "threat-model": {
            "routes": ["normal", "major"],
            "any_of": [{"dimensions": ["security", "privacy", "data"]}, {"compliance": True, "paths": auth + secrets}],
        },
        "authz": {"routes": ["normal", "major"], "paths": auth, "any_of": [{"dimensions": ["security"]}, {"compliance": True}]},
        "design-spec": {"routes": ["major"], "suggest": ["normal"], "change_types": ["feat"], "paths": UI_PATHS},
        "test-plan": {
            "routes": ["major"],
            "suggest": ["normal"],
            "any_of": [
                {"dimensions": ["compliance"]},
                {"change_types": ["compliance"]},
                {"paths": DEVICE_PATHS},
                {"uat": True},
                {"min_acceptance": 10},
            ],
        },
        "migration": {"routes": ["major"], "suggest": ["normal"], "any_of": [{"dimensions": ["data"]}, {"change_types": ["data"]}, {"reversible": False}]},
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
    warnings: list[str] = field(default_factory=list)
    # The repository paths of the parent configs it was built from (`extends: [{path: ...}]`, at any depth).
    parent_paths: tuple[str, ...] = ()
    # Which `extends` preset each rule in `risks.rules` came from, by its selector: `preset <path or url>`, or `org
    # preset` for AIDD_ORG_PRESET. A rule this file sets itself has no entry, so it reads `config`.
    rule_sources: dict[tuple, str] = field(default_factory=dict)

    def get(self, *keys, default=None):
        node = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    @property
    def approvers(self) -> list[str]:
        """The people the agents ask for a decision, in order (`owners.approvers`); empty means whoever directs them."""
        return list(self.get("owners", "approvers", default=[]))

    @property
    def specialists(self) -> dict[str, list[str]]:
        return dict(self.get("owners", "specialists", default={}))

    @property
    def specs_dir(self) -> str:
        return globs.normal_dir(str(self.get("specs_dir", default="specs")))

    @property
    def proposals_dir(self) -> str:
        return globs.normal_dir(str(self.get("proposals_dir", default="proposals")))

    @property
    def docs_dir(self) -> str:
        return globs.normal_dir(str(self.get("docs", "dir", default="docs")))

    @property
    def docs_required(self) -> dict[str, dict]:
        off = {k for k, v in (self.get("docs", "required", default={}) or {}).items() if v == "off"}
        return {k: v for k, v in default_docs_required().items() if k not in off}

    @property
    def standards(self) -> list[dict]:
        return list(self.get("standards", default=[]))

    @property
    def standards_policy(self) -> dict:
        return dict(self.get("standards_policy", default={}) or {})

    @property
    def max_runbook_age_days(self) -> int:
        return int(self.get("docs", "max_runbook_age_days", default=MAX_RUNBOOK_AGE_DAYS))

    @property
    def max_review_age_days(self) -> int:
        return int(self.get("docs", "max_review_age_days", default=MAX_REVIEW_AGE_DAYS))

    @property
    def tests(self) -> list[dict]:
        return list(self.get("tests", default=[]))


# The types of document a Spec links in `docs` (spec.schema.json#/$defs/doc).
DOC_TYPES = (
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


# The specialist pool that reviews each risk dimension that makes a change major.
POOL_OF = {"data": "data", "security": "security", "privacy": "privacy", "financial": "finance", "compliance": "compliance"}
