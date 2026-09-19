# Architecture

The validator uses one acceptance engine for two evidence sources:

```text
secret-free config ─┬─ fixture adapter ─┐
                    └─ guarded HTTP ────┤
                                       ▼
                              acceptance contract
                                       │
                                       ▼
                         recursive redaction + report
```

`config.py` rejects embedded credentials, validates environment and host scope, enforces the probe budget, and resolves a request to a policy-checked IP. `http_client.py` connects directly to that IP without environment proxies, preserves the original Host and TLS hostname, caps JSON responses at 1 MiB, closes responses, and never follows redirects. `validator.py` adapts fixture or live responses to the same checks and constructs report details from explicit field allow-lists. `redact.py` and `report.py` form a defense-in-depth output boundary. `cli.py` owns explicit live acknowledgement, generic unexpected-input errors, and file output.

There is no database, background service, telemetry, provider SDK, plugin system, or configuration discovery. The CLI reads only paths and environment-variable names explicitly supplied by the operator.

## Environment isolation

Isolation is enforced in layers: the configured base URL host must be allow-listed; the credential declares and must match the provider environment; and an optional response header can bind returned evidence to the intended environment. Every request repeats URL and DNS policy validation, rejects non-global addresses except literal loopback in local/test, then binds the connection to the validated IP. HTTPS still verifies the certificate against the original hostname. A single run constructs every URL from one validated base URL and uses exactly one configured success model plus one fixed invalid error-probe model.

## Output minimization

Raw provider response bodies are validation input, not report content. Model output becomes only a length, usage becomes three standard counters, error messages become presence and length fields, and environment headers become presence/match booleans. Recursive secret, URL-query, authorization, and whole-line cookie/header redaction remains as a final safeguard.

## Budget invariant

The live success probe requests at most `probe.max_tokens` (1–16). Configuration is rejected if this exceeds `probe.normal_request_max_tokens`. The error probe requests one token but should be rejected before generation. This prevents acceptance testing from silently raising the integration's normal completion budget.
