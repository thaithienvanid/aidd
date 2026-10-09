"""The project's constraints and rules: `[project]` in .aidd/config.toml.

People set them: a technology radar (`adopt`, `trial`, `hold`), the hosting, a budget, the team's own rules each with
its why (BCP 14 levels), and time-boxed waivers a person approves. Agents read them in Specify and Review, `aidd assess`
and `aidd owners` print the rules that apply to the paths in question, and `aidd validate` checks them. The gate never
reads them: a rule is enforced by its `check`, a command or a `[[tests]]` entry, or by a reviewer.

A parent config that lists `project` in `locks` binds its `[project]`: a child adds rules, raises a rule's level, adds
to the stack lists, and tightens the budget; it never lowers a level, waives a locked rule, adopts what the parent
holds, raises the spend, or moves the hosting.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re

from . import config as cfgmod
from . import globs, resources
from .model import fmt_number, section

LEVELS = ("must", "should", "may")  # strictest first
PAID = ("allowed", "ask", "forbidden")  # loosest first
RINGS = ("adopt", "trial", "hold")
CONTROLS_PACK = "enterprise-controls"
# The targets whose auditors expect separation of duties, which the solo profile waives: `aidd validate` warns.
DUTIES_TARGETS = ("soc2", "iso27001", "pci-dss", "fedramp", "hipaa")
WAIVER_WARNING_DAYS = 14
# `[project.defaults]`: what every product gets unless `off` names it, with the reason.
DEFAULTS = (
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
# The defaults that only a user interface needs: `aidd init` turns them off in a command-line tool or a library.
UI_DEFAULTS = ("dark_mode", "responsive", "perf_budget", "public_page_basics")
NO_UI = "no user interface"
# `aidd init` in a repository that already has code: the structure stays until a person adopts the modular monolith.
EXISTING_STRUCTURE = "an existing structure; an ADR adopts the modular monolith"


# ---- Layering ---------------------------------------------------------------------------------------------------


def merge(parent: dict | None, child: dict, *, locked: bool, where: str, warnings: list[str]) -> dict:
    """A child's `[project]` over its parent's. Unlocked, the child's entries replace the parent's; locked, they may only
    add or tighten, and whatever would loosen is dropped with a warning."""
    out = copy.deepcopy(parent or {})
    for key, value in child.items():
        if key == "rules":
            out[key] = _merge_rules(out.get(key, []), value, locked, where, warnings)
        elif key == "waivers":
            bound = {r["id"] for r in out.get("rules", [])} if locked else set()
            for w in value:
                if w["rule"] in bound:
                    warnings.append(f"{where}: project.waivers of {w['rule']!r} ignored; a parent config locks the rule, so only it may waive it")
            out[key] = list(out.get(key, [])) + [w for w in value if w["rule"] not in bound]
        elif key == "stack":
            out[key] = _merge_stack(out.get(key, {}), value, locked, where, warnings)
        elif key == "budget":
            out[key] = _merge_budget(out.get(key, {}), value, locked, where, warnings)
        elif key == "defaults":
            out[key] = _merge_defaults(out.get(key, {}), value, locked, where, warnings)
        elif key == "compliance":
            out[key] = _merge_compliance(out.get(key, {}), value, locked, where, warnings)
        elif key == "writing":
            out[key] = _merge_writing(out.get(key, {}), value, locked)
        elif key == "hosting" and locked and out.get(key) and value != out[key]:
            warnings.append(f"{where}: project.hosting {value!r} ignored; a parent config sets {out[key]!r}")
        else:
            out[key] = copy.deepcopy(value)
    return out


def _merge_rules(parents: list[dict], children: list[dict], locked: bool, where: str, warnings: list[str]) -> list[dict]:
    """The parent's rules, then the child's. A child rule with a parent's id replaces it, or, when the parent locks
    its rules, may only raise its level. A repeated id inside one file stays repeated, for `aidd validate` to report."""
    out = [dict(r) for r in parents]
    index = {r["id"]: i for i, r in enumerate(parents)}
    for rule in children:
        i = index.get(rule["id"])
        if i is None:
            out.append(dict(rule))
        elif not locked:
            out[i] = dict(rule)
        else:
            mine = out[i]
            if LEVELS.index(rule["level"]) > LEVELS.index(mine["level"]):
                warnings.append(f"{where}: project.rules {rule['id']!r} level {rule['level']!r} ignored; a parent config locks it at {mine['level']!r}")
            else:
                mine["level"] = rule["level"]
            if any(rule.get(k) != mine.get(k) for k in set(rule) | set(mine) if k != "level"):
                warnings.append(f"{where}: project.rules {rule['id']!r} is set by a parent config; a child may only raise its level")
    return out


def _merge_stack(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    """Each list adds the child's items. Unlocked, the child's ring wins for an item both name; locked, an item the
    parent holds stays on hold."""
    out = {ring: list(parent.get(ring, [])) for ring in RINGS if ring in parent or ring in child}
    held = {h.lower() for h in parent.get("hold", [])}
    for ring in RINGS:
        for item in child.get(ring, []):
            if locked and ring != "hold" and item.lower() in held:
                warnings.append(f"{where}: project.stack.{ring} {item!r} ignored; a parent config holds it")
                continue
            if not locked:
                for other in RINGS:
                    if other != ring and other in out:
                        out[other] = [x for x in out[other] if x.lower() != item.lower()]
            if item.lower() not in {x.lower() for x in out[ring]}:
                out[ring].append(item)
    return out


def _merge_defaults(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    """The child's `off` replaces the parent's. Locked, the child may only drop keys (turn a default back on): a key
    the parent's `off` lacks is ignored, so a default the parent keeps on stays on."""
    out = copy.deepcopy(parent)
    if "off" not in child:
        return out
    off = dict(child["off"])
    if locked:
        kept = (parent.get("off") or {}).keys()
        for key in [k for k in off if k not in kept]:
            warnings.append(f"{where}: project.defaults.off.{key} ignored; a parent config keeps it on")
            del off[key]
    out["off"] = off
    return out


def _merge_budget(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    out = dict(parent)
    for key, value in child.items():
        cur = parent.get(key)
        if locked and cur is not None and value != cur:
            looser = (key == "new_paid_service" and PAID.index(value) < PAID.index(cur)) or (key == "max_infra_per_month" and value > cur) or key == "currency"
            if looser:
                warnings.append(f"{where}: project.budget.{key}={value!r} ignored; a parent config sets {cur!r}")
                continue
        out[key] = value
    return out


def _merge_compliance(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    """The child's targets replace the parent's; locked, they join them."""
    out = dict(parent)
    if "targets" in child:
        out["targets"] = list(dict.fromkeys([*(parent.get("targets") or []), *child["targets"]])) if locked else list(child["targets"])
    return out


def _merge_writing(parent: dict, child: dict, locked: bool) -> dict:
    """The child's `ste_100` kinds replace the parent's; locked, they join them."""
    out = dict(parent)
    if "ste_100" in child:
        out["ste_100"] = list(dict.fromkeys([*(parent.get("ste_100") or []), *child["ste_100"]])) if locked else list(child["ste_100"])
    return out


def compliance(cfg: cfgmod.Config | None) -> dict:
    """The project's compliance stance, the one place that decides it: on when `[project.compliance]` names a target
    (`source` targets) or the profile is regulated (`source` profile), else off. When it is on, the enterprise-controls
    pack applies, the security docs are asked for on security and auth paths, and `aidd init` writes the security CI."""
    c = (cfg.get("project", "compliance", default={}) if cfg else {}) or {}
    targets = list(c.get("targets") or [])
    source = "targets" if targets else "profile" if cfg is not None and cfg.profile == "regulated" else "off"
    return {"on": source != "off", "targets": targets, "source": source}


# ---- Checks ------------------------------------------------------------------------------------------------------


def _date(value: object) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def is_agent(identity: str, bots: set[str] | frozenset[str] = frozenset()) -> bool:
    """An agent (`agent:<name>`, tenant-qualified or not) or a bot account, which never approves a waiver."""
    s = identity.strip().lower()
    bare = s.split(":", 1)[1] if ":" in s and not s.startswith(("agent:", "email:")) else s
    return bare.startswith("agent:") or cfgmod.is_bot(bare) or bare.lstrip("@") in bots


def findings(cfg: cfgmod.Config, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for `aidd validate`: a repeated rule id, a waiver of an unknown rule or approved by an agent,
    an expired waiver (a warning in its last 14 days), a rule past its `review_due`, and a target that expects
    separation of duties under the solo profile, which waives it."""
    today = today or dt.date.today()
    p = cfg.get("project") or {}
    errors: list[str] = []
    warnings: list[str] = []
    rules = p.get("rules", [])
    ids = [r["id"] for r in rules]
    for rid in dict.fromkeys(i for i in ids if ids.count(i) > 1):
        errors.append(f"project.rules: id {rid!r} names {ids.count(rid)} rules; a rule's id is stable and unique")
    for r in rules:
        if r.get("level") not in LEVELS:
            errors.append(f"project.rules {r['id']!r}: level {r.get('level')!r} is not one of must, should, may")
        due = _date(r.get("review_due"))
        if due and due < today:
            warnings.append(f"project.rules {r['id']!r}: review_due {due} has passed; {r['owner']} reviews the rule and sets a new date, or drops it")
    duties = [t for t in compliance(cfg)["targets"] if t in DUTIES_TARGETS]
    if duties and cfg.profile == "solo":
        warnings.append(
            f"project.compliance targets {', '.join(duties)} under the solo profile. Its auditors expect separation of duties, which solo "
            "waives (one person approves their own work). Move to the team profile with a second approver before the audit"
        )
    bots = {b.lower().lstrip("@") for b in cfg.get("identities", "bots", default=[]) or []}
    for w in p.get("waivers", []):
        rid = w["rule"]
        if rid not in ids:
            errors.append(f"project.waivers: the waiver of {rid!r} names no rule in project.rules")
        if is_agent(str(w["approved_by"]), bots):
            errors.append(f"project.waivers: the waiver of {rid!r} is approved by {w['approved_by']}, an agent or bot account; a person approves a waiver")
        until = _date(w["until"])
        if until and until < today:
            errors.append(f"project.waivers: the waiver of {rid!r} expired on {until}; meet the rule, or a person approves a new waiver")
        elif until and (until - today).days <= WAIVER_WARNING_DAYS:
            warnings.append(f"project.waivers: the waiver of {rid!r} expires on {until} (in {(until - today).days} days); plan the work or ask for a renewal")
    return errors, warnings


def defaults(cfg: cfgmod.Config | None) -> dict[str, bool]:
    """Each product default, on unless `[project.defaults] off` names it."""
    off = (cfg.get("project", "defaults", "off", default={}) if cfg else {}) or {}
    return {k: k not in off for k in DEFAULTS}


def theme_hint(cfg: cfgmod.Config | None, design_specs: list[tuple[str, str]]) -> list[str]:
    """Hints for `aidd validate`, never a gate rule: each design spec (path, text) whose Screen inventory table names no
    dark theme while `dark_mode` is on (a case-insensitive text match on the table's rows)."""
    if not defaults(cfg)["dark_mode"]:
        return []
    out = []
    for rel, text in design_specs:
        rows = [line for line in section(text, "Screen inventory").splitlines() if line.lstrip().startswith("|")]
        if not any(re.search(r"\bdark\b", line, re.I) for line in rows):
            out.append(
                f"the design spec {rel} has no dark column in its Screen inventory and [project.defaults] dark_mode is on. Add a "
                "Theme column, light and dark, for each screen. Or turn dark_mode off in [project.defaults] off, with its reason (a text-match hint)"
            )
    return out


def hold_hint(text: str, data: dict, cfg: cfgmod.Config | None) -> str | None:
    """A hint for `aidd validate`, never a gate rule: the `hold` technologies a Spec's Context or Design names (a
    case-insensitive match on the whole name) when the Spec links no ADR. None when there is nothing to say."""
    hold = (cfg.get("project", "stack", "hold", default=[]) if cfg else []) or []
    if not hold or any(isinstance(d, dict) and d.get("kind") == "adr" for d in data.get("docs") or []):
        return None
    body = section(text, "Context") + "\n" + section(text, "Design")
    named = [h for h in hold if re.search(rf"(?<![\w.-]){re.escape(h)}(?![\w-])", body, re.I)]
    if not named:
        return None
    return (
        f"the Context or Design names {', '.join(named)}, on the [project.stack] hold list, and the Spec links no ADR. Record a "
        "person's decision in one (`aidd new adr <topic> --spec <ID>`), or choose from adopt or trial (a text-match hint)"
    )


# ---- The cost of an infrastructure change ------------------------------------------------------------------------

_IAC_RULE: dict = next((r for r in resources.load_json("baseline.json")["risk_rules"] if r["name"] == "baseline:iac"), {})
# What an infrastructure change looks like in a Task's scope: the paths of the `baseline:iac` risk rule.
IAC_PATHS: list[str] = list(_IAC_RULE.get("paths", []))
_IAC_EXCLUDE: list[str] = list(_IAC_RULE.get("exclude", []))
_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
# The ISO 4217 codes (list one, published 2026-09-17), so a three-letter word before a number ("SLA 99.9") is no money.
_ISO_4217 = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF
    CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD
    MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN
    PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD
    TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD
    XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG
    """.split()
)

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# An amount with its currency, the symbol or ISO 4217 code before it or the code after it.
_CODE = "|".join(sorted(_ISO_4217))
_MONEY = re.compile(rf"(?<![\w.])(?:(?P<pre>[$€£]|(?:{_CODE}))\s?(?P<a1>{_NUMBER})|(?P<a2>{_NUMBER})\s?(?P<post>(?:{_CODE})|[€£$]))(?![\w])")
# A month right after the amount ("a month", "per month", "/month", "/mo", "monthly"), or "monthly" shortly before it.
_MONTH_AFTER = re.compile(r"^\s*(?:(?:a|per|each|every)\s+month\b|/\s*mo(?:nth)?\b|monthly\b)", re.I)
_MONTH_BEFORE = re.compile(r"\bmonthly\b[^\n|.]{0,40}$", re.I)


def monthly_estimates(text: str) -> list[tuple[float, str]]:
    """The monthly amounts `text` states, in order, as (amount, ISO 4217 code): "40 EUR a month", "$120/month", or
    "monthly cost: 75 EUR". A unit price ("0.002 USD per request") is not one."""
    out = []
    for m in _MONEY.finditer(text):
        after, before = text[m.end() : m.end() + 30], text[max(0, m.start() - 50) : m.start()]
        if not (_MONTH_AFTER.search(after) or _MONTH_BEFORE.search(before)):
            continue
        amount = float((m.group("a1") or m.group("a2")).replace(",", ""))
        cur = m.group("pre") or m.group("post")
        out.append((amount, _SYMBOLS.get(cur, cur)))
    return out


def _scale_and_cost(text: str) -> str:
    """The "Scale and cost" rows of a tech spec's tables, without the row's own label."""
    return "\n".join(ln.split("|", 2)[-1] for ln in text.splitlines() if re.match(r"^\s*\|\s*Scale and cost\s*\|", ln, re.I))


def cost_hint(text: str, data: dict, cfg: cfgmod.Config | None, tech_specs: list[tuple[str, str]], tracked: list[str] | None = None) -> str | None:
    """A hint for `aidd validate`, never a gate rule: a Spec whose Task scopes hit the `baseline:iac` paths and whose
    Context and linked tech specs' "Scale and cost" rows state no monthly cost estimate, or whose first estimate in the
    budget's currency is above `[project.budget] max_infra_per_month` (a text match). None when there is nothing to say.
    With `tracked` (the repository's files), a glob or a folder scope also hits through an IaC file it holds."""
    scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]

    def iac(s: str) -> bool:
        paths = (s, globs.sample_path(s))
        return any(globs.match_any(IAC_PATHS, x) for x in paths) and not any(globs.match_any(_IAC_EXCLUDE, x) for x in paths)

    def held(s: str) -> str | None:
        if not (any(c in s for c in "*?") or s.endswith("/")):
            return None
        pattern = s.removeprefix("./") + ("**" if s.endswith("/") else "")
        return next((t for t in tracked or [] if globs.match_any([pattern], t) and iac(t)), None)

    hit = []
    for s in scopes:
        if iac(s):
            hit.append(s)
        elif f := held(s):
            hit.append(f"{s}, holding {f}")
    if not hit:
        return None
    found = monthly_estimates(section(text, "Context")) + [e for _, body in tech_specs for e in monthly_estimates(_scale_and_cost(body))]
    if not found:
        return (
            f"a Task scopes infrastructure code ({', '.join(hit)}), and neither the Context nor a linked tech spec's Scale and cost "
            "row states a monthly cost estimate. State one at today's load and at 10x, per aidd-team:cloud-and-infrastructure. "
            "Write it as, for example, `about 40 EUR a month`, from the provider's calculator, or Infracost where the project uses it "
            "(a text-match hint)"
        )
    budget = (cfg.get("project", "budget", default={}) if cfg else {}) or {}
    most, cur = budget.get("max_infra_per_month"), budget.get("currency")
    amount, unit = next((e for e in found if e[1] == cur), (0.0, cur))
    if most is not None and amount > most:
        return (
            f"the monthly cost estimate {fmt_number(amount)} {unit} is above [project.budget] max_infra_per_month {fmt_number(most)} {cur}. Change the "
            "placement or the sizing, or have a person raise the budget before Spec approval (a text-match hint)"
        )
    return None


# ---- What applies ------------------------------------------------------------------------------------------------


def radar_line(stack: dict | None) -> str:
    """The stack radar in one line."""
    parts = [f"{ring} {', '.join(stack[ring])}" for ring in RINGS if stack and stack.get(ring)]
    return "Stack: " + ("; ".join(parts) if parts else "not set ([project.stack] in .aidd/config.toml)")


def _waiver(rule_id: str, waivers: list[dict], today: dt.date) -> dict | None:
    """The waiver in force for a rule: the one lasting longest among those not yet expired."""
    live = [w for w in waivers if w["rule"] == rule_id and (d := _date(w["until"])) and d >= today]
    w = max(live, key=lambda w: str(w["until"]), default=None)
    return {"until": str(w["until"]), "approved_by": w["approved_by"], "reason": w["reason"]} if w else None


def effective(cfg: cfgmod.Config | None, paths: list[str] | None = None, today: dt.date | None = None) -> dict | None:
    """The constraints for `paths` (None: the whole repository): the radar, the hosting, the budget, and the rules whose
    `applies` match one of them (a rule without `applies` always does), must first, each with the waiver in force.
    None when the config has no `[project]`."""
    p = cfg.get("project") if cfg else None
    stance = compliance(cfg)
    if not p and not stance["on"]:
        return None
    p = p or {}
    today = today or dt.date.today()

    def applies(r: dict) -> bool:
        return not r.get("applies") or paths is None or any(globs.match_any(r["applies"], x) for x in paths)

    rules = sorted((r for r in p.get("rules", []) if applies(r)), key=lambda r: LEVELS.index(r["level"]) if r["level"] in LEVELS else len(LEVELS))
    out = {
        "radar": radar_line(p.get("stack")),
        "stack": {ring: list((p.get("stack") or {}).get(ring, [])) for ring in RINGS},
        "hosting": p.get("hosting"),
        "budget": dict(p["budget"]) if p.get("budget") else None,
        "rules": [
            {
                "id": r["id"],
                "level": r["level"],
                "statement": r["statement"],
                "why": r["why"],
                "applies": list(r.get("applies", [])),
                "check": r.get("check"),
                "source": r.get("source"),
                "owner": r["owner"],
                "review_due": r.get("review_due"),
                "waiver": _waiver(r["id"], p.get("waivers", []), today),
            }
            for r in rules
        ],
    }
    if stance["on"]:
        out["compliance"] = {"targets": stance["targets"], "pack": CONTROLS_PACK}
    return out


def compliance_line(c: dict) -> str:
    """The compliance stance in one line, for `aidd assess` and `aidd owners`."""
    why = f"for {', '.join(c['targets'])}" if c.get("targets") else "under the regulated profile"
    return (
        f"Compliance: on, {why}. Load `aidd-team:{c['pack']}` for the control set and its evidence; a threat model and an "
        "authorization matrix are asked for on security and auth paths."
    )


def markdown(p: dict | None) -> list[str]:
    """The constraints as lines: the radar, the hosting and budget, then each rule with its why."""
    if not p:
        return []
    lines = ["## Project constraints", "", p["radar"] + " (a hold needs an ADR and a person's decision)"]
    if p.get("compliance"):
        lines += ["", compliance_line(p["compliance"])]
    b = p.get("budget") or {}
    money = f"infra at most {fmt_number(b['max_infra_per_month'])} {b['currency']} a month" if "max_infra_per_month" in b else ""
    paid = f"a new paid service: {b.get('new_paid_service', 'ask')}" if b else ""
    facts = [x for x in (f"Hosting: {p['hosting']}" if p.get("hosting") else "", f"Budget: {'; '.join(y for y in (money, paid) if y)}" if b else "") if x]
    if facts:
        lines += ["", ". ".join(facts) + "."]
    lines.append("")
    if not p["rules"]:
        return lines + ["No project rule applies to these paths."]
    for r in p["rules"]:
        extra = [f"checked by `{r['check']}`" if r.get("check") else "", f"decided in {r['source']}" if r.get("source") else ""]
        w = r.get("waiver")
        if w:
            extra.append(f"waived until {w['until']} by {w['approved_by']}: {w['reason']}")
        tail = "; ".join(x for x in extra if x)
        lines.append(f"- {r['level'].upper()} {r['id']}: {r['statement']} Why: {r['why']}" + (f" ({tail})" if tail else ""))
    return lines


# ---- aidd init ---------------------------------------------------------------------------------------------------

STACK_COMMENT = (
    "# The project's technology radar, as `aidd init` detected it (docs/ADOPTION.md, Project constraints and rules). It binds\n"
    "# nothing until a person uncomments and edits it: adopt for new work, trial where the design says why, and hold only\n"
    "# with an ADR. Hosting, the budget, and the rules are yours to write: `aidd init` never guesses them.\n"
)


DEFAULTS_COMMENT = (
    "# Product defaults (docs/HOW-TO.md, Product defaults and how to turn one off): every one is on unless `off` names\n"
    "# it here with its reason, and agents build them as aidd-team:product-defaults says, which owns each one and its test.\n"
    "# Uncomment a line and write the reason to turn that default off.\n"
)


def defaults_block(ui: bool = True, existing_code: bool = False) -> str:
    """`[project.defaults.off]` for the starting config: commented, every default on; with `ui` False (a command-line
    tool or a library), the interface defaults written off with the reason; with `existing_code` (a repository that
    already has a structure), `modular_monolith` written off with the reason, so the structure stays as it is."""
    off = {k: NO_UI for k in ([] if ui else UI_DEFAULTS)} | ({"modular_monolith": EXISTING_STRUCTURE} if existing_code else {})
    lines = [DEFAULTS_COMMENT.rstrip("\n"), "[project.defaults.off]" if off else "# [project.defaults.off]"]
    lines += [f"{k} = {json.dumps(off[k])}" if k in off else f'# {k} = "the reason it is off"' for k in DEFAULTS]
    return "\n".join(lines) + "\n"


def repo_block(repo: str) -> str:
    """`[project] repo` for the starting config: the GitHub repository `aidd init` saw as `origin`."""
    return (
        "# The GitHub repository this config belongs to. Autopilot (experimental) trusts the platform's approvals only\n"
        "# from it, as the base branch holds it.\n"
        f"[project]\nrepo = {json.dumps(repo)}\n"
    )


def stack_block(adopt: list[str]) -> str:
    """A commented `[project.stack]` pre-filled with what `aidd init` detected."""
    quoted = ", ".join(json.dumps(x, ensure_ascii=False) for x in adopt)
    return STACK_COMMENT + f"# [project.stack]\n# adopt = [{quoted}]\n# trial = []\n# hold = []\n"


COMPLIANCE_COMMENT = (
    "# What the product must be ready for (docs/ADOPTION.md, Compliance-ready by default). `targets`: soc2, iso27001, gdpr,\n"
    "# hipaa, pci-dss, fedramp, other. Any target, or the regulated profile, turns compliance on: the enterprise-controls\n"
    "# pack's control set, a threat model and an authorization matrix on security and auth paths, security scanning in CI,\n"
    "# and evidence by control with `aidd record export --by-control`. Policies, the ISMS, vendor reviews, training, a\n"
    "# penetration test, and the auditor stay with people outside the team.\n"
)


def compliance_block(targets: list[str] | None = None) -> str:
    """`[project.compliance]` for `aidd init`: commented out unless init was given targets."""
    if not targets:
        return COMPLIANCE_COMMENT + '# [project.compliance]\n# targets = ["soc2", "gdpr"]\n'
    return COMPLIANCE_COMMENT + "[project.compliance]\ntargets = [" + ", ".join(json.dumps(t) for t in targets) + "]\n"
