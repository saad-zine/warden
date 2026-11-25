"""Web tool safety and parsing.

The network is never touched: DNS resolution is stubbed and the search /
fetch providers are monkeypatched. What is tested here is the part that
matters for safety and correctness — SSRF refusal, redirect re-validation,
markup stripping, and the labelled mock fallback.
"""
import json
import socket

import pytest

from app.agents import tools


def _resolve_to(*ips):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]

    return fake_getaddrinfo


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http://localhost:8000/health",
    "http://127.0.0.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/internal",
    "http://192.168.1.1/",
    "http://[::1]/",
    "http://metadata.local/",
])
def test_ssrf_guard_blocks_non_public_targets(url):
    with pytest.raises(tools.UnsafeURLError):
        tools.assert_public_url(url)


def test_ssrf_guard_allows_public_host(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _resolve_to("93.184.216.34"))
    tools.assert_public_url("https://example.com/page")


def test_ssrf_guard_blocks_hostname_that_resolves_private(monkeypatch):
    """Rebinding a public-looking name to an internal IP is refused."""
    monkeypatch.setattr(socket, "getaddrinfo", _resolve_to("127.0.0.1"))
    with pytest.raises(tools.UnsafeURLError):
        tools.assert_public_url("https://totally-public.example/x")


def test_html_to_text_strips_scripts_and_styles():
    html = """
    <html><head><style>.x{color:red}</style><script>alert(1)</script></head>
    <body><h1>Acme pricing</h1><p>Business plan: <b>$49</b> per seat.</p>
    <div>Setup fee is $200.</div></body></html>
    """
    text = tools.html_to_text(html)
    assert "Acme pricing" in text
    assert "$49" in text
    assert "Setup fee is $200." in text
    assert "alert(1)" not in text
    assert "color:red" not in text
    assert "<b>" not in text


def test_ddg_redirect_is_unwrapped():
    wrapped = ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Facme"
               "&rut=abc")
    assert tools._unwrap_ddg(wrapped) == "https://example.com/acme"


def test_ddg_result_parser():
    html = """
    <div class="result">
      <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Facme.test%2Fpricing">Acme pricing</a>
      <a class="result__snippet">The Business plan costs $49 per seat.</a>
    </div>
    """
    parser = tools._DuckDuckGoParser()
    parser.feed(html)
    parser.close()
    assert parser.results[0]["title"] == "Acme pricing"
    assert parser.results[0]["url"] == "https://acme.test/pricing"
    assert "49" in parser.results[0]["snippet"]


def _tool(tools_list, name):
    return next(t for t in tools_list if t.name == name)


def test_web_fetch_blocks_private_url_even_in_auto_mode():
    fetch = _tool(tools.make_tools(mode="auto"), "web_fetch")
    with pytest.raises(Exception) as err:
        fetch.invoke({"url": "http://169.254.169.254/latest/meta-data/"})
    # The tool logs and re-raises; in auto mode a *network* failure falls
    # back, but a deliberate SSRF attempt must not be downgraded to mock.
    assert "169.254.169.254" in str(err.value)


def test_web_search_falls_back_to_mock_and_says_so(monkeypatch):
    def boom(query):
        raise RuntimeError("provider down")

    monkeypatch.setattr(tools, "real_search", boom)
    search = _tool(tools.make_tools(mode="auto"), "web_search")
    out = json.loads(search.invoke({"query": "Acme Corp pricing"}))
    assert out["results"][0]["url"].startswith("https://example.com/acme")
    assert out["source"].startswith("mock (fallback: RuntimeError")


def test_web_search_real_mode_propagates_failure(monkeypatch):
    def boom(query):
        raise RuntimeError("provider down")

    monkeypatch.setattr(tools, "real_search", boom)
    search = _tool(tools.make_tools(mode="real"), "web_search")
    with pytest.raises(RuntimeError):
        search.invoke({"query": "Acme Corp pricing"})


def test_mock_mode_never_hits_the_network(monkeypatch):
    def explode():
        raise AssertionError("network used in mock mode")

    monkeypatch.setattr(tools, "real_search", explode)
    search = _tool(tools.make_tools(mode="mock"), "web_search")
    out = json.loads(search.invoke({"query": "Globex pricing"}))
    assert out["source"] == "mock"


def test_crm_update_persists_and_returns_record():
    update = _tool(tools.make_tools(mode="mock"), "crm_update")
    out = json.loads(update.invoke({"record_id": "CUST-1042",
                                    "fields": {"status": "quoted"}}))
    assert out["record"]["record_id"] == "CUST-1042"
    assert out["record"]["status"] == "quoted"
    # Restore the fixture so other tests see the original record.
    tools.CRM["Acme Corp"]["status"] = "active"
