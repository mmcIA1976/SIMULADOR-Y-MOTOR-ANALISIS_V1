from __future__ import annotations

import argparse

from nested_horizon_evaluation import (
    build_nested_dataset,
    build_protocol,
    evaluate_horizon_value,
    validate_nested_dataset,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=("protocol", "build", "validate", "evaluate", "all"),
    )
    args = parser.parse_args()
    if args.command in {"protocol", "all"}:
        result = build_protocol()
        print(f"PROTOCOL_SHA256={result['canonical_payload_sha256']}")
    if args.command in {"build", "all"}:
        result = build_nested_dataset()
        print(f"NESTED_DATASET_SHA256={result['dataset_sha256']}")
    if args.command in {"validate", "all"}:
        result = validate_nested_dataset()
        print(f"NESTED_DATASET_VALID={result['valid']}")
        print(f"NESTED_VALIDATION_SHA256={result['canonical_payload_sha256']}")
    if args.command in {"evaluate", "all"}:
        result = evaluate_horizon_value()
        print(f"HORIZON_VALUE_SHA256={result['canonical_payload_sha256']}")
        print(f"HORIZON_VALUE_DECISION={result['decision']}")


if __name__ == "__main__":
    main()
