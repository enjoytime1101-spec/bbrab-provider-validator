"""Zero-dependency PEP 517 backend for bbrab-provider-validator.

The project intentionally keeps this backend small and repository-specific. It
builds one pure-Python package, its console entry point, and standard wheel
metadata using only Python 3.11+ standard-library modules.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import tomllib

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "bbrab_provider_validator"
DIST_NAME = "bbrab-provider-validator"
NORMALIZED_NAME = "bbrab_provider_validator"


def _project() -> dict[str, Any]:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def _version() -> str:
    return str(_project()["version"])


def _dist_info() -> str:
    return f"{NORMALIZED_NAME}-{_version()}.dist-info"


def _metadata() -> str:
    project = _project()
    return "\n".join([
        "Metadata-Version: 2.3",
        f"Name: {DIST_NAME}",
        f"Version: {project['version']}",
        f"Summary: {project['description']}",
        f"Requires-Python: {project['requires-python']}",
        "License: Apache-2.0",
        "License-File: LICENSE",
        "Description-Content-Type: text/markdown",
        "",
        (ROOT / "README.md").read_text(encoding="utf-8"),
        "",
    ])


def _wheel_metadata() -> str:
    return "\n".join([
        "Wheel-Version: 1.0",
        "Generator: bbrab-build 1",
        "Root-Is-Purelib: true",
        "Tag: py3-none-any",
        "",
    ])


def _entry_points() -> str:
    return "[console_scripts]\nbbrab-provider-validator = bbrab_provider_validator.cli:main\n"


def _metadata_files() -> dict[str, bytes]:
    prefix = _dist_info()
    return {
        f"{prefix}/METADATA": _metadata().encode("utf-8"),
        f"{prefix}/WHEEL": _wheel_metadata().encode("utf-8"),
        f"{prefix}/entry_points.txt": _entry_points().encode("utf-8"),
        f"{prefix}/licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
    }


def _digest(content: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}"


def _record(files: dict[str, bytes]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for name in sorted(files):
        writer.writerow((name, _digest(files[name]), len(files[name])))
    writer.writerow((f"{_dist_info()}/RECORD", "", ""))
    return output.getvalue().encode("utf-8")


def get_requires_for_build_wheel(config_settings: dict[str, Any] | None = None) -> list[str]:
    return []


def get_requires_for_build_sdist(config_settings: dict[str, Any] | None = None) -> list[str]:
    return []


def prepare_metadata_for_build_wheel(
    metadata_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    target = Path(metadata_directory) / _dist_info()
    target.mkdir(parents=True, exist_ok=False)
    for archive_name, content in _metadata_files().items():
        relative = Path(archive_name).relative_to(_dist_info())
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return _dist_info()


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    filename = f"{NORMALIZED_NAME}-{_version()}-py3-none-any.whl"
    destination = Path(wheel_directory) / filename
    files: dict[str, bytes] = {}
    for source in sorted(PACKAGE_ROOT.glob("*.py")):
        files[f"bbrab_provider_validator/{source.name}"] = source.read_bytes()
    files.update(_metadata_files())
    files[f"{_dist_info()}/RECORD"] = _record(files)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for archive_name, content in sorted(files.items()):
            wheel.writestr(archive_name, content)
    return filename


def build_sdist(
    sdist_directory: str,
    config_settings: dict[str, Any] | None = None,
) -> str:
    filename = f"{NORMALIZED_NAME}-{_version()}.tar.gz"
    destination = Path(sdist_directory) / filename
    prefix = f"{NORMALIZED_NAME}-{_version()}"
    included = [
        "pyproject.toml", "README.md", "LICENSE", "API.md", "ARCHITECTURE.md",
        "BOUNDARIES.md", "CHANGELOG.md", "CONTRIBUTING.md", "LOCKING.md", "SECURITY.md",
        "requirements.lock",
    ]
    included.extend(str(path.relative_to(ROOT)) for path in sorted(PACKAGE_ROOT.glob("*.py")))
    included.append("build_backend/bbrab_build.py")
    with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for relative in included:
            source = ROOT / relative
            archive.add(source, arcname=f"{prefix}/{relative}", recursive=False)
    return filename
