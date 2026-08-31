# Mac mini public EIS TLS verification path

## Context

The first real autonomous Mac mini E2E run reached Tender Agent public EIS discovery but stopped fail-closed before procurement selection:

- product marker: `MACMINI_AUTONOMOUS_PROCUREMENT_E2E_BLOCKED`
- product code: `search_not_actionable`
- public EIS outcome: `source_unavailable`
- parser status: `blocked`
- error: `TLS verification failed`

No procurement, documents, analysis run, local LLM call, or report was created. This is a source/runtime TLS blocker, not an AI-ENG orchestration failure.

## Root cause in the application path

Public EIS requests use `src.shared.network.http_client.fetch_with_http_policy()`. The shared client obtains its TLS context from `src.shared.network.etp_trust.build_ssl_context()`.

Before this change, an explicitly configured `system` trust authority used `truststore.SSLContext`, but a normal public HTTPS host with no explicit ETP authority used `ssl.create_default_context()`. On macOS this makes verification depend on the Python/OpenSSL CA discovery path rather than the native Keychain trust path used by the operating system.

The public EIS request then correctly failed closed as `tls_verify`, which the public EIS parser mapped to `blocked`.

## Secure correction

For public/unregistered HTTPS hosts, and for explicit `system` authorities, the shared TLS layer now creates a verified client context through `truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)`.

The following security properties remain mandatory:

- certificate verification: `ssl.CERT_REQUIRED`;
- hostname verification: enabled;
- minimum TLS version: TLS 1.2;
- no `verify=False` or unverified context;
- no source-control bypass;
- no cloud fallback;
- explicit custom/pinned CA authorities continue to use their validated CA file and fingerprint checks;
- failure to initialise native system trust is fail-closed.

## Runtime validation required on Mac mini

Hosted CI can prove policy invariants but cannot prove the Mac mini Keychain/network path. The same machine that produced the blocker must therefore run the shared production HTTP client after updating to the fixed commit.

The TLS probe must use `fetch_with_http_policy()` with normal certificate verification. If that succeeds, restart the local backend and rerun the same one-command E2E.

Success is not declared at TLS connectivity alone. The target remains:

`public EIS search -> selection -> documents -> completeness gate -> local LLM event -> HTML report`

Any later blocker is recorded as the next product/runtime blocker and must remain fail-closed.
