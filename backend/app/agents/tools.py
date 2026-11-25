"""Agent tools.

Two modes, selected by WARDEN_TOOLS (or per-run):

  real  actual network I/O: search provider chain, HTTP fetch, arithmetic,
        sandboxed file writes, a stateful local CRM
  mock  the original fully-offline synthetic data (deterministic in tests)
  auto  real, with a labelled fallback to mock when the network fails

The mock data (Acme/Globex/Initech) is clearly synthetic and exists so the
platform runs offline. Every tool is wrapped so each invocation is traced
with timing, status and — for web tools — where the data came from.

`web_fetch` is the risky one: an agent that can be told a URL must not be
able to reach localhost, link-local metadata endpoints, or private ranges.
Every hop (including redirects) is resolved and checked against
`assert_public_url`, the body is size-capped, and the scheme is restricted
to http(s).
"""
import ipaddress
import json
import re
import socket
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from langchain_core.tools import tool

from .. import config

USER_AGENT = "WardenAgent/1.1 (+https://github.com/saad-zine/warden)"

# --- mock data (clearly synthetic) ---
CRM = {
    "Acme Corp": {"record_id": "CUST-1042", "name": "Acme Corp",
                  "plan": "Business", "seats": 50, "status": "active"},
    "Globex Ltd": {"record_id": "CUST-2077", "name": "Globex Ltd",
                   "plan": "Enterprise", "seats": 120, "status": "active"},
    "Initech": {"record_id": "CUST-3301", "name": "Initech",
                "plan": "Starter", "seats": 10, "status": "trial"},
}

SEARCH_INDEX = {
    "acme": [
        {"title": "Acme Corp — Pricing", "url": "https://example.com/acme/pricing",
         "snippet": "Acme Corp Business plan: $49 per seat per month, annual billing."},
        {"title": "Acme Corp — Overview", "url": "https://example.com/acme/overview",
         "snippet": "Acme Corp sells workflow software to mid-size companies."},
    ],
    "globex": [
        {"title": "Globex Ltd — Pricing", "url": "https://example.com/globex/pricing",
         "snippet": "Globex Ltd Enterprise plan: $89 per seat per month."},
    ],
    "initech": [
        {"title": "Initech — Pricing", "url": "https://example.com/initech/pricing",
         "snippet": "Initech Starter plan: $19 per seat per month."},
    ],
}

FETCH_INDEX = {
    "https://example.com/acme/pricing": (
        "Acme Corp Business plan costs $49 per seat per month on annual "
        "billing. A $200 setup fee applies once. Support is included."
    ),
    "https://example.com/acme/overview": (
        "Acme Corp is a mid-size workflow software vendor with 400 "
        "employees, founded in 2015."
    ),
    "https://example.com/globex/pricing": (
        "Globex Ltd Enterprise plan costs $89 per seat per month. "
        "Volume discounts start at 100 seats."
    ),
    "https://example.com/initech/pricing": (
        "Initech Starter plan costs $19 per seat per month, up to 10 seats."
    ),
}


# --------------------------------------------------------------------------
# network safety
# --------------------------------------------------------------------------
class UnsafeURLError(ValueError):
    """The URL resolves somewhere an agent must not reach."""


def assert_public_url(url: str) -> None:
    """Raise unless `url` is http(s) and resolves only to public addresses.

    Blocks loopback, private, link-local (cloud metadata), reserved,
    multicast and unspecified addresses — including via IPv6 and IPv4-mapped
    IPv6. Resolution happens here, so a hostname that rebinds between the
    check and the request is still caught on the next hop.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("missing host")
    if host.lower() in ("localhost", "localhost.localdomain") or host.lower().endswith(".local"):
        raise UnsafeURLError(f"local host not allowed: {host}")
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve {host}") from e
    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw.split("%")[0])
        except ValueError:
            raise UnsafeURLError(f"unparseable address for {host}")
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(f"{host} resolves to a non-public address ({ip})")


def _http_get(url: str, *, timeout=None, max_bytes=None, max_redirects=None):
    """GET a URL with manual redirect handling, re-validating every hop."""
    import httpx

    timeout = config.WEB_TIMEOUT_S if timeout is None else timeout
    max_bytes = config.WEB_MAX_BYTES if max_bytes is None else max_bytes
    max_redirects = config.WEB_MAX_REDIRECTS if max_redirects is None else max_redirects

    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for _ in range(max_redirects + 1):
            assert_public_url(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise ValueError("redirect without a location header")
                    current = urljoin(current, location)
                    continue
                resp.raise_for_status()
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise ValueError(f"response larger than {max_bytes} bytes")
                return current, resp.headers.get("content-type", ""), bytes(body)
    raise ValueError(f"more than {max_redirects} redirects")


class _TextExtractor(HTMLParser):
    """Strip markup, scripts and styles; keep readable text."""

    SKIP = {"script", "style", "noscript", "template", "svg", "iframe"}
    BLOCK = {"p", "div", "br", "li", "tr", "td", "th", "h1", "h2", "h3",
             "h4", "h5", "h6", "section", "article", "header", "footer",
             "table", "ul", "ol", "blockquote", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag in self.BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self.BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def html_to_text(html: str, limit: int = 20000) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Never let malformed markup fail a fetch: fall back to tag stripping.
        return re.sub(r"<[^>]+>", " ", html)[:limit]
    return parser.text()[:limit]


class _DuckDuckGoParser(HTMLParser):
    """Pull result titles/links/snippets out of DuckDuckGo's HTML endpoint."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._capture = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "result__a" in (attrs.get("class") or ""):
            self._capture = "title"
            self._buffer = []
            href = attrs.get("href", "")
            self._pending_url = _unwrap_ddg(href)
        elif tag in ("a", "div") and "result__snippet" in (attrs.get("class") or ""):
            self._capture = "snippet"
            self._buffer = []

    def handle_endtag(self, tag):
        if self._capture == "title" and tag == "a":
            title = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if title:
                self.results.append({"title": title, "url": self._pending_url, "snippet": ""})
            self._capture = None
        elif self._capture == "snippet" and tag in ("a", "div"):
            snippet = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if self.results:
                self.results[-1]["snippet"] = snippet
            self._capture = None

    def handle_data(self, data):
        if self._capture:
            self._buffer.append(data)


def _unwrap_ddg(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return target or href
    return href


def _search_duckduckgo(query: str) -> list[dict]:
    _, _, body = _http_get(
        "https://html.duckduckgo.com/html/?q=" + quote_plus(query),
        max_bytes=500_000,
    )
    parser = _DuckDuckGoParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    parser.close()
    return [r for r in parser.results if r["url"].startswith("http")][:5]


def _search_brave(query: str, key: str) -> list[dict]:
    import httpx

    r = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 5},
        headers={"Accept": "application/json", "X-Subscription-Token": key},
        timeout=config.WEB_TIMEOUT_S,
    )
    r.raise_for_status()
    out = []
    for item in (r.json().get("web", {}) or {}).get("results", [])[:5]:
        out.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": re.sub(r"<[^>]+>", "", item.get("description", "")),
        })
    return out


def _search_tavily(query: str, key: str) -> list[dict]:
    import httpx

    r = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": 5},
        timeout=config.WEB_TIMEOUT_S,
    )
    r.raise_for_status()
    return [
        {"title": i.get("title", ""), "url": i.get("url", ""),
         "snippet": i.get("content", "")}
        for i in (r.json().get("results") or [])[:5]
    ]


def _env(name: str) -> str:
    import os

    return (os.environ.get(name) or "").strip()


def real_search(query: str) -> tuple[list[dict], str]:
    """Run the search provider chain; return (results, provider)."""
    if key := _env("TAVILY_API_KEY"):
        return _search_tavily(query, key), "tavily"
    if key := _env("BRAVE_API_KEY"):
        return _search_brave(query, key), "brave"
    return _search_duckduckgo(query), "duckduckgo"


def mock_search(query: str) -> list[dict]:
    key = next((k for k in SEARCH_INDEX if k in query.lower()), None)
    return SEARCH_INDEX.get(key, [
        {"title": f"Result for {query}", "url": "https://example.com/generic",
         "snippet": f"General information about {query}."},
    ])


# --------------------------------------------------------------------------
# filesystem / arithmetic
# --------------------------------------------------------------------------
def _safe_eval(expr):
    """Evaluate a simple arithmetic expression safely (numbers + - * / ( ))."""
    if not re.fullmatch(r"[0-9\.\+\-\*\/\(\) ]+", expr or ""):
        raise ValueError(f"unsafe expression: {expr!r}")
    return eval(expr, {"__builtins__": {}}, {})


def _maybe_fail(behaviour, name):
    mode = (behaviour or {}).get(name)
    if mode == "fail":
        raise RuntimeError(f"{name} failed (simulated failure)")
    if mode == "timeout":
        raise TimeoutError(f"{name} timed out after 5s (simulated timeout)")


def _crm_update(record_id: str, fields: dict) -> dict:
    """Apply a field update to the local CRM and return the new record."""
    record = next((r for r in CRM.values() if r["record_id"] == record_id), None)
    if record is None:
        record = {"record_id": record_id, "name": record_id, "plan": "Unknown",
                  "seats": 0, "status": "unknown"}
        CRM[record_id] = record
    record.update(fields)
    return dict(record)


def make_tools(behaviour=None, tracer=None, mode=None):
    """Build the LangChain tool set for one run.

    behaviour: {"tool_name": "fail" | "timeout"} to simulate failures.
    mode: real | mock | auto (defaults to WARDEN_TOOLS).
    """
    behaviour = behaviour or {}
    tool_mode = (mode or config.TOOL_MODE or "auto").lower()

    def _log(name, args, output, started, status="ok"):
        if tracer is None:
            return
        tracer.log_tool(name, args, output,
                        duration_ms=int((time.time() - started) * 1000),
                        status=status)

    def _web_source_error(e) -> str:
        return f"{type(e).__name__}: {e}"

    @tool
    def web_search(query: str) -> str:
        """Search the web for a vendor or topic. Returns a JSON list of results."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "web_search")
            if tool_mode == "mock":
                results, source = mock_search(query), "mock"
            else:
                try:
                    results, source = real_search(query)
                except Exception as e:
                    if tool_mode == "real":
                        raise
                    results, source = mock_search(query), f"mock (fallback: {_web_source_error(e)})"
            out = {"query": query, "results": results, "source": source}
            _log("web_search", {"query": query}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("web_search", {"query": query}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def web_fetch(url: str) -> str:
        """Fetch a web page and return its readable text as JSON."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "web_fetch")
            if tool_mode == "mock":
                content, source = FETCH_INDEX.get(url, f"Page content for {url} (generic)."), "mock"
            else:
                try:
                    final_url, ctype, body = _http_get(url)
                    if "html" in ctype or ctype == "":
                        content = html_to_text(body.decode("utf-8", errors="replace"))
                    else:
                        content = body.decode("utf-8", errors="replace")[:20000]
                    source = "web"
                    url = final_url
                except UnsafeURLError:
                    # Never downgrade a deliberate SSRF attempt to mock data:
                    # that would hide the attack from the trace and the user.
                    raise
                except Exception as e:
                    if tool_mode == "real":
                        raise
                    content = FETCH_INDEX.get(url, f"Page content for {url} (generic).")
                    source = f"mock (fallback: {_web_source_error(e)})"
            out = {"url": url, "content": content, "source": source}
            _log("web_fetch", {"url": url}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("web_fetch", {"url": url}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def calculator(expression: str) -> str:
        """Evaluate an arithmetic expression (e.g. '50*49+200'). Returns JSON with the result."""
        started = time.time()
        try:
            result = _safe_eval(expression)
            out = {"expression": expression, "result": result}
            _log("calculator", {"expression": expression}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("calculator", {"expression": expression}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def file_writer(filename: str, content: str) -> str:
        """Write a text file into the agent's sandboxed output directory. Returns JSON with the path."""
        started = time.time()
        try:
            safe = re.sub(r"[^a-zA-Z0-9_.\-]", "_", filename)
            if ".." in safe or "/" in safe:
                raise ValueError("invalid filename")
            out_dir = config.OUTPUT_DIR
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / safe
            path.write_text(content, encoding="utf-8")
            out = {"path": str(path), "bytes": len(content.encode("utf-8"))}
            _log("file_writer", {"filename": safe}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("file_writer", {"filename": filename}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def crm_lookup(customer: str) -> str:
        """Look up a customer record in the (local) CRM. Returns JSON with the record."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "crm_lookup")
            rec = CRM.get(customer) or {
                "record_id": "CUST-0000", "name": customer,
                "plan": "Unknown", "seats": 0, "status": "unknown",
            }
            out = dict(rec)
            _log("crm_lookup", {"customer": customer}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("crm_lookup", {"customer": customer}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def crm_update(record_id: str, fields: dict) -> str:
        """Update a CRM record. `fields` is an object of field changes. Returns JSON."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "crm_update")
            parsed = fields if isinstance(fields, dict) else json.loads(fields)
            record = _crm_update(record_id, parsed)
            out = {"record_id": record_id, "updated": parsed,
                   "record": record, "status": "updated"}
            _log("crm_update", {"record_id": record_id, "fields": parsed}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("crm_update", {"record_id": record_id}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def send_message(recipient: str, message: str) -> str:
        """Send a message to a recipient (outbox, local). Returns JSON with a message id."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "send_message")
            out = {"recipient": recipient, "status": "sent",
                   "message_id": f"msg_{int(time.time() * 1000) % 1000000}"}
            _log("send_message", {"recipient": recipient, "message": message}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("send_message", {"recipient": recipient}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def delete_file(path: str) -> str:
        """Delete a file inside the sandboxed output directory. Returns JSON."""
        started = time.time()
        try:
            safe = re.sub(r"[^a-zA-Z0-9_.\-]", "_", Path(path).name)
            target = config.OUTPUT_DIR / safe
            if not target.exists():
                raise FileNotFoundError(f"no such file: {safe}")
            target.unlink()
            out = {"path": str(target), "status": "deleted"}
            _log("delete_file", {"path": safe}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("delete_file", {"path": path}, {"error": str(e)}, started, status="error")
            raise

    return [web_search, web_fetch, calculator, file_writer,
            crm_lookup, crm_update, send_message, delete_file]


TOOL_NAMES = ["web_search", "web_fetch", "calculator", "file_writer",
              "crm_lookup", "crm_update", "send_message", "delete_file"]
