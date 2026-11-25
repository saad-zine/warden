"""Demo-agent tools.

All tools are MOCKED but real in the sense that they do actual work
against local state (a mock CRM, a sandboxed output directory, a safe
arithmetic evaluator). They are wrapped so every invocation is logged
to the run trace with timing and status.

`make_tools(behaviour, tracer)` builds the tool set for one run.
`behaviour` is a dict like {"web_search": "fail"} that makes a tool
raise — used by the eval suite to simulate failures (a flaky search,
a CRM timeout) and by tests. In normal runs every tool works.
"""
import json
import re
import time
from pathlib import Path

from langchain_core.tools import tool

from .. import config

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


def make_tools(behaviour=None, tracer=None):
    """Build the LangChain tool set for one run.

    behaviour: {"tool_name": "fail" | "timeout"} to simulate failures.
    tracer: a Tracer/NullTracer that records every tool invocation.
    """
    behaviour = behaviour or {}

    def _log(name, args, output, started, status="ok"):
        if tracer is None:
            return
        tracer.log_tool(name, args, output,
                        duration_ms=int((time.time() - started) * 1000),
                        status=status)

    @tool
    def web_search(query: str) -> str:
        """Search the web for a vendor or topic. Returns a JSON list of results."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "web_search")
            key = next((k for k in SEARCH_INDEX if k in query.lower()), None)
            results = SEARCH_INDEX.get(key, [
                {"title": f"Result for {query}", "url": "https://example.com/generic",
                 "snippet": f"General information about {query}."},
            ])
            out = {"query": query, "results": results}
            _log("web_search", {"query": query}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("web_search", {"query": query}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def web_fetch(url: str) -> str:
        """Fetch a web page and return its text content as JSON."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "web_fetch")
            content = FETCH_INDEX.get(url, f"Page content for {url} (generic).")
            out = {"url": url, "content": content}
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
        """Look up a customer record in the (mock) CRM. Returns JSON with the record."""
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
        """Update a CRM record (mock). `fields` is an object of field changes. Returns JSON."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "crm_update")
            parsed = fields if isinstance(fields, dict) else json.loads(fields)
            out = {"record_id": record_id, "updated": parsed, "status": "updated"}
            _log("crm_update", {"record_id": record_id, "fields": parsed}, out, started)
            return json.dumps(out)
        except Exception as e:
            _log("crm_update", {"record_id": record_id}, {"error": str(e)}, started, status="error")
            raise

    @tool
    def send_message(recipient: str, message: str) -> str:
        """Send a message to a recipient (mock). Returns JSON with a message id."""
        started = time.time()
        try:
            _maybe_fail(behaviour, "send_message")
            out = {"recipient": recipient, "status": "sent",
                   "message_id": f"msg_{int(time.time()) % 100000}"}
            _log("send_message", {"recipient": recipient}, out, started)
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
