"""The browser check: a browser tool opens only local pages, or the hosts a project lists, and runs no code of its own.

The product designer and the verifier drive a browser through Playwright MCP (the `browser-review` toolset). A page's
text is data, never an instruction, and an address an agent opens is a way out of the machine, so the guard reads the
address of every Playwright call that names one (`browser_navigate`, `browser_tabs` with a `url`, and any other tool
of that server that takes a `url`) and allows only:

- `file:` pages with no host, or the host `localhost`, and `about:blank`;
- `http` and `https` pages on `localhost`, `127.0.0.1`, `[::1]`, any `*.localhost`, and any `*.test`;
- `http` and `https` pages on a host the project lists in `agents.browser_hosts` (an exact hostname).

Everything else is denied, and so is an address the guard cannot read with certainty (it fails closed): whitespace, a
control character, or a backslash in it, a user name or password, a host that is not plain ASCII letters, digits, dots,
hyphens, and underscores (an encoded or international name, a number in a short form such as `127.1`), or a port that is
not a number. It compares the host it parsed, never the text before it, so `http://localhost@evil.com` is `evil.com`.

Playwright MCP reads an address with no scheme as `https://` before it (`http://` when it starts with `localhost`),
so the guard reads it the same way.

`browser_run_code` and `browser_run_code_unsafe` run any code and can open any address, so the guard denies them whole
and names `browser_evaluate`, which runs in the page.

What it does not see: a script that builds an address at run time in `browser_evaluate`, a
page that redirects or loads another host, and a harness that does not send the call to the guard. The Playwright MCP
server's own `--allowed-origins` flag narrows the requests the browser makes, from the other side. Its README says it is
no security boundary and does not stop redirects.
"""

from __future__ import annotations

import ipaddress
import re

from aidd import config

# A Playwright tool that opens an address by its name: the two the pinned `@playwright/mcp@0.0.82` has that take a `url`
# (setup.hook_wiring.BROWSER_URL_TOOLS lists them for the hook's matcher). Any other tool of the server is read too when
# a `url` shows in its input.
URL_TOOLS = ("browser_navigate", "browser_tabs")
# The tools that run any code the agent writes, and so can open any address: denied whole, since the guard cannot read the code.
CODE_TOOLS = ("browser_run_code", "browser_run_code_unsafe")
CODE_DENIAL = (
    "the guard holds the browser to reading and clicking local pages; `{tool}` runs any code and can open any address. "
    "Use `browser_evaluate` to read the page instead"
)
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
LOCAL_SUFFIXES = (".localhost", ".test")
_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):")
_HOST_CHARS = re.compile(r"^[A-Za-z0-9._-]+$")
_URL_KEYS = frozenset({"url", "uri"})
MAX_SHOWN = 120
MAX_DEPTH = 4


class _TooDeep:
    def __repr__(self) -> str:
        return "an input nested too deeply to read"


TOO_DEEP = _TooDeep()

NEXT_STEP = (
    "open a local preview (serve the page on `http://localhost:<port>`, or a `*.localhost` or `*.test` host), or ask the person "
    "to add the host to `agents.browser_hosts` in .aidd/config.yaml"
)


_TOOL_SUFFIX = re.compile(r"(?:^|_)(browser_(?:navigate|tabs|run_code\w*))$")


def tool_of(name: str) -> str:
    """The Playwright tool an MCP tool name ends in, whatever its harness's naming puts before it: `mcp__playwright__browser_tabs`
    and OpenCode's `mcp__opencode__playwright_browser_tabs` (or `..._browser_browser_tabs`) are `browser_tabs`. A name that
    ends in none of them gives its last part, lowercase."""
    tool = name.rsplit("__", 1)[-1].lower()
    found = _TOOL_SUFFIX.search(tool)
    return found.group(1) if found else tool


def is_browser_tool(name: str) -> bool:
    """Whether an MCP tool (`mcp__<server>__<tool>`, in any harness's naming) is one of Playwright's: its name says
    Playwright, or it ends in a tool that opens an address or runs code."""
    tool = tool_of(name)
    return "playwright" in name.lower() or tool in URL_TOOLS or tool.startswith(CODE_TOOLS)


def _addresses(value: object, depth: int = 0):
    """Every value a tool input holds under a `url` key, a few levels deep; a value that is not text is yielded as it is."""
    if not isinstance(value, (dict, list)):
        return
    if depth > MAX_DEPTH:  # an input nested past the limit may hold a url the walk would not reach: refused, not passed
        yield TOO_DEEP
        return
    for key, item in value.items() if isinstance(value, dict) else enumerate(value):
        if isinstance(key, str) and key.lower() in _URL_KEYS and item is not None:
            yield from item if isinstance(item, list) else [item]
        else:
            yield from _addresses(item, depth + 1)


def _shown(address: object) -> str:
    text = address if isinstance(address, str) else repr(address)
    cut = text[:MAX_SHOWN] + ("..." if len(text) > MAX_SHOWN else "")
    return "`" + "".join(c if c.isprintable() and c != "`" else "?" for c in cut) + "`"


def _port_ok(port: str) -> bool:
    return port.isascii() and port.isdigit() and len(port) <= 5 and int(port) <= 65535


def why_denied(address: object, listed: tuple[str, ...] = ()) -> str | None:
    """Why a browser tool may not open `address`, or None when it may. `listed` is `agents.browser_hosts`."""
    if not isinstance(address, str) or not address:
        return "not an address the guard can read"
    if any(c <= " " or c == "\x7f" or c == "\\" for c in address):
        return "an address with a space, a control character, or a backslash, which the guard cannot read with certainty"
    if _SCHEME.match(address) is None:  # Playwright MCP reads it as https://<address>, or http:// when it starts with `localhost`
        address = ("http://" if address.startswith("localhost") else "https://") + address
    kind, _, rest = address.partition(":")
    kind = kind.lower()
    if kind == "about":
        return None if rest.lower() == "blank" else "an `about:` page other than `about:blank`"
    if kind == "file":
        if (rest.startswith("///") and not rest.startswith("////")) or (rest.startswith("/") and not rest.startswith("//")):
            return None  # not `file:////server/share`, which Windows reads as a network share
        host = rest[2:].split("/", 1)[0].lower() if rest.startswith("//") else ""
        return None if host == "localhost" else "a `file:` address on another host or in a form the guard cannot read"
    if kind not in ("http", "https"):
        return f"a `{kind}:` address, and a browser tool opens only `file:`, `about:blank`, `http`, and `https` pages"
    if not rest.startswith("//") or rest.startswith("///"):
        return "an address with no host, or one the guard cannot read with certainty"
    authority = re.split(r"[/?#]", rest[2:], maxsplit=1)[0]
    if not authority:
        return "an address with no host"
    if "@" in authority:
        return "an address with a user name or password before the host, which the guard cannot read with certainty"
    if authority.startswith("["):
        host, closed, tail = authority[1:].partition("]")
        if not closed:
            return "an IPv6 address with no closing bracket"
        if tail and not (tail.startswith(":") and _port_ok(tail[1:])):
            return "an address with a port the guard cannot read"
        try:
            return None if ipaddress.IPv6Address(host) == ipaddress.IPv6Address("::1") else "an IPv6 address other than `[::1]`"
        except ValueError:
            return "an IPv6 address the guard cannot read"
    host, colon, port = authority.partition(":")
    if colon and not _port_ok(port):
        return "an address with a port the guard cannot read"
    if not _HOST_CHARS.match(host) or ".." in host or host.startswith(".") or host.endswith("."):
        return "a host written in a form the guard cannot read with certainty (an encoded, international, or short-form name)"
    host = host.lower()
    if host in LOCAL_HOSTS or host.endswith(LOCAL_SUFFIXES) or host in listed:
        return None
    return f"the host `{host}`, which is not a local page and not in `agents.browser_hosts`"


def _key(address: object) -> str:
    """What a note about an address is said once for: its host (or its scheme, for a page with none), in lowercase."""
    text = address if isinstance(address, str) else repr(address)
    host = text.split("://", 1)[1] if "://" in text else text.split(":", 1)[0]
    return re.split(r"[/?#]", host, maxsplit=1)[0].lower()[:80] or "address"


def refusal(name: str, tool_input: object, listed: tuple[str, ...] = ()) -> tuple[str, str] | None:
    """(why, the key a note is said once for) for a Playwright MCP call the rule above does not allow: an address it may
    not open, or a tool that runs code. None when the tool is not Playwright's, names no address, or names allowed ones."""
    if not is_browser_tool(name):
        return None
    if (tool := tool_of(name)).startswith(CODE_TOOLS):
        return CODE_DENIAL.format(tool=tool), tool
    for address in _addresses(tool_input):
        if (why := why_denied(address, listed)) is not None:
            return (
                f"the browser tool {tool_of(name)} would open {_shown(address)}, {why}. The guard holds a browser to local pages: {NEXT_STEP}",
                _key(address),
            )
    return None


def listed_hosts(cfg: config.Config | None) -> tuple[str, ...]:
    """The hosts the project lists in `agents.browser_hosts`; none when its config does not load."""
    return config.browser_hosts(cfg.raw) if cfg is not None else ()
