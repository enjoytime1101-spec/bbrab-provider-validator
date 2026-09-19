# Local release evidence

This repository remains an unpublished candidate. Building assets does not authorize uploading, tagging, publishing, or contacting a provider.

Generate a fully local release evidence bundle with:

```sh
python scripts/release_evidence.py --output /tmp/bbrab-release-evidence
```

The standard-library script builds the actual wheel and source distribution, safely unpacks the source distribution, checks its required operational assets, creates separate fresh virtual environments, installs both artifacts with package indexes disabled, runs each installed console CLI against the unpacked offline fixture, validates the unpacked Codex Skill, and writes `release-assets.json`.

The manifest is the candidate asset inventory. Each wheel and source distribution entry includes its filename, byte size, and SHA-256 digest. Verification flags record offline installation, console version, fixture execution, source asset coverage, and Skill validation. Generate a new manifest after every source change; hashes are intentionally not committed because the manifest itself is release-run evidence.
