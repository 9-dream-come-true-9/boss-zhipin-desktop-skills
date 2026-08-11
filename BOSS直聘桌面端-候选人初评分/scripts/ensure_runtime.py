"""Force-install or verify the bundled BOSS scoring runtime globally."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PACKAGE_NAME = "boss-candidate-pipeline-automation"
PACKAGE_VERSION = "0.4.3"
WHEEL_NAME = "boss_candidate_pipeline_automation-0.4.3-py3-none-any.whl"
WHEEL_SHA256 = "55ac6e1837efb91e32cf5ea893167b0c459e82a6ccce47fb4623c2c31e6e9b16"
EXPECTED_BUILD_ID = "boss-candidate-pipeline-20260803-v9"
EXPECTED_SELECTOR_PROFILE = "boss-1.7.4.963-candidate-pipeline-v6"
REQUIRED_MODULES = ("pywinauto", "psutil", "win32api", "comtypes")


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def wheel_path() -> Path:
    return skill_dir() / "references" / WHEEL_NAME


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_version() -> str | None:
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None


def missing_modules() -> list[str]:
    return [
        name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None
    ]


def runtime_provenance() -> dict[str, object]:
    script = r'''
import importlib.metadata
import importlib.util
import json
from pathlib import Path

required = ("pywinauto", "psutil", "win32api", "comtypes")
missing = [name for name in required if importlib.util.find_spec(name) is None]
try:
    import boss_candidates
    from boss_candidates.ui.selectors import SELECTOR_PROFILE
    payload = {
        "distribution_version": importlib.metadata.version(
            "boss-candidate-pipeline-automation"
        ),
        "runtime_version": boss_candidates.__version__,
        "runtime_build_id": boss_candidates.RUNTIME_BUILD_ID,
        "selector_profile": SELECTOR_PROFILE,
        "module_path": str(Path(boss_candidates.__file__).resolve()),
        "missing_modules": missing,
    }
except Exception as exc:
    payload = {
        "probe_error": f"{type(exc).__name__}: {exc}",
        "missing_modules": missing,
    }
print(json.dumps(payload, ensure_ascii=False))
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        return {"probe_error": result.stderr.strip() or result.stdout.strip()}
    try:
        return dict(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        return {"probe_error": f"invalid probe JSON: {exc}"}


def provenance_expected(value: dict[str, object]) -> bool:
    return (
        value.get("distribution_version") == PACKAGE_VERSION
        and value.get("runtime_version") == PACKAGE_VERSION
        and value.get("runtime_build_id") == EXPECTED_BUILD_ID
        and value.get("selector_profile") == EXPECTED_SELECTOR_PROFILE
        and value.get("missing_modules") == []
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("This Skill requires an interactive Windows desktop.")
    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        raise SystemExit("Use Python 3.11, 3.12, or 3.13.")
    wheel = wheel_path()
    if not wheel.is_file():
        raise SystemExit(f"Bundled wheel not found: {wheel}")
    actual_hash = file_sha256(wheel)
    if actual_hash.casefold() != WHEEL_SHA256.casefold():
        raise SystemExit(
            f"Bundled wheel hash mismatch: expected {WHEEL_SHA256}, got {actual_hash}"
        )

    provenance = runtime_provenance()
    ready = (
        installed_version() == PACKAGE_VERSION
        and provenance_expected(provenance)
        and not missing_modules()
    )
    print("Global Python:", sys.executable)
    print("Wheel:", wheel)
    print("Wheel SHA256:", actual_hash)
    print("Runtime:", json.dumps(provenance, ensure_ascii=False))
    print("Missing modules:", missing_modules() or "<none>")
    if ready and not args.force:
        print(f"{PACKAGE_NAME} {PACKAGE_VERSION} is ready globally.")
        return 0

    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        "--force-reinstall",
        str(wheel),
    ]
    print("Command:", subprocess.list2cmdline(command))
    if args.dry_run:
        return 0
    result = subprocess.run(command, check=False)
    if result.returncode:
        return result.returncode
    verified = runtime_provenance()
    if not provenance_expected(verified):
        raise SystemExit(
            "Global runtime provenance is wrong: "
            + json.dumps(verified, ensure_ascii=False)
        )
    print(f"{PACKAGE_NAME} {PACKAGE_VERSION} installed and verified globally.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
