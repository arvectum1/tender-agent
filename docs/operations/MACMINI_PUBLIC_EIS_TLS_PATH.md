# Mac mini public EIS TLS verification path

## Context

The first real autonomous Mac mini E2E run reached Tender Agent public EIS discovery but stopped fail-closed before procurement selection:

- product marker: `MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED`
- product code: `search_not_actionable`
- public EIS outcome: `source_unavailable`
- parser status: `blocked`
- error: `TLS verification failed`

No procurement, documents, analysis run, local LLM call, or report was created. This is a source/runtime transport blocker, not an AI-ENG orchestration failure.

## Actual Product transport path

The public HTML search does not use a generic `httpx` request directly. The runtime path is:

`public-44fz-search endpoint -> procurement_discovery.search_public_44fz() -> fetch_public_44fz_search_page() -> Public44FzSearchProvider._fetch_page()`

`Public44FzSearchProvider._fetch_page()` obtains the verified SSL context from `src.shared.network.http_client.create_urllib_context()`. It then combines two independent proxy decisions:

1. generic ETP trust-policy direct connection from `should_bypass_proxy()`;
2. the public-search source control: `bypass_proxy=True` plus the explicit EIS host allowlist in `DEFAULT_NO_PROXY_DOMAINS`.

For an allowed EIS host, the second path constructs `ProxyHandler({})`, so environment `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` values do not determine the public-search route. This source-specific direct route is explicit repository policy; it is not a TLS or source-control bypass.

## TLS correction

Before the TLS correction, an explicitly configured `system` trust authority used `truststore.SSLContext`, but a normal public HTTPS host with no explicit ETP authority used `ssl.create_default_context()`. On macOS that can make verification depend on the Python/OpenSSL CA discovery path rather than the native Keychain trust path used by the host.

For public/unregistered HTTPS hosts, and for explicit `system` authorities, the shared TLS layer now creates a verified client context through `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`.

The following security properties remain mandatory:

- certificate verification: `ssl.CERT_REQUIRED`;
- hostname verification: enabled;
- minimum TLS version: TLS 1.2;
- no `verify=False` or unverified context;
- no removal of the EIS source allowlist/control;
- no cloud fallback;
- explicit custom/pinned CA authorities continue to use their validated CA file and fingerprint checks;
- failure to initialise native system trust is fail-closed.

## Generic-proxy diagnostic result and reconciliation

A later Mac mini diagnostic reported:

- generic ETP policy disabled/unmatched for `zakupki.gov.ru`;
- environment proxy variables present;
- generic effective proxy bypass `false`;
- `ProxyError: 502 Bad Gateway`;
- no TLS verification failure.

That diagnostic exercised the generic shared-client proxy decision only. It did **not** include `Public44FzSearchProvider`'s source-controlled EIS direct-routing decision. Therefore `EFFECTIVE_PROXY_POLICY` from that probe is not, by itself, a Product public-search blocker and does not classify the native TLS fix.

The repository-owned diagnostic `scripts/diagnose_macmini_public_eis_transport.py` now reports both decisions and performs the read-only request through the actual `Public44FzSearchProvider` path. It prints proxy-variable presence only, never proxy credentials or other secret values.

Regression coverage pins the requirement that, when generic ETP policy does not request direct connection but environment proxies exist, an allowed public EIS host still receives the explicit source-controlled `ProxyHandler({})` route while certificate and hostname verification stay enabled.

## Runtime validation required on Mac mini

Hosted CI can prove transport-policy invariants but cannot prove the Mac mini Keychain/network route. Runtime validation must therefore use the exact Product provider path:

```bash
.venv/bin/python scripts/diagnose_macmini_public_eis_transport.py \
  --query "электротехническое оборудование" \
  --law 44fz \
  --page-size 10
```

Interpretation:

- `PRODUCT_TRANSPORT_PASS`: TLS and the Product direct-route transport reached EIS; continue the one-command E2E.
- `TLS_VERIFY_BLOCKED`: native TLS correction is not runtime-accepted; stop and diagnose trust on the Mac mini.
- `PRODUCT_PROXY_BLOCKED`: the actual Product provider still reached a proxy; stop and reconcile Product routing before any E2E run.
- `PRODUCT_APPLICATION_OR_PARSER_BLOCKED`: transport reached EIS but EIS/application/parser behavior is the next blocker; do not weaken transport controls.

After `PRODUCT_TRANSPORT_PASS`, restart the local backend so it loads the exact fixed code, then rerun the same one-command E2E.

Success is not declared at transport connectivity alone. The target remains:

`public EIS search -> selection -> documents -> completeness gate -> local LLM event -> HTML report`

Any later blocker is recorded as the next Product/runtime blocker and remains fail-closed.
