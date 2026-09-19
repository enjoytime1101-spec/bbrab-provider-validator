# Contributing

Use Python 3.11 or newer. Keep runtime code standard-library only, English-only, and independent from any host application. Do not copy product business logic, credentials, databases, or private fixtures into this repository.

Before proposing a change:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
node --test tests/playground.test.js
PYTHONPATH=src python -m bbrab_provider_validator validate \
  --config examples/provider.example.json \
  --fixture examples/fixture.passing.json
```

Changes to packaging must also pass a network-free install in a new venv:

```sh
python -m venv /tmp/bbrab-clean
/tmp/bbrab-clean/bin/python -m pip install --no-index --no-build-isolation .
/tmp/bbrab-clean/bin/bbrab-provider-validator --version
```

Before treating a candidate as releasable, run `scripts/release_evidence.py` as documented in [RELEASE.md](RELEASE.md). It must verify both the actual wheel and source distribution; a source-checkout-only test is insufficient.

New acceptance behavior needs an offline fixture test. Network behavior needs a local mock server test. Real provider calls do not belong in CI, pull requests, or issue reproduction steps.

Commits must not contain API keys or generated reports derived from non-public providers. Keep generated build products and local environments untracked.
