#!/usr/bin/env python3
"""Build, install, exercise, and inventory local release candidates offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build_backend"))
import bbrab_build  # noqa: E402


def _run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_sdist(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("sdist contains a non-file entry")
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise RuntimeError("sdist contains an unsafe path")
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError("sdist member cannot be read")
            target.write_bytes(source.read())
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise RuntimeError("sdist must contain one root directory")
    return roots[0]


def _venv_python(directory: Path) -> Path:
    venv.EnvBuilder(with_pip=True, clear=True).create(directory)
    return directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _console(directory: Path) -> Path:
    return directory / ("Scripts/bbrab-provider-validator.exe" if os.name == "nt" else "bin/bbrab-provider-validator")


def _install_and_check(asset: Path, environment: Path, examples: Path, *, source: bool) -> dict[str, str | bool]:
    python = _venv_python(environment)
    clean_env = os.environ.copy()
    clean_env.update({"PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    command = [str(python), "-m", "pip", "install", "--no-index"]
    if source:
        command.append("--no-build-isolation")
    command.append(str(asset))
    _run(command, env=clean_env)
    console = _console(environment)
    version = _run([str(console), "--version"], env=clean_env)
    _run([
        str(console), "validate",
        "--config", str(examples / "provider.example.json"),
        "--fixture", str(examples / "fixture.passing.json"),
    ], env=clean_env)
    return {"installed": True, "console_version": version, "offline_fixture": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    wheel = output / bbrab_build.build_wheel(str(output))
    sdist = output / bbrab_build.build_sdist(str(output))

    with tempfile.TemporaryDirectory(prefix="bbrab-release-evidence-") as temporary:
        temp = Path(temporary)
        extracted = _extract_sdist(sdist, temp / "source")
        wheel_check = _install_and_check(wheel, temp / "wheel-venv", extracted / "examples", source=False)
        sdist_check = _install_and_check(sdist, temp / "sdist-venv", extracted / "examples", source=True)
        skill_output = _run([
            sys.executable,
            str(extracted / "scripts" / "validate_skill.py"),
            str(extracted / "skill" / "bbrab-provider-validator"),
        ], cwd=extracted)
        required = [
            "examples/provider.example.json", "skill/bbrab-provider-validator/SKILL.md",
            "prompt-blocks/README.md", "docs/playground-core.js", "tests/playground.test.js",
            ".github/workflows/ci.yml", "scripts/validate_skill.py",
        ]
        missing = [relative for relative in required if not (extracted / relative).is_file()]
        if missing:
            raise RuntimeError("sdist is missing required assets: " + ", ".join(missing))

    assets = [
        {"filename": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in (wheel, sdist)
    ]
    manifest = {
        "schema_version": 1,
        "project": "bbrab-provider-validator",
        "version": bbrab_build._version(),
        "assets": assets,
        "verification": {
            "network_index_disabled": True,
            "wheel": wheel_check,
            "sdist": sdist_check,
            "sdist_required_assets": True,
            "extracted_skill": skill_output == "Skill is valid!",
        },
    }
    manifest_path = output / "release-assets.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(manifest_path.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
