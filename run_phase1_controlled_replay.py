from __future__ import annotations

import argparse

from phase1_controlled_replay import (
    audit_frozen_current_engine,
    build_controlled_dataset,
    build_freeze_manifest,
    download_all_archives,
    evaluate_controlled_rules,
    finalize_phase1_decision,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "freeze",
            "download",
            "build",
            "evaluate",
            "audit-current",
            "finalize",
            "all",
        ),
    )
    args = parser.parse_args()
    if args.command in {"freeze", "all"}:
        result = build_freeze_manifest()
        print(f"FREEZE_SHA256={result['canonical_payload_sha256']}")
    if args.command in {"download", "all"}:
        result = download_all_archives()
        print(f"ARCHIVE_SHA256={result['canonical_payload_sha256']}")
    if args.command in {"build", "all"}:
        result = build_controlled_dataset()
        print(f"DATASET_SHA256={result['dataset_sha256']}")
    if args.command in {"evaluate", "all"}:
        result = evaluate_controlled_rules()
        print(f"VALIDATION_SHA256={result['canonical_payload_sha256']}")
        print(f"SUPPORTED_RULES={result['supported_rule_count']}")
    if args.command in {"audit-current", "all"}:
        result = audit_frozen_current_engine()
        print(f"CURRENT_ENGINE_AUDIT_SHA256={result['canonical_payload_sha256']}")
        print(f"CURRENT_ENGINE_ALL_HORIZONS_SUPPORTED={result['all_horizons_supported']}")
    if args.command in {"finalize", "all"}:
        result = finalize_phase1_decision()
        print(f"FINAL_DECISION_SHA256={result['canonical_payload_sha256']}")
        print(f"FINAL_DECISION={result['decision']}")


if __name__ == "__main__":
    main()
