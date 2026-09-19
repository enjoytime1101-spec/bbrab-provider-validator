# Trust and product boundaries

## In scope

- OpenAI-compatible `GET /models` and `POST /chat/completions` acceptance.
- Offline, reviewable fixtures.
- One explicitly selected provider, environment, base URL, credential reference, and model per run.
- Redacted JSON and Markdown evidence.
- Local mock HTTP testing and a static sample-config Playground.

## Out of scope

- Provider onboarding, account creation, billing, quotas, price verification, key creation, or key storage.
- Production traffic, load, latency, quality, jailbreak, safety, streaming, tool-call, or embedding tests.
- Automatic retries, redirects, provider fallback, cross-provider routing, model aliases, or endpoint discovery.
- Claims that a passing fixture proves the current live provider state.
- Sending production secrets to a web page. The Playground rejects secret-shaped keys and never makes requests.

## Non-leakage invariant

One run cannot add a second provider or success model. All three live requests share the validated base URL. Each request is revalidated and connected to a policy-checked IP, with no redirect or proxy fallback. The models and completion requests use the configured model boundary; the error request uses only the fixed sentinel `bbrab-validator-intentionally-invalid-model`. There is no global config search or provider fallback. Tests assert the exact local mock request paths and bodies.

## Live stopping conditions

Do not run live validation unless a staging/test credential, provider-side spend cap, intended host, and environment are independently confirmed. Credentials containing control characters are rejected. Stop after one run if a safety precondition fails, a response identifies another environment, a redirect is returned, the 1 MiB response cap is exceeded, or provider cost cannot be bounded. Never retry automatically.

The `--acknowledge-provider-cost` flag confirms awareness; it is not a cost guarantee or authorization to use someone else's credential.
