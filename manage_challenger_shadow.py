from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from db import close_pool, connect
from shadow_runtime import (
    disable_shadow,
    read_current_shadow_config,
    register_model_artifact,
    rollback_shadow,
    select_shadow_model,
)


def current_commit_sha() -> str | None:
    railway_sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "").strip()
    if railway_sha:
        return railway_sha
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Gestion append-only del challenger en sombra."
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status")

    disable = commands.add_parser("disable")
    disable.add_argument("--reason", required=True)
    disable.add_argument("--requested-by", required=True)

    select = commands.add_parser("select")
    select.add_argument("--model-version", required=True)
    select.add_argument("--reason", required=True)
    select.add_argument("--requested-by", required=True)

    rollback = commands.add_parser("rollback")
    rollback.add_argument("--reason", required=True)
    rollback.add_argument("--requested-by", required=True)

    register = commands.add_parser("register-model")
    register.add_argument("--artifact", required=True)
    register.add_argument("--reason", required=True)
    register.add_argument("--registered-by", required=True)
    return root


def main() -> int:
    args = parser().parse_args()
    commit_sha = current_commit_sha()
    try:
        with connect() as db:
            if args.command == "status":
                result = read_current_shadow_config(db)
            elif args.command == "disable":
                event_id = disable_shadow(
                    db,
                    reason=args.reason,
                    requested_by=args.requested_by,
                    code_commit_sha=commit_sha,
                )
                result = {"status": "disabled", "config_event_id": event_id}
            elif args.command == "select":
                event_id = select_shadow_model(
                    db,
                    model_version=args.model_version,
                    reason=args.reason,
                    requested_by=args.requested_by,
                    code_commit_sha=commit_sha,
                )
                result = {
                    "status": "selected",
                    "config_event_id": event_id,
                    "model_version": args.model_version,
                }
            elif args.command == "rollback":
                event_id = rollback_shadow(
                    db,
                    reason=args.reason,
                    requested_by=args.requested_by,
                    code_commit_sha=commit_sha,
                )
                result = {"status": "rolled_back", "config_event_id": event_id}
            else:
                artifact = json.loads(
                    Path(args.artifact).read_text(encoding="utf-8")
                )
                artifact_id = register_model_artifact(
                    db,
                    artifact,
                    reason=args.reason,
                    registered_by=args.registered_by,
                )
                result = {
                    "status": "registered",
                    "artifact_id": artifact_id,
                    "model_version": artifact["model_version"],
                }
        print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
