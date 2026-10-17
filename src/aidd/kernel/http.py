"""Minimal HTTPS client on urllib. Credentials never follow a redirect; rate limits and 5xx are retried."""

from __future__ import annotations

import functools
import http.client
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from aidd import __version__

USER_AGENT = f"aidd/{__version__}"
RETRIES = 3
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
# The most one API response (a JSON object, or one page of a list) may hold: an API that sends more is refused, never
# read into memory whole.
MAX_API_BYTES = 10 * 1024 * 1024


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} for {url}: {body[:300]}" if status else f"cannot reach {url}: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


class PageLimitError(RuntimeError):
    """`paginate(..., strict=True)` hit a list longer than `limit`; the gate cannot see it all."""


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


# Used explicitly, never installed: importing aidd must not change urllib's global opener for the host program.
_OPENER = _build_opener(SafeRedirectHandler())
_NO_REDIRECT_OPENER = _build_opener(NoRedirectHandler())


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
    max_bytes: int | None = None,
    follow_redirects: bool = True,
    pinned_ip: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """One HTTP request with retries. `pinned_ip` connects to that address (vetted by the caller) and follows no
    redirect, whatever the host name resolves to at connect time."""
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
                opener = _OPENER if follow_redirects else _NO_REDIRECT_OPENER
            with opener.open(req, timeout=timeout_seconds) as resp:
                status = resp.status if hasattr(resp, "status") else resp.code
                body = resp.read() if max_bytes is None else resp.read(max_bytes + 1)
                if max_bytes is not None and len(body) > max_bytes:
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


def get_bytes(url: str, *, max_bytes: int | None = DEFAULT_MAX_BYTES, **kw) -> bytes:
    return request("GET", url, max_bytes=max_bytes, **kw)[2]


def with_params(url: str, params: dict | None) -> str:
    if not params:
        return url
    return url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)


def next_link(headers: dict[str, str], current_url: str | None = None) -> str | None:
    m = re.search(r'<([^>]+)>;\s*rel="next"', headers.get("link", ""))
    link = m.group(1) if m else None
    if not m:
        page = headers.get("x-next-page")
        if page and current_url:
            parts = urllib.parse.urlsplit(current_url)
            query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != "page"]
            query.append(("page", page))
            link = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), parts.fragment))
    if link and current_url:
        cur, nxt = urllib.parse.urlsplit(current_url), urllib.parse.urlsplit(link)
        if (nxt.scheme.lower(), nxt.netloc.lower()) != (cur.scheme.lower(), cur.netloc.lower()):
            return None
    return link


class JsonClient:
    """A JSON API client: auth header, GET, link-header pagination, and downloads. Adapters add their writes."""

    headers: dict[str, str] | None = None

    def __init__(self, token: str, api: str, transport=None):
        self.token = token
        self.api = api.rstrip("/")
        self._request = transport or request

    def _auth(self) -> tuple[str, str] | None:
        return ("Authorization", f"Bearer {self.token}") if self.token else None

    def _url(self, path: str, params: dict | None = None) -> str:
        return path if path.startswith("http") else with_params(self.api + path, params)

    def get(self, path: str, params: dict | None = None):
        _, _, body = self._request("GET", self._url(path, params), auth=self._auth(), headers=self.headers, max_bytes=MAX_API_BYTES)
        return json.loads(body or b"null")

    def paginate(self, path: str, params: dict | None = None, key: str | None = None, limit: int = 3000, strict: bool = False) -> list:
        """Every page up to `limit` items. With strict, more items than that is an error, never a silent cut."""
        url: str | None = with_params(self.api + path, {"per_page": 100, **(params or {})})
        items: list = []
        while url and len(items) < limit:
            _, headers, body = self._request("GET", url, auth=self._auth(), headers=self.headers, max_bytes=MAX_API_BYTES)
            data = json.loads(body or b"[]")
            items.extend(data[key] if key else data)
            url = next_link(headers, url)
        if strict and url:
            raise PageLimitError(f"{path} has more than {limit} items; the gate cannot see them all")
        return items

    def download(self, url: str, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
        """A binary download, refused past `max_bytes`: an artifact is read into memory."""
        return self._request("GET", url, auth=self._auth(), headers=self.headers, timeout_seconds=120, max_bytes=max_bytes)[2]
