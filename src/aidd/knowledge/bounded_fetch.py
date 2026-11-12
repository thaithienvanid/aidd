"""One bounded GET for the knowledge checks: a timeout per request, a time cap for the run, a byte limit per page, a
user agent that names aidd, and https only: the start URL and every redirect hop."""

from __future__ import annotations

import functools
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from aidd import __version__
from aidd.kernel import http

USER_AGENT = f"aidd/{__version__} (standards citation check; +https://github.com/thaithienvanid/aidd)"
TIMEOUT_SECONDS = 15.0
MAX_SECONDS = 600.0
MAX_BYTES = 3_000_000
CONCURRENCY = 2
HOST_DELAY_SECONDS = 1.0
# The schemes a fetch may use, for the start URL and every redirect hop. A test that serves a page from 127.0.0.1 patches it.
SCHEMES = ("https",)


class Fetched:
    def __init__(self, status: int, final_url: str, ctype: str, body: bytes, truncated: bool):
        self.status, self.final_url, self.ctype, self.body, self.truncated = status, final_url, ctype, body, truncated


class FetchError(Exception):
    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.status = status


class _SchemeCheckedRedirects(http.SafeRedirectHandler):
    """Every redirect hop must use an allowed scheme, as the start URL did, so a page never leads the fetch to plain http."""

    def redirect_request(self, req, fp, code, *rest):  # rest: msg, headers, newurl
        newurl = rest[-1]
        scheme = urllib.parse.urlsplit(newurl).scheme.lower()
        if scheme not in SCHEMES:
            raise http.HttpError(code, newurl, f"refusing a redirect to scheme {scheme!r}; only {', '.join(SCHEMES)} is permitted")
        return super().redirect_request(req, fp, code, *rest)


@functools.cache
def _opener() -> urllib.request.OpenerDirector:
    """The opener every fetch uses, built on first use, as kernel/http.py's `_shared_opener` is: building one reads the
    system's proxies, which a command that fetches nothing should not wait for. Used explicitly, never installed. Each
    redirect hop is checked against `SCHEMES`."""
    return urllib.request.build_opener(_SchemeCheckedRedirects())


def fetch(url: str, timeout_seconds: float, max_bytes: int, deadline: float) -> Fetched:
    """One GET, read in chunks until `max_bytes`, the request's timeout, or the run's `deadline` (monotonic)."""
    if urllib.parse.urlsplit(url).scheme.lower() not in SCHEMES:
        raise FetchError(f"refusing {url}: only {', '.join(SCHEMES)} addresses are fetched")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Language": "en",
            "Accept-Encoding": "identity",
        },
    )
    # The GitHub API allows few unauthenticated reads; a token in the environment (read-only is enough) goes to that
    # host alone, and never follows a redirect.
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and urllib.parse.urlsplit(url).netloc.lower() == "api.github.com" and urllib.parse.urlsplit(url).scheme == "https":
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    stop = min(time.monotonic() + timeout_seconds, deadline)
    try:
        with _opener().open(req, timeout=max(0.05, min(timeout_seconds, deadline - time.monotonic()))) as resp:
            body, truncated = b"", False
            while True:
                if time.monotonic() > stop:
                    raise FetchError(f"no complete answer within {timeout_seconds:g} s" if stop < deadline else "the run's time cap was reached")
                chunk = resp.read(65536)
                if not chunk:
                    break
                body += chunk
                if len(body) > max_bytes:
                    body, truncated = body[:max_bytes], True
                    break
            encoding = resp.headers.get("Content-Encoding", "")
            body, clipped = decode_body(body, encoding, max_bytes)
            return Fetched(resp.status, resp.geturl(), resp.headers.get("Content-Type", ""), body, truncated or clipped)
    except urllib.error.HTTPError as exc:
        exc.close()
        raise FetchError(f"HTTP {exc.code}", exc.code) from exc
    except http.HttpError as exc:
        raise FetchError(str(exc), exc.status or None) from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise FetchError(str(getattr(exc, "reason", exc)) or type(exc).__name__) from exc


def decode_body(body: bytes, encoding: str, max_bytes: int) -> tuple[bytes, bool]:
    """The body with its `Content-Encoding` undone, at most `max_bytes` of it, and whether that cut it short. Some hosts
    compress whatever the request asks for, so gzip and deflate (zlib-wrapped or raw) are decoded; the output is
    bounded, so a small compressed body cannot expand past the limit. Another encoding is a FetchError."""
    codings = [c.strip().lower() for c in encoding.split(",") if c.strip() and c.strip().lower() != "identity"]
    for coding in reversed(codings):  # applied in order, so undone last first
        if coding in ("gzip", "x-gzip"):
            tries = [zlib.MAX_WBITS | 16]
        elif coding == "deflate":
            tries = [zlib.MAX_WBITS, -zlib.MAX_WBITS]
        else:
            raise FetchError(f"cannot decode a body sent with Content-Encoding {coding}; check the quote by hand")
        for wbits in tries:
            try:
                d = zlib.decompressobj(wbits)
                out = d.decompress(body, max_bytes + 1)
                break
            except zlib.error:
                continue
        else:
            raise FetchError(f"the {coding} body does not decode")
        if len(out) > max_bytes:
            return out[:max_bytes], True
        body = out
    return body, False


def charset(ctype: str) -> str:
    m = re.search(r"charset=([\w.-]+)", ctype, re.I)
    return m.group(1) if m else "utf-8"
