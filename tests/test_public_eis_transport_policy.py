from __future__ import annotations

import ssl
from urllib.request import ProxyHandler

import src.tender_research.providers.public_44fz_search as public_search


EIS_URL = (
    "https://zakupki.gov.ru/epz/order/extendedsearch/"
    "results.html?fz44=on"
)


class _FailingOpener:
    def open(self, *args, **kwargs):
        raise RuntimeError("stop after transport construction")


def test_public_eis_source_control_bypasses_environment_proxy_when_generic_policy_does_not(
    monkeypatch,
):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:8080")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:8080")

    captured: dict[str, tuple[object, ...]] = {}

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return _FailingOpener()

    verified_context = ssl.create_default_context()
    monkeypatch.setattr(public_search, "build_opener", fake_build_opener)
    monkeypatch.setattr(
        public_search,
        "create_urllib_context",
        lambda url: (verified_context, False),
    )

    provider = public_search.Public44FzSearchProvider(bypass_proxy=True)
    result = provider._fetch_page(EIS_URL)

    assert result["status"] == public_search.PublicSearchStatus.NETWORK_ERROR
    assert "stop after transport construction" in str(result["error"])

    proxy_handlers = [
        handler
        for handler in captured["handlers"]
        if isinstance(handler, ProxyHandler)
    ]
    assert len(proxy_handlers) == 1
    assert proxy_handlers[0].proxies == {}

    assert verified_context.verify_mode == ssl.CERT_REQUIRED
    assert verified_context.check_hostname is True


def test_public_eis_source_control_can_be_disabled_explicitly(monkeypatch):
    captured: dict[str, tuple[object, ...]] = {}

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return _FailingOpener()

    monkeypatch.setattr(public_search, "build_opener", fake_build_opener)
    monkeypatch.setattr(
        public_search,
        "create_urllib_context",
        lambda url: (ssl.create_default_context(), False),
    )

    provider = public_search.Public44FzSearchProvider(bypass_proxy=False)
    provider._fetch_page(EIS_URL)

    proxy_handlers = [
        handler
        for handler in captured["handlers"]
        if isinstance(handler, ProxyHandler)
    ]
    assert proxy_handlers == []


def test_public_eis_source_allowlist_matches_expected_hosts_only():
    domains = public_search.DEFAULT_NO_PROXY_DOMAINS

    assert public_search._hostname_matches_no_proxy("zakupki.gov.ru", domains)
    assert public_search._hostname_matches_no_proxy("www.zakupki.gov.ru", domains)
    assert public_search._hostname_matches_no_proxy("int44.zakupki.gov.ru", domains)
    assert not public_search._hostname_matches_no_proxy("example.com", domains)
    assert not public_search._hostname_matches_no_proxy(
        "zakupki.gov.ru.example.com",
        domains,
    )
