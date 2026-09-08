from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit_final_rule_utility import (
    DEFAULT_OUTPUT,
    DEFAULT_REPORT,
    build_report,
    run_final_audit,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Consolida operaciones cerradas y contrafactuales exactos, "
            "reconstruye las 38 reglas y emite decisiones por horizonte."
        )
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = run_final_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(build_report(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "audit_version": payload["audit_version"],
                "audit_sha256": payload["audit_sha256"],
                "closed_operations": payload["cohort"]["closed_operations_loaded"],
                "exact_counterfactuals": payload["cohort"][
                    "formal_exact_counterfactuals"
                ],
                "formal_cases": payload["episodes"]["formal_cases"],
                "effective_horizon_episodes": payload["episodes"][
                    "effective_horizon_episodes"
                ],
                "rules_classified": len(payload["rule_decisions"]),
                "decision_summary": payload["decision_summary"],
                "output": str(args.output),
                "report": str(args.report),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
