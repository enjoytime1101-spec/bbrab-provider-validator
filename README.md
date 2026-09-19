# BBRab Provider Validator

[GitHub source](https://github.com/enjoytime1101-spec/bbrab-provider-validator) · [Browser Playground](https://enjoytime1101-spec.github.io/bbrab-provider-validator/) · [Releases](https://github.com/enjoytime1101-spec/bbrab-provider-validator/releases)

BBRab Provider Validator is an independent, offline-first Python 3.11+ CLI and library for accepting an OpenAI-compatible provider integration. It checks model discovery, visible completion content, exact token usage, structured client errors, and environment isolation. Runtime code uses only the Python standard library.

Official releases are source and wheel assets on GitHub. The project is not published to PyPI or any provider marketplace.

## Safety model

- Offline fixture validation is the default workflow and makes no network requests.
- Live validation is impossible unless both `--live` and `--acknowledge-provider-cost` are supplied.
- A live run sends one model-list request, one minimal completion, and one intentionally invalid-model request. The completion can incur provider cost. The CLI never performs a live run automatically.
- Credentials are local environment-variable references. Literal API keys, tokens, passwords, or authorization values are rejected in configuration.
- Reports contain the credential environment-variable name, never its value. Acceptance details are allow-listed: usage exports only the three standard integer counters, and provider error messages are summarized rather than copied. Recursive redaction is defense in depth.
- HTTP redirects and proxy environment variables are ignored. Each request resolves and validates its target, connects to the validated IP, and retains the original Host and TLS hostname checks. Responses are capped at 1 MiB and always closed.
- Non-loopback live targets require HTTPS and globally routable addresses. Local traffic is allowed only for literal `localhost`, `127.0.0.1`, or `::1` in `local` or `test` environments; naming another private address does not bypass this boundary.

Read [BOUNDARIES.md](BOUNDARIES.md) before live use.

## Quick start

Run directly from a checkout:

```sh
export PYTHONPATH="$PWD/src"
python -m bbrab_provider_validator validate \
  --config examples/provider.example.json \
  --fixture examples/fixture.passing.json \
  --format markdown
```

Or install in an isolated environment:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --no-build-isolation .
bbrab-provider-validator validate \
  --config examples/provider.example.json \
  --fixture examples/fixture.passing.json
```

The project has no runtime or build dependencies. Its repository-local PEP 517 backend uses only Python 3.11+ standard-library modules, so the exact command above works in a fresh venv containing only pip and does not access a package index. See [LOCKING.md](LOCKING.md).

## Explicit live validation

Create a secret-free config from the example, point it at the intended provider and environment, then set the referenced variable locally:

```sh
export EXAMPLE_STAGING_API_KEY='set-this-only-in-your-shell'
bbrab-provider-validator validate \
  --config provider.staging.json \
  --live \
  --acknowledge-provider-cost \
  --report-json provider-report.json \
  --report-markdown provider-report.md
```

Do not put a production key in configuration, fixtures, command-line arguments, reports, issue bodies, or the Playground. Prefer a restricted test or staging credential with a hard provider-side spend cap.

## Acceptance contract

A run passes only when:

1. `GET /models` returns HTTP 200 and a non-empty model list containing the configured model.
2. `POST /chat/completions` returns HTTP 200 and non-whitespace assistant content.
3. `usage.prompt_tokens`, `usage.completion_tokens`, and `usage.total_tokens` are non-boolean integers; prompt and completion are non-negative, total is positive, and total equals prompt plus completion.
4. An intentionally invalid model returns a 4xx response with a non-empty OpenAI-style error message.
5. The configured host and credential environment match the declared environment boundary. If an environment response header is configured, every response must match it.

Provider-specific usage accounting that cannot satisfy exact equality is currently a failure, not a warning. Preserve the fixture as evidence and discuss a contract revision before weakening this invariant.

## Library usage

```python
from bbrab_provider_validator.config import load_json
from bbrab_provider_validator.validator import validate_fixture

report = validate_fixture(load_json("provider.json"), load_json("fixture.json"))
if report["status"] != "passed":
    raise SystemExit("provider acceptance failed")
```

See [API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [SECURITY.md](SECURITY.md).

## Playground

The static [Pages Playground](docs/index.html) validates and exports sample, secret-free configurations entirely in the browser. Its validation rejects both credential field names and credential-shaped values, and its Markdown export escapes all dynamic content. It performs no network requests and cannot run live validation. Serve `docs/` with any static server or enable GitHub Pages after publishing a repository.

## Tests

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
node --test tests/playground.test.js
```

The suite includes a local mock HTTP server. It does not contact a real provider and does not incur cost.

## Project resources

- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [Local release evidence](RELEASE.md)
- [Apache-2.0 license](LICENSE)
- [Codex Skill](skill/bbrab-provider-validator/SKILL.md)
- [Prompt Blocks](prompt-blocks/README.md)
