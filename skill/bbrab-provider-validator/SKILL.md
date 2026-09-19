---
name: bbrab-provider-validator
description: Validate a secret-free OpenAI-compatible provider configuration from offline fixtures, or prepare an explicitly authorized live acceptance run. Use for provider acceptance evidence; not for account setup, key storage, load testing, or automatic production probes.
---

# BBRab Provider Validator

Prefer offline fixture validation. Inspect the intended configuration and fixture, then run the actual CLI from the repository root:

```sh
PYTHONPATH=src python -m bbrab_provider_validator validate --config <config.json> --fixture <fixture.json> --format markdown
```

Treat a nonzero exit as a failed or invalid acceptance. Report which contract checks failed without reproducing provider response bodies or secrets.

For live validation, first read `BOUNDARIES.md`. Confirm the user explicitly requested a live run, the credential is a local environment-variable reference, and a minimal request can incur provider cost. Never infer either acknowledgement. The actual command must contain both gates:

```sh
PYTHONPATH=src python -m bbrab_provider_validator validate --config <config.json> --live --acknowledge-provider-cost --report-json <report.json> --report-markdown <report.md>
```

Do not pass credentials as arguments or place them in config, fixture, prompts, or reports. Do not retry a live failure automatically. Never weaken host, environment, usage, or probe-budget checks to obtain a pass.
