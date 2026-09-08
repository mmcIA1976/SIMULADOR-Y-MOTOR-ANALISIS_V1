from __future__ import annotations

import json

from audit_real_closed_rule_evidence import run_real_closed_audit, write_outputs


def main() -> None:
    payload = run_real_closed_audit()
    write_outputs(payload)
    print(
        json.dumps(
            {
                "audit_version": payload["audit_version"],
                "audit_sha256": payload["audit_sha256"],
                "closed_operations": payload["inventory"]["closed_operations"],
                "resolved_unambiguous": payload["inventory"][
                    "resolved_unambiguous"
                ],
                "current_engine_closed_operations": payload[
                    "current_engine_real_cohort"
                ]["closed_operations"],
                "decision_summary": payload["decision_summary"],
                "production_effect": payload["production_effect"],
                "supabase_writes": payload["supabase_writes"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
