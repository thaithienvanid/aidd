"""The prototype tool's opt-in local server: `serve` (`aidd prototype --serve`), so a person opens a design on a real phone.

This file sits beside `prototype.py` and belongs to the same tool, standard library only. It listens only when a person
runs `serve`, on 127.0.0.1 unless they ask for the local network with `--lan`, and stops with Ctrl-C. It answers GET
alone: `/` is the design's page, built again on each request so a reload shows the latest edit, and any other path is a
file inside the design's folder. A path out of the folder, a dot-file, a folder, a link that leaves it, or a missing file
is a 404, and nothing lists a folder. It answers only a request addressed to it by name (the Host header), so a web page
that rebinds a domain to 127.0.0.1 reads nothing. Under `--lan` every path starts with a random token the printed address
carries, so another device on the network can't guess the page. `AIDD_OFFLINE=1` refuses to start it.
"""

from __future__ import annotations

import http.server
import mimetypes
import os
import secrets
import socket
import stat
import urllib.parse
from collections.abc import Callable
from pathlib import Path

LOOPBACK = "127.0.0.1"
ALL_INTERFACES = "0.0.0.0"  # only with --lan, which a person types to reach the page from a phone
DEFAULT_PORT = 8765
# What every answer says: no caching, no sniffing, no referrer, and the page never framed by another site.
_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY"}


def offline_problem() -> str:
    """Why the server will not start, or nothing: `AIDD_OFFLINE=1` stops every listener and call aidd makes on its own."""
    if os.environ.get("AIDD_OFFLINE") == "1":
        return "AIDD_OFFLINE=1 is set, so the prototype server does not start: unset it to serve the page, or open the written page as a file"
    return ""


def file_in(folder: Path, url_path: str) -> Path | None:
    """The regular file `url_path` names inside `folder`, or None: no path out of it, no folder, no link that leaves it."""
    rel = urllib.parse.unquote(urllib.parse.urlsplit(url_path).path)
    parts = [p for p in rel.split("/") if p]
    # A dot-file (.env, .git) is never part of a design, so none is served.
    if not parts or "\x00" in rel or "\\" in rel or any(p.startswith(".") or ":" in p for p in parts):
        return None
    root = folder.resolve()
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root):
        return None
    try:
        return path if stat.S_ISREG(path.stat().st_mode) else None
    except OSError:
        return None


def new_token() -> str:
    """The random first path segment under `--lan`, which only the printed address carries."""
    return secrets.token_urlsafe(16)


def make_server(
    folder: Path, page: Callable[[], str], *, lan: bool = False, port: int = DEFAULT_PORT, token: str = "", hosts: tuple[str, ...] = ()
) -> http.server.ThreadingHTTPServer:
    """A server bound to 127.0.0.1, or to every interface with `lan`, that answers `/` with `page()` and other paths with
    files inside `folder`. With a `token`, every path starts `/<token>/`. It answers only a Host of 127.0.0.1 or localhost,
    or one of `hosts`, each at its port. It is not started: call `serve_forever`."""
    prefix = f"/{token}" if token else ""

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "aidd-prototype"
        sys_version = ""

        def log_message(self, *args: object) -> None:
            pass  # quiet: a person reads the one line the command prints

        def _answer(self, code: int, body: bytes, kind: str) -> None:
            self.send_response(code)
            for key, value in {**_HEADERS, "Content-Type": kind, "Content-Length": str(len(body))}.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            bound = getattr(self.server, "server_port", port)
            names = {f"{h}:{bound}" for h in (LOOPBACK, "localhost", *hosts)}
            if self.headers.get("Host", "").lower() not in names:
                self._answer(421, b"this server answers only its own address", "text/plain; charset=utf-8")
                return
            path = urllib.parse.urlsplit(self.path).path
            if prefix and not (path == prefix or path.startswith(prefix + "/")):
                self._answer(404, b"no such file in the design's folder", "text/plain; charset=utf-8")
                return
            path = path[len(prefix) :] or "/"
            if path == "/":
                try:
                    body = page().encode("utf-8")
                except (OSError, ValueError) as exc:
                    self._answer(500, f"the page could not be built: {exc}".encode(), "text/plain; charset=utf-8")
                    return
                self._answer(200, body, "text/html; charset=utf-8")
                return
            found = file_in(folder, path)
            if found is None:
                self._answer(404, b"no such file in the design's folder", "text/plain; charset=utf-8")
                return
            kind = mimetypes.guess_type(found.name)[0] or "application/octet-stream"
            self._answer(200, found.read_bytes(), kind)

    return http.server.ThreadingHTTPServer((ALL_INTERFACES if lan else LOOPBACK, port), Handler)


def lan_address() -> str:
    """This machine's address on the local network, as a phone would reach it, or 127.0.0.1 when it has none. It opens a UDP
    socket and sends nothing: connect() only picks the interface a route would use."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed: no packet leaves
        return probe.getsockname()[0]
    except OSError:
        return LOOPBACK
    finally:
        probe.close()


def serve(
    folder: Path, page: Callable[[], str], *, lan: bool = False, port: int = DEFAULT_PORT, say: Callable[[str], None] = lambda line: print(line, flush=True)
) -> int:
    """Serve until Ctrl-C. Returns the exit code."""
    if problem := offline_problem():
        say(problem)
        return 2
    if not 0 <= port <= 65535:
        say(f"--port {port} is no port: pick one from 1024 to 65535, or 0 for any free one")
        return 2
    address = lan_address() if lan else LOOPBACK
    token = new_token() if lan else ""
    try:
        server = make_server(folder, page, lan=lan, port=port, token=token, hosts=(address,) if lan else ())
    except OSError as exc:
        say(f"port {port} cannot be used ({exc.strerror or exc}): pick another with --port")
        return 2
    where = f"http://{address}:{server.server_address[1]}/" + (f"{token}/" if token else "")
    reach = "every device on this network can open it" if lan else "only this machine can open it; add --lan to open it on a phone on the same network"
    say(f"serving {where}: {reach}. Reload after an edit. Ctrl-C stops it")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("stopped")
    finally:
        server.server_close()
    return 0
