"""The command pins: the exact tool versions that packs and practice skills name in their commands, read by one reader and
compared online with each registry's newest release. The registry comes from the command's form. The online comparison
runs on a stubbed registry, never the network."""

from __future__ import annotations

import json
import re
import unittest

from helpers import ROOT

from aidd.kernel import json_schema
from aidd.knowledge import bounded_fetch, command_pins, recheck_report, release_feeds

PYPI = {"tool": "checkov", "registry": "pypi", "version": "3.3.20"}


def pin(tool: str, registry: str, version: str) -> dict:
    return {"tool": tool, "registry": registry, "version": version}


class ReaderTests(unittest.TestCase):
    def test_each_form_reads_as_one_pin_or_none(self):
        osv = "github.com/google/osv-scanner/v2/cmd/osv-scanner"
        cases = {
            "`uvx checkov==3.3.20 -d .`": [PYPI],
            "uvx checkov==3.3.20": [PYPI],
            "(`uvx strictdoc==0.30.1 export .`, failing on a link)": [pin("strictdoc", "pypi", "0.30.1")],
            "`uvx --from datacontract-cli==1.2.2 datacontract test x.yaml`": [pin("datacontract-cli", "pypi", "1.2.2")],
            "uvx --from=datacontract-cli==1.2.2 datacontract": [pin("datacontract-cli", "pypi", "1.2.2")],
            "uvx --python 3.12 checkov==3.3.20": [PYPI],
            "uvx ruff@0.5.0 check": [pin("ruff", "pypi", "0.5.0")],
            "uvx 'mypy[faster-cache]==1.2.3'": [pin("mypy", "pypi", "1.2.3")],
            "uv tool run checkov==3.3.20": [PYPI],
            "pipx run checkov==3.3.20 -d .": [PYPI],
            "`npx @lhci/cli@0.15.1 autorun`": [pin("@lhci/cli", "npm", "0.15.1")],
            "npx --yes web-ext@10.7.0 lint": [pin("web-ext", "npm", "10.7.0")],
            "npx -y knip@6.42.1 --dependencies": [pin("knip", "npm", "6.42.1")],
            "npx -p @graphql-inspector/cli@7.0.0 graphql-inspector diff a b": [pin("@graphql-inspector/cli", "npm", "7.0.0")],
            "npx --package=@asyncapi/cli@6.2.1 asyncapi diff": [pin("@asyncapi/cli", "npm", "6.2.1")],
            "npx -p a@1.0.0 -p b@2.0.0 run": [pin("a", "npm", "1.0.0"), pin("b", "npm", "2.0.0")],
            "npm exec markdownlint-cli2@0.23.3 -- x.md": [pin("markdownlint-cli2", "npm", "0.23.3")],
            "pnpm dlx shadcn@4.22.1 init": [pin("shadcn", "npm", "4.22.1")],
            f"go run {osv}@v2.7.0 scan source .": [pin("github.com/google/osv-scanner/v2", "goproxy", "v2.7.0")],
            "go install golang.org/x/vuln/cmd/govulncheck@v1.1.4": [pin("golang.org/x/vuln", "goproxy", "v1.1.4")],
            "go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12": [pin("github.com/rhysd/actionlint", "goproxy", "v1.7.12")],
            "`stylelint@17.15.0` with `color-no-hex`": [pin("stylelint", "npm", "17.15.0")],
            "the `eslint-plugin-security@4.1.0` plugin": [pin("eslint-plugin-security", "npm", "4.1.0")],
            "the `codespell==2.4.3` plugin": [pin("codespell", "pypi", "2.4.3")],
            # Not pins: no exact version, a placeholder, no command form, or a runner in prose.
            "npx -y @mermaid-js/mermaid-cli -i x.md": [],
            "npx wrangler deploy --dry-run": [],
            "npx tool@latest run": [],
            "uvx pip-audit==<version> -r requirements.txt": [],
            "go run golang.org/x/vuln/cmd/govulncheck@<version> ./...": [],
            "go run example.com/tool@latest": [],
            "uvx --from datacontract-cli datacontract test": [],
            "`oasdiff breaking` (oasdiff v1.32.1) and Pulumi v3.265.0": [],
            "uvx": [],
            "the npx runner, or a `snpx foo@1.2.3` typo": [],
            "write to user@10.example.com or see v2@next": [],
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(command_pins.read_pins(text), want)

    def test_the_go_module_is_found_from_the_package_path(self):
        for path, module in {
            "github.com/google/osv-scanner/v2/cmd/osv-scanner": "github.com/google/osv-scanner/v2",
            "github.com/golangci/golangci-lint/cmd/golangci-lint": "github.com/golangci/golangci-lint",
            "golang.org/x/vuln/cmd/govulncheck": "golang.org/x/vuln",
            "example.com/tool/cmd/tool": "example.com/tool/cmd/tool",
        }.items():
            with self.subTest(path=path):
                self.assertEqual(command_pins._go_module(path), module)


def repo_texts() -> list[tuple[str, str]]:
    """Every text the reader is meant to cover, read here without the reader: the packs' data as JSON text, and each
    practice skill's Markdown."""
    packs = json.loads((ROOT / "schemas" / "packs.json").read_text(encoding="utf-8"))
    texts = [(f"pack {p['slug']}", json.dumps(p, ensure_ascii=False)) for p in packs]
    skills = ROOT / "plugins" / "aidd-team" / "skills"
    return texts + [
        (str(f.relative_to(skills)), f.read_text(encoding="utf-8")) for f in sorted(skills.rglob("*.md")) if f.relative_to(skills).parts[0] != "aidd-team"
    ]


class RepositoryPinTests(unittest.TestCase):
    # Anything shaped `name==1.2.3` or `name@1.2.3`, which a pin is, whatever command it follows.
    SHAPE = re.compile(r"[A-Za-z0-9_./@~-]+?(?:==|@)v?\d+(?:\.\d+)+[\w.+-]*")

    def test_every_pin_in_the_packs_and_skills_is_read(self):
        read = command_pins.pinned_commands()
        self.assertTrue(read)
        missed = []
        for where, text in repo_texts():
            for token in self.SHAPE.findall(text):
                name, _, version = token.rpartition("==" if "==" in token else "@")
                if not any(p["version"] == version and (name == p["tool"] or name.startswith(p["tool"] + "/")) for p in read):
                    missed.append(f"{where}: {token}")
        self.assertEqual(missed, [], "a pin in a form command_pins.read_pins does not read: teach the reader, or write the version another way")

    def test_each_pin_has_a_registry_a_feed_and_the_places_that_name_it(self):
        for p in command_pins.pinned_commands():
            with self.subTest(pin=p["tool"]):
                self.assertIn(p["registry"], {"pypi", "npm", "goproxy"})
                self.assertTrue(p["where"])
                release_feeds.feed_url(p["registry"], p["tool"])

    def test_the_offline_lines_give_the_count_and_each_pin(self):
        lines = command_pins.pinned_command_lines()
        pins = command_pins.pinned_commands()
        self.assertTrue(lines[0].startswith(f"{len(pins)} pinned commands"))
        self.assertEqual(len(lines), len(pins) + 1)
        self.assertTrue(any(line.startswith("- checkov ") and "(PyPI)" in line and "pack cloud-and-infrastructure" in line for line in lines))


class OnlineTests(unittest.TestCase):
    """The comparison with each registry's newest release, on a stubbed registry."""

    @staticmethod
    def fetcher(newest: dict[str, str]):
        """A registry that answers by feed host: `newest` maps a tool name found in the address to its newest release."""

        def get(url: str) -> bounded_fetch.Fetched:
            for tool, version in newest.items():
                if tool in url:
                    body = {"pypi.org": {"info": {"version": version}}, "registry.npmjs.org": {"version": version}, "proxy.golang.org": {"Version": version}}
                    return bounded_fetch.Fetched(200, url, "application/json", json.dumps(next(b for h, b in body.items() if h in url)).encode(), False)
            raise bounded_fetch.FetchError("no route")

        return get

    def rows(self, newest: dict[str, str]) -> dict[str, dict]:
        entries = command_pins.pinned_command_entries()
        return {r["tool"]: r for r in release_feeds.check_releases(entries, fetcher=self.fetcher(newest))}

    def test_a_newer_major_is_flagged_the_way_a_library_standard_is(self):
        rows = self.rows(
            {
                "checkov": "4.0.0",  # a newer major
                "semgrep": "1.181.0",  # the same major
                "zizmor": "2.0.0rc1",  # a pre-release never counts
                "garak": "0.18.0",  # before 1.0, a newer minor is a newer major
                "osv-scanner": "v3.0.0",
                "wrangler": "5.0.0",
            }
        )
        self.assertEqual(rows["checkov"]["status"], "newer_major")
        self.assertEqual(rows["checkov"]["latest"], "4.0.0")
        self.assertIn("pinned at 3.3.20 in pack cloud-and-infrastructure, skill cloud-and-infrastructure", rows["checkov"]["reason"])
        self.assertEqual(rows["semgrep"]["status"], "ok")
        self.assertEqual(rows["zizmor"]["status"], "unreachable")  # the feed names a pre-release only
        self.assertEqual(rows["garak"]["status"], "newer_major")
        self.assertEqual(rows["github.com/google/osv-scanner/v2"]["status"], "newer_major")
        self.assertEqual(rows["wrangler"]["status"], "newer_major")
        self.assertEqual(rows["knip"]["status"], "unreachable")  # no answer to judge

    def test_each_pin_goes_to_the_registry_its_command_form_names(self):
        urls = {e["tool"]: e["url"] for e in command_pins.pinned_command_entries()}
        self.assertEqual(urls["checkov"], "https://pypi.org/pypi/checkov/json")
        self.assertEqual(urls["@lhci/cli"], "https://registry.npmjs.org/@lhci%2Fcli/latest")
        self.assertEqual(urls["github.com/google/osv-scanner/v2"], "https://proxy.golang.org/github.com/google/osv-scanner/v2/@latest")

    def test_the_report_counts_pins_apart_and_the_strict_run_goes_red(self):
        rows = self.rows({"checkov": "4.0.0"})
        counts = {"ok": 0, "moved": 0, "missing": 0, "unreachable": 0}
        result = {"schema_version": "1", "checked": "2026-11-04", "limits": {"timeout_seconds": 1, "max_seconds": 1, "max_bytes": 1, "concurrency": 1}}
        result |= {"counts": counts, "results": [], "releases": list(rows.values())}
        self.assertEqual(json_schema.validate(result, "knowledge.schema.json"), [])
        self.assertEqual(recheck_report.exit_code(result, strict=True), 1)
        text = recheck_report.markdown(result)
        self.assertIn("| newer major | `pin:checkov@3.3.20` | checkov | 3.3.20 | 4.0.0 |", text)
        self.assertRegex(text, rf"{len(rows)} pinned commands on their release feeds: 0 ok, 1 newer major, {len(rows) - 1} unreachable\.")
        self.assertNotIn("library tools on their release feeds", text)


if __name__ == "__main__":
    unittest.main()
