"""Minimal HTTPS client on urllib. Credentials never follow a redirect; rate limits and 5xx are retried."""

from __future__ import annotations

import functools
import http.client
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from aidd import __version__

USER_AGENT = f"aidd/{__version__}"
RETRIES = 3


def _redacted_url(url: str) -> str:
    """`url` without its userinfo, query, and fragment, which can hold a password or token. Scheme, host, port, and path stay."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "<unparseable URL>"
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc.rpartition("@")[2], parts.path, "", ""))


class HttpError(RuntimeError):
    """A failed request. Its message and `url` are shown to people, so they carry no userinfo, query, or fragment."""

    def __init__(self, status: int, url: str, body: str):
        shown = _redacted_url(url)
        super().__init__(f"HTTP {status} for {shown}: {body[:300]}" if status else f"cannot reach {shown}: {body[:300]}")
        self.status = status
        self.url = shown
        self.body = body


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_scheme = urllib.parse.urlsplit(newurl).scheme.lower()
        if req.type == "https" and new_scheme != "https":
            raise HttpError(code, newurl, f"refusing redirect from https to non-https scheme '{new_scheme}'")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """For fetches whose address was vetted before the request: a redirect could lead anywhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HttpError(code, newurl, "refusing to follow a redirect; use the final URL")


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """An HTTPS connection to one vetted IP address, whatever the host name resolves to by now.

    The certificate is still checked against the host name (SNI and verification use `host`), so pinning the
    address closes DNS rebinding between the address check and the connect without weakening TLS.
    """

    def __init__(self, host: str, *, pinned_ip: str, **kw):
        super().__init__(host, **kw)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout, getattr(self, "source_address", None))
        self.sock = getattr(self, "_context").wrap_socket(sock, server_hostname=self.host)  # noqa: B009  (not in typeshed)
        peer = self.sock.getpeername()[0]
        if peer != self._pinned_ip:  # belt and braces: the socket is where the check said it would be
            self.sock.close()
            raise OSError(f"connected to {peer}, not the vetted address {self._pinned_ip}")


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip: str):
        super().__init__()
        self._pinned_ip = pinned_ip

    def https_open(self, req):
        return self.do_open(functools.partial(_PinnedHTTPSConnection, pinned_ip=self._pinned_ip), req)


def _build_opener(redirects: urllib.request.HTTPRedirectHandler, pinned_ip: str | None = None) -> urllib.request.OpenerDirector:
    opener = urllib.request.OpenerDirector()
    if pinned_ip is None:
        opener.add_handler(urllib.request.ProxyHandler())
        opener.add_handler(urllib.request.HTTPSHandler())
    else:
        opener.add_handler(_PinnedHTTPSHandler(pinned_ip))  # direct: a proxy would pick its own address
    opener.add_handler(urllib.request.HTTPHandler())
    opener.add_handler(urllib.request.UnknownHandler())
    opener.add_handler(redirects)
    opener.add_handler(urllib.request.HTTPDefaultErrorHandler())
    opener.add_handler(urllib.request.HTTPErrorProcessor())
    return opener


@functools.cache
def _shared_opener(follow_redirects: bool) -> urllib.request.OpenerDirector:
    """The opener for every unpinned request, built on first use: building one loads the CA store and reads the
    system's proxies, which a command that makes no request should not wait for. Used explicitly, never installed:
    importing aidd must not change urllib's global opener for the host program."""
    return _build_opener(SafeRedirectHandler() if follow_redirects else NoRedirectHandler())


def _retry_after(headers, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None when the response is final."""
    value = headers.get("retry-after") if headers else None
    if value and value.isdigit():
        return min(float(value), 60.0)
    if headers and headers.get("x-ratelimit-remaining") == "0" and (headers.get("x-ratelimit-reset") or "").isdigit():
        return min(max(float(headers["x-ratelimit-reset"]) - time.time(), 1.0), 60.0)
    return float(2**attempt)


def request(
    method: str,
    url: str,
    *,
    auth: tuple[str, str] | None = None,
    data: object = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
    max_bytes: int,
    follow_redirects: bool = True,
    pinned_ip: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """One HTTP request with retries. `pinned_ip` connects to that address (vetted by the caller) and follows no
    redirect, whatever the host name resolves to at connect time. `max_bytes` is required: no response is read without a
    cap, and one longer than it is an HttpError."""
    if max_bytes < 0:
        raise ValueError(f"max_bytes must not be negative, got {max_bytes}")
    payload = None
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    idempotent = method.upper() in ("GET", "HEAD")
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, data=payload, method=method, headers=req_headers)
        if auth:
            req.add_unredirected_header(auth[0], auth[1])
        try:
            if pinned_ip is not None:
                opener = _build_opener(NoRedirectHandler(), pinned_ip)
            else:
                opener = _shared_opener(follow_redirects)
            with opener.open(req, timeout=timeout_seconds) as resp:
                status = resp.status if hasattr(resp, "status") else resp.code
                body = resp.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise HttpError(status, url, f"response exceeded maximum size of {max_bytes} bytes")
                return status, {k.lower(): v for k, v in resp.headers.items()}, body
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
                hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
                limited = exc.code == 429 or (exc.code == 403 and (hdrs.get("x-ratelimit-remaining") == "0" or "retry-after" in hdrs))
                if attempt < RETRIES and idempotent and (limited or exc.code >= 500):
                    time.sleep(_retry_after(hdrs, attempt) or 1.0)
                    continue
                raise HttpError(exc.code, url, body) from exc
            finally:
                exc.close()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < RETRIES and idempotent:
                time.sleep(float(2**attempt))
                continue
            raise HttpError(0, url, str(getattr(exc, "reason", exc))) from exc
    raise HttpError(0, url, "retries exhausted")


def get_bytes(url: str, *, max_bytes: int, **kw) -> bytes:
    return request("GET", url, max_bytes=max_bytes, **kw)[2]
