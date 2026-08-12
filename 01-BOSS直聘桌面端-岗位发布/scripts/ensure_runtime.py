"""Install or verify the bundled boss-zhipin-automation wheel."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


PACKAGE_NAME = "boss-zhipin-automation"
PACKAGE_VERSION = "0.8.0"
WHEEL_NAME = "boss_zhipin_automation-0.8.0-py3-none-any.whl"
WHEEL_SHA256 = "fa0fbf1ed0bb9ec31730dfd55af55e6344f4ca4fdda919e236e2c338ab050ce9"
EXPECTED_BUILD_ID = "boss-job-publishing-20260812-internship-social-campus-parttime-v1"
EXPECTED_SELECTOR_PROFILE = "boss-1.7.4.963-native-uia-four-recruitment-v1"
REQUIRED_MODULES = ("pywinauto", "psutil", "PIL", "win32api", "win32gui", "comtypes")


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


def missing_modules() -> list[str]:
    return [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]


def missing_modules_in_fresh_python() -> list[str]:
    script = (
        "import importlib.util, json; "
        f"names={REQUIRED_MODULES!r}; "
        "print(json.dumps([n for n in names if importlib.util.find_spec(n) is None]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(
            "Could not verify runtime modules in a fresh Python process: "
            + result.stderr.strip()
        )
    return list(json.loads(result.stdout))


def installed_version() -> str | None:
    try:
        return importlib.metadata.version(PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_provenance_in_fresh_python() -> dict[str, str]:
    script = """
import importlib.metadata
import json
from pathlib import Path
import boss_zhipin
from boss_zhipin.uielements import SELECTOR_PROFILE
print(json.dumps({
    "distribution_version": importlib.metadata.version("boss-zhipin-automation"),
    "runtime_version": getattr(boss_zhipin, "__version__", ""),
    "runtime_build_id": getattr(boss_zhipin, "RUNTIME_BUILD_ID", ""),
    "selector_profile": SELECTOR_PROFILE,
    "module_path": str(Path(boss_zhipin.__file__).resolve()),
}, ensure_ascii=False))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        return {"probe_error": result.stderr.strip() or result.stdout.strip()}
    return dict(json.loads(result.stdout))


def provenance_is_expected(provenance: dict[str, str]) -> bool:
    return (
        provenance.get("distribution_version") == PACKAGE_VERSION
        and provenance.get("runtime_version") == PACKAGE_VERSION
        and provenance.get("runtime_build_id") == EXPECTED_BUILD_ID
        and provenance.get("selector_profile") == EXPECTED_SELECTOR_PROFILE
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Reinstall even when the correct version is ready.")
    parser.add_argument("--no-deps", action="store_true", help="Do not let pip install runtime dependencies.")
    parser.add_argument("--dry-run", action="store_true", help="Print the action without changing the environment.")
    parser.add_argument("--inspect", action="store_true", help="Print a read-only BOSS environment report after verification.")
    args = parser.parse_args()

    if not ((3, 11) <= sys.version_info[:2] < (3, 14)):
        raise SystemExit("Use Python 3.11, 3.12, or 3.13; Python 3.12 is recommended.")

    wheel = wheel_path()
    if not wheel.is_file():
        raise SystemExit(f"Bundled wheel not found: {wheel}")
    actual_hash = file_sha256(wheel)
    if actual_hash.casefold() != WHEEL_SHA256.casefold():
        raise SystemExit(
            f"Bundled wheel hash mismatch: expected {WHEEL_SHA256}, got {actual_hash}"
        )

    current = installed_version()
    missing = missing_modules()
    provenance = runtime_provenance_in_fresh_python()
    ready = (
        current == PACKAGE_VERSION
        and not missing
        and provenance_is_expected(provenance)
    )
    print("Python:", sys.executable)
    print("Wheel:", wheel)
    print("Wheel SHA256:", actual_hash)
    print("Installed version:", current or "<not installed>")
    print("Fresh-process runtime:", json.dumps(provenance, ensure_ascii=False))
    print("Missing modules:", ", ".join(missing) if missing else "<none>")

    if ready and not args.force:
        print(f"{PACKAGE_NAME} {PACKAGE_VERSION} is ready.")
    else:
        command = [sys.executable, "-m", "pip", "install", "--upgrade"]
        if args.force:
            command.append("--force-reinstall")
        if args.no_deps:
            command.append("--no-deps")
        command.append(str(wheel))
        print("Command:", subprocess.list2cmdline(command))
        if args.no_deps and missing:
            print("Warning: --no-deps leaves required modules missing:")
            for name in missing:
                print("-", name)
        if args.dry_run:
            return 0
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
        if installed_version() != PACKAGE_VERSION:
            raise SystemExit("pip finished, but the expected package version is not installed")
        # pywin32 adds its win32 directory through a .pth file. A fresh Python
        # process is required to observe it after installation.
        still_missing = missing_modules_in_fresh_python()
        if still_missing:
            raise SystemExit(
                "Installation finished, but modules are still missing: "
                + ", ".join(still_missing)
            )
        verified_provenance = runtime_provenance_in_fresh_python()
        if not provenance_is_expected(verified_provenance):
            raise SystemExit(
                "Installation finished, but fresh-process runtime provenance "
                f"is wrong: {json.dumps(verified_provenance, ensure_ascii=False)}"
            )
        print(f"Installed {PACKAGE_NAME} {PACKAGE_VERSION}.")

    if args.inspect:
        from boss_zhipin import BossJobs

        print(BossJobs.inspect_environment().as_dict())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
