"""Fresh-process command runner for the bundled BOSS automation functions."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_VERSION = "0.8.0"
EXPECTED_BUILD_ID = "boss-job-publishing-20260812-internship-social-campus-parttime-v1"
EXPECTED_SELECTOR_PROFILE = "boss-1.7.4.963-native-uia-four-recruitment-v1"


def runtime() -> tuple[Any, dict[str, str]]:
    import boss_zhipin
    from boss_zhipin.uielements import SELECTOR_PROFILE

    provenance = {
        "python_executable": sys.executable,
        "module_path": str(Path(boss_zhipin.__file__).resolve()),
        "runtime_version": str(getattr(boss_zhipin, "__version__", "")),
        "distribution_version": importlib.metadata.version(
            "boss-zhipin-automation"
        ),
        "runtime_build_id": str(
            getattr(boss_zhipin, "RUNTIME_BUILD_ID", "")
        ),
        "selector_profile": SELECTOR_PROFILE,
    }
    expected = {
        "runtime_version": EXPECTED_VERSION,
        "distribution_version": EXPECTED_VERSION,
        "runtime_build_id": EXPECTED_BUILD_ID,
        "selector_profile": EXPECTED_SELECTOR_PROFILE,
    }
    mismatches = {
        key: {"expected": value, "actual": provenance.get(key)}
        for key, value in expected.items()
        if provenance.get(key) != value
    }
    if mismatches:
        raise RuntimeError(
            "BOSS runtime provenance mismatch; run ensure_runtime.py, then "
            f"start this script again. mismatches={mismatches}"
        )
    return boss_zhipin, provenance


def result_dict(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    return value


def prepare_options(module: Any, args: argparse.Namespace) -> Any:
    return module.PrepareOptions(
        restart_for_accessibility=False,
        maximize_window=not args.no_maximize,
        timeout_seconds=args.timeout,
        artifact_dir=args.artifact_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("runtime")
    subparsers.add_parser("inspect")

    open_form = subparsers.add_parser("open-form")
    open_form.add_argument("--timeout", type=float, default=30.0)
    open_form.add_argument("--artifact-dir")
    open_form.add_argument("--no-maximize", action="store_true")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--spec-file", required=True)
    prepare.add_argument("--idempotency-key", required=True)
    prepare.add_argument("--timeout", type=float, default=30.0)
    prepare.add_argument("--artifact-dir")
    prepare.add_argument("--no-maximize", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("--run-id", required=True)

    publish_reviewed = subparsers.add_parser("publish-reviewed")
    publish_reviewed.add_argument("--run-id", required=True)

    reconcile = subparsers.add_parser("reconcile")
    reconcile.add_argument("--run-id", required=True)
    return parser


def execute(args: argparse.Namespace) -> tuple[dict[str, str], Any]:
    module, provenance = runtime()
    if args.command == "runtime":
        return provenance, provenance
    if args.command == "inspect":
        return provenance, module.BossJobs.inspect_environment().as_dict()
    if args.command == "open-form":
        value = module.BossJobs.open_publish_form(
            options=prepare_options(module, args)
        )
        return provenance, value.as_dict()
    if args.command == "prepare":
        spec_path = Path(args.spec_file).expanduser().resolve()
        data = json.loads(spec_path.read_text(encoding="utf-8"))
        value = module.BossJobs.prepare_job_post(
            data,
            idempotency_key=args.idempotency_key,
            options=prepare_options(module, args),
        )
        return provenance, value.as_dict()
    if args.command == "status":
        return provenance, module.BossJobs.get_run_status(args.run_id)
    if args.command == "publish-reviewed":
        value = module.BossJobs.publish_reviewed_job(args.run_id)
        return provenance, value.as_dict()
    if args.command == "reconcile":
        value = module.BossJobs.reconcile_job_post(args.run_id)
        return provenance, value.as_dict()
    raise RuntimeError(f"unsupported command: {args.command}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        provenance, result = execute(args)
    except Exception as exc:
        error_details = (
            exc.as_dict()
            if callable(getattr(exc, "as_dict", None))
            else {
                "code": type(exc).__name__,
                "message": str(exc),
            }
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "error_details": error_details,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "runtime": provenance,
                "result": result_dict(result),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
