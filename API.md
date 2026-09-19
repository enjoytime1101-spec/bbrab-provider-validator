# API reference

The public API is intentionally small. Inputs and returned dictionaries must be treated as untrusted data at system boundaries.

## `validate_fixture(config, fixture)`

Validates a recorded fixture without network access. `config` and `fixture` are dictionaries matching the example files. It returns a redacted report dictionary and raises `ConfigurationError` or `ValueError` for malformed input.

## `validate_live(config, *, live=False, acknowledge_provider_cost=False, timeout=15.0)`

Runs the same acceptance checks against an OpenAI-compatible provider. Both booleans must be `True`; otherwise it raises `PermissionError`. The credential value is read from `config["credential"]["env"]` at call time. Do not log the config, request headers, or process environment around this call.

The optional `request` keyword is an injectable transport for tests. Production callers should leave it unchanged.

## CLI exit codes

| Code | Meaning |
| --- | --- |
| `0` | All acceptance checks passed. |
| `1` | A well-formed run completed and at least one acceptance check failed. |
| `2` | Configuration, fixture, credential, or live-safety precondition failed. |

## Report shape

Reports contain `contract`, `generated_at`, `mode`, `provider`, `status`, and `checks`. A check has `name`, `status`, and an allow-listed, redacted `detail`. JSON output is stable enough for CI inspection, but new checks may be added in minor releases.

Usage detail contains exactly `prompt_tokens`, `completion_tokens`, and `total_tokens`; unknown provider extensions are discarded. Error detail contains only the HTTP status and structural summary fields. Original provider error messages, response headers, completion text, and response bodies are never exported.

The report includes `provider.credential_env` as a reference. It never includes the environment variable value.
