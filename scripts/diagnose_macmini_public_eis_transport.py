#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import ssl
from typing import Any
from urllib.parse import urlparse

from src.shared.network.etp_trust import (
    policy_from_environment,
    resolve_host_policy,
    should_bypass_proxy,
)
from src.shared.network.http_client import create_urllib_context
from src.tender_research.providers.public_44fz_search import (
    Public44FzSearchProvider,
    PublicSearchStatus,
    _hostname_matches_no_proxy,
)

PROXY_ENV_NAMES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _proxy_environment_presence() -> dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in PROXY_ENV_NAMES}


def _safe_transport_snapshot(
    provider: Public44FzSearchProvider,
    url: str,
) -> dict[str, Any]:
    hostname = (urlparse(url).hostname or "").lower()
    policy = policy_from_environment()
    host_policy = resolve_host_policy(hostname, policy)
    ssl_context, policy_bypass = create_urllib_context(url, policy=policy)
    source_allowlist_match = _hostname_matches_no_proxy(
        hostname,
        provider._no_proxy_domains,
    )
    source_direct_connection = bool(
        provider._bypass_proxy and source_allowlist_match
    )
    effective_proxy_bypass = bool(policy_bypass or source_direct_connection)

    return {
        "hostname": hostname,
        "generic_etp_policy": {
            "policy_enabled": policy.enabled,
            "proxy_bypass_enabled": policy.proxy_bypass_enabled,
            "host_policy_matched": host_policy is not None,
            "host_direct_connection": bool(
                host_policy and host_policy.direct_connection
            ),
            "host_authority_configured": bool(
                host_policy and host_policy.authority
            ),
            "effective_proxy_bypass": should_bypass_proxy(hostname, policy),
        },
        "public_search_source_control": {
            "bypass_proxy_requested": provider._bypass_proxy,
            "source_allowlist_match": source_allowlist_match,
            "source_direct_connection": source_direct_connection,
            "effective_proxy_bypass": effective_proxy_bypass,
            "configured_no_proxy_domains": list(provider._no_proxy_domains),
        },
        "tls": {
            "verify_mode": int(ssl_context.verify_mode),
            "verify_mode_is_cert_required": ssl_context.verify_mode
            == ssl.CERT_REQUIRED,
            "check_hostname": ssl_context.check_hostname,
            "minimum_version": str(ssl_context.minimum_version),
            "context_type": type(ssl_context).__name__,
        },
        "proxy_environment_present": _proxy_environment_presence(),
    }


def _classification(status: str, error: str | None) -> tuple[str, int]:
    lowered = (error or "").lower()
    if "tls verification failed" in lowered or "certificate verify failed" in lowered:
        return "TLS_VERIFY_BLOCKED", 41
    if "proxy" in lowered or "502 bad gateway" in lowered:
        return "PRODUCT_PROXY_BLOCKED", 43
    if status in {PublicSearchStatus.SUCCESS, PublicSearchStatus.EMPTY}:
        return "PRODUCT_TRANSPORT_PASS", 0
    if status in {
        PublicSearchStatus.PARSE_ERROR,
        PublicSearchStatus.BLOCKED,
        PublicSearchStatus.CAPTCHA,
    }:
        return "PRODUCT_APPLICATION_OR_PARSER_BLOCKED", 21
    if status == PublicSearchStatus.TIMEOUT:
        return "PRODUCT_TRANSPORT_TIMEOUT", 42
    return "PRODUCT_TRANSPORT_BLOCKED", 44


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Probe the exact Tender Agent public-EIS provider transport path "
            "without weakening TLS or source controls."
        )
    )
    parser.add_argument(
        "--query",
        default="электротехническое оборудование",
    )
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--law", default="44fz")
    args = parser.parse_args()

    provider = Public44FzSearchProvider(bypass_proxy=True)
    url = provider._build_url(
        query=args.query,
        page=1,
        page_size=max(1, min(args.page_size, 100)),
        law_type=args.law,
    )

    try:
        transport = _safe_transport_snapshot(provider, url)
        page = provider.search(
            query=args.query,
            page=1,
            page_size=max(1, min(args.page_size, 100)),
            law_type=args.law,
        )
        classification, rc = _classification(page.status, page.error)
        payload = {
            "transport": transport,
            "product_probe": {
                "status": page.status,
                "error": page.error,
                "items_count": len(page.items),
                "source_url": page.source_url,
            },
            "classification": classification,
            "tls_verification_disabled": False,
        }
    except Exception as exc:
        payload = {
            "transport": None,
            "product_probe": {
                "status": "exception",
                "error": str(exc),
                "exception_type": type(exc).__name__,
                "items_count": 0,
            },
            "classification": "PRODUCT_PROBE_EXCEPTION",
            "tls_verification_disabled": False,
        }
        rc = 45

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
