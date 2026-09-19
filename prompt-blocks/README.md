# Prompt Blocks

These blocks are reviewable operator prompts. They call the repository's real CLI; they do not ask an agent to simulate provider acceptance.

## Offline acceptance

```text
Use $bbrab-provider-validator in offline mode. Review <config-path> and <fixture-path> for embedded secrets, then run the real CLI with PYTHONPATH=src. Return the exit code, overall status, failed check names, and paths to any requested redacted reports. Do not make network requests and do not print provider response bodies.
```

## Prepare, but do not execute, live acceptance

```text
Use $bbrab-provider-validator to review <config-path> for a possible live run. Check the host allow-list, credential environment name, environment match, response marker, and probe budget. Do not execute live validation. Show the exact gated command and explain that the minimal completion may incur provider cost.
```

## Explicit live acceptance

```text
Use $bbrab-provider-validator to run one live acceptance against <config-path>. I explicitly authorize the live run and acknowledge provider cost. Confirm the credential is available only through the configured local environment variable, run the real CLI with both --live and --acknowledge-provider-cost, write redacted JSON and Markdown reports, and do not retry automatically.
```
