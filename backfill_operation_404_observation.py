from __future__ import annotations

from datetime import datetime, timezone

from db import close_pool, connect
from operation_observation_learning import (
    create_or_get_observation_session,
    ensure_operation_observation_tables,
    observation_session_report,
    persist_exit_counterfactual,
    persist_observation_checkpoint,
    update_reconstructed_session_summary,
    unified_predictive_inventory,
)


OPERATION_ID = 404
REPORTED_CHECKPOINTS = 47
FINAL_PNL = 48.6487

# These are only the checkpoints whose numeric headline survived in the thread
# history. They intentionally remain non-formal because their complete engine
# and rule snapshots were never persisted at observation time.
CHECKPOINTS = (
    (16, "01a0777e-61fb-7b41-b9d1-f9fe4da6ea51", "2026-09-06T16:12:46+00:00", 79708.1, -9.61, 133.1, 49.2, 50.8, "hold", False),
    (17, "01a077b9-e89d-7e52-b0a1-ce8be06d4e53", "2026-09-06T17:17:47+00:00", 79644.6, -6.41, 132.0, 50.2, 49.7, "hold", False),
    (18, "01a077e1-be27-7461-9e51-1b45bc95d938", "2026-09-06T18:01:18+00:00", 79721.7, -10.29, 131.3, 43.1, 56.8, "watch", False),
    (19, "01a07a8e-7567-7eb1-a08e-9c33052d55d1", "2026-09-07T06:29:11+00:00", 79671.9, -7.79, 118.8, 47.3, 52.6, "hold", False),
    (20, "01a07aa3-0ffd-7be0-bbe6-c6d8136369d1", "2026-09-07T06:51:42+00:00", 79635.0, -5.93, 118.4, 52.5, 47.4, "unreviewed", False),
    (21, "01a07ab9-f4eb-71b0-acd5-89390b592338", "2026-09-07T07:16:42+00:00", 79583.6, -3.35, 118.0, 55.6, 44.3, "unreviewed", False),
    (22, "01a07ace-1a89-76d3-a95d-f5d4c3b5fe5b", "2026-09-07T07:38:42+00:00", 79238.0, 14.04, 117.7, 69.7, 30.3, "unreviewed", False),
    (23, "01a07ae2-40a4-71f2-acd1-c77f6cb37e40", "2026-09-07T08:00:43+00:00", 79367.4, 7.53, 117.3, 64.8, 35.1, "unreviewed", False),
    (24, "01a07af6-daa9-7840-be51-abc34c11f303", "2026-09-07T08:23:13+00:00", 79427.0, 4.53, 116.9, 60.7, 39.3, "unreviewed", False),
    (25, "01a07b0b-757c-7062-a3af-f172e81fbea2", "2026-09-07T08:45:43+00:00", 79450.4, 3.36, 116.6, 59.7, 40.3, "protect", True),
    (26, "01a07b2c-6d2d-7442-ae16-0c84a97a9f3c", "2026-09-07T09:21:44+00:00", 79458.1, 2.97, 115.9, 61.2, 38.7, "unreviewed", False),
    (27, "01a07b44-3c16-7d52-9f56-73950ee93865", "2026-09-07T09:47:44+00:00", 79381.5, 6.82, 115.5, 64.6, 35.4, "unreviewed", False),
    (28, "01a07b58-d6ec-7650-9dbf-cc74ac572e54", "2026-09-07T10:10:14+00:00", 79328.5, 9.49, 115.1, 66.9, 33.0, "unreviewed", False),
    (29, "01a07b6d-715b-7280-a2f2-63450e1c8027", "2026-09-07T10:32:45+00:00", 79378.6, 6.97, 114.8, 63.8, 36.1, "watch", False),
    (30, "01a07b82-f6ef-7312-b9e6-c2c772f20ac6", "2026-09-07T10:56:15+00:00", 79325.8, 9.62, 114.4, 63.9, 36.0, "hold", False),
    (31, "01a07b99-66a1-7d03-9b95-bb45020493f0", "2026-09-07T11:20:46+00:00", 79403.9, 5.69, 114.0, 59.3, 40.6, "watch", False),
    (32, "01a07bae-018a-7c91-8f5e-3eff2d864b50", "2026-09-07T11:43:16+00:00", 79385.2, 6.64, 113.6, 58.5, 41.4, "protect", True),
    (33, "01a07bc2-9c95-7cd3-85df-858f0ab99d1c", "2026-09-07T12:05:46+00:00", 79390.0, 6.39, 113.2, 57.2, 42.7, "protect", False),
    (34, "01a07bd7-3738-7081-b4dd-10ce3833864f", "2026-09-07T12:28:17+00:00", 79495.2, 1.10, 112.8, 52.4, 47.5, "protect", False),
    (35, "01a07beb-d1fa-7091-a28d-23125cb2c1aa", "2026-09-07T12:50:47+00:00", 79512.3, 0.24, 112.5, 52.0, 47.9, "protect", False),
    (36, "01a07c4a-4a9b-7a31-b3dd-1a38011c1ae8", "2026-09-07T14:33:58+00:00", 78970.1, 27.52, 110.8, 81.0, 19.0, "hold", False),
    (37, "01a07c5f-5a9d-7160-ac9e-2d752d536d8c", "2026-09-07T14:56:59+00:00", 79183.1, 16.80, 110.4, 72.7, 27.3, "hold", False),
    (38, "01a07c73-8048-7b02-ae96-b4ba29069f02", "2026-09-07T15:18:59+00:00", 79004.3, 25.80, 110.0, 80.5, 19.5, "hold", False),
    (39, "01a07c88-1b21-7a81-a776-e176283bef73", "2026-09-07T15:41:29+00:00", 78661.7, 43.03, 109.6, 93.5, 6.4, "watch", False),
    (40, "01a07c9c-b5dd-7f80-829e-5d9068b21531", "2026-09-07T16:04:00+00:00", 78864.3, 32.84, 109.3, 85.7, 14.3, "hold", False),
    (41, "01a07cb0-db77-7990-9fb2-d2a7d9dd15b6", "2026-09-07T16:26:00+00:00", 78816.5, 35.24, 108.9, 88.2, 11.8, "hold", False),
    (42, "01a07cc5-7678-7671-8762-f4cbb1ba05d7", "2026-09-07T16:48:30+00:00", 78950.0, 28.53, 108.5, 80.4, 19.5, "watch", False),
    (43, "01a07cda-1103-7b60-9183-937e5cab0249", "2026-09-07T17:11:01+00:00", 79073.6, 22.31, 108.1, 75.9, 24.1, "protect", True),
    (44, "01a07d04-a640-79e0-95e1-71315b22040a", "2026-09-07T17:57:31+00:00", 79138.0, 19.07, 107.4, 72.2, 27.7, "protect", False),
    (45, "01a07d19-b674-7b50-862a-086b7db62bf1", "2026-09-07T18:20:32+00:00", 79155.0, 18.21, 107.0, 70.4, 29.6, "protect", False),
    (46, "01a07d2d-dc2c-7ec3-ac31-d817eb179ba5", "2026-09-07T18:42:32+00:00", 79093.7, 21.30, 106.6, 72.3, 27.7, "protect", False),
    (47, "01a07fbf-310a-7481-bec7-2084fb49d07b", "2026-09-08T05:00:31.478000+00:00", 78550.0, 48.6487, 0.0, None, None, "final", False),
)


EXIT_REFERENCES = {
    25: (3.36, None, "premature_exit"),
    32: (6.64, None, "premature_exit"),
    33: (6.39, None, "premature_exit"),
    35: (0.24, None, "premature_exit"),
    39: (43.03, 40.96, "protection_plausible_but_hold_won"),
    43: (22.31, 20.24, "protected_drawdown_but_missed_profit"),
    44: (19.07, 17.00, "protected_drawdown_but_missed_profit"),
    45: (18.21, 16.14, "protected_drawdown_but_missed_profit"),
    46: (21.30, 19.23, "protected_drawdown_but_missed_profit"),
}


def probability_values(tp_percent: float | None, sl_percent: float | None):
    if tp_percent is None or sl_percent is None:
        return None, None, None
    tp = tp_percent / 100
    sl = sl_percent / 100
    return tp, sl, max(0.0, 1.0 - tp - sl)


def main() -> None:
    with connect() as db:
        ensure_operation_observation_tables(db)
        operation = db.execute(
            "SELECT * FROM operations WHERE id = ?",
            (OPERATION_ID,),
        ).fetchone()
        if operation is None:
            raise RuntimeError("operation_404_not_found")
        operation = dict(operation)
        if operation.get("status") != "CLOSED":
            raise RuntimeError("operation_404_not_closed")
        opening = db.execute(
            """
            SELECT id, engine_version, tp_probability, sl_probability,
                   range_probability
            FROM recommendations
            WHERE id = 1361 AND operation_id = ?
            """,
            (OPERATION_ID,),
        ).fetchone()
        if opening is None:
            raise RuntimeError("operation_404_opening_recommendation_missing")
        learning = db.execute(
            """
            SELECT id, evidence_status, evidence_quality,
                   evidence_candle_count, evidence_expected_candles,
                   evidence_coverage_ratio, reconstructed_plan_result,
                   r_multiple
            FROM learning_evaluations
            WHERE operation_id = ?
            """,
            (OPERATION_ID,),
        ).fetchone()
        if learning is None:
            raise RuntimeError("operation_404_learning_evaluation_missing")
        opening = dict(opening)
        learning = dict(learning)
        session = create_or_get_observation_session(
            db,
            operation=operation,
            opening_recommendation_id=int(opening["id"]),
            capture_mode="reconstructed",
            evidence_quality="reconstructed_partial",
            planned_interval_minutes=20,
            status="completed",
            started_at=operation["started_at"],
            ended_at=operation["closed_at"],
            evidence_source="codex_thread_reconstruction",
            summary={"status": "reconstruction_in_progress"},
        )

        by_number = {}
        for (
            number,
            turn_id,
            observed_at,
            price,
            pnl,
            remaining_hours,
            tp_percent,
            sl_percent,
            decision,
            candidate,
        ) in CHECKPOINTS:
            tp, sl, unresolved = probability_values(tp_percent, sl_percent)
            checkpoint = persist_observation_checkpoint(
                db,
                session_id=int(session["id"]),
                operation_id=OPERATION_ID,
                checkpoint_number=number,
                recommendation_id=None,
                observed_at=observed_at,
                source_turn_id=turn_id,
                market_price=price,
                unrealized_pnl=pnl,
                remaining_seconds=round(remaining_hours * 3600),
                tp_probability=tp,
                sl_probability=sl,
                range_probability=unresolved,
                decision=decision,
                decision_candidate=candidate,
                contract_quality="reconstructed_partial",
                evidence_source="codex_thread_reconstruction",
                context={
                    "source": "thread_heartbeat_report",
                    "source_turn_id": turn_id,
                    "reported_probability_precision": "one_decimal_percent",
                    "remaining_time_precision": "approximate_hours",
                    "raw_engine_snapshot_available": False,
                    "formal_predictive_learning_eligible": False,
                    "original_plan": {
                        "entry": float(operation["entry"]),
                        "take_profit": float(operation["take_profit"]),
                        "stop_loss": float(operation["stop_loss"]),
                        "time_horizon": operation["time_horizon"],
                    },
                },
            )
            by_number[number] = checkpoint

        closed_at = datetime.fromisoformat(
            str(operation["closed_at"]).replace("Z", "+00:00")
        )
        for number, (
            pnl_if_closed,
            protected_drawdown,
            risk_verdict,
        ) in EXIT_REFERENCES.items():
            checkpoint = by_number[number]
            observed_at = datetime.fromisoformat(
                str(checkpoint["observed_at"]).replace("Z", "+00:00")
            )
            persist_exit_counterfactual(
                db,
                checkpoint=checkpoint,
                actual_final_pnl=FINAL_PNL,
                pnl_if_closed=pnl_if_closed,
                tp_reached_after=True,
                sl_reached_after=False,
                time_to_terminal_minutes=(closed_at - observed_at).total_seconds()
                / 60,
                protected_drawdown=protected_drawdown,
                absolute_profit_verdict="hold_outperformed_close",
                risk_adjusted_verdict=risk_verdict,
                contract_quality="reconstructed_partial",
                evaluated_at=closed_at,
                evaluation={
                    "source": "operation_404_final_audit",
                    "checkpoint_number": number,
                    "actual_outcome": "take_profit",
                    "actual_final_pnl": FINAL_PNL,
                    "pnl_if_closed": pnl_if_closed,
                    "missed_profit": FINAL_PNL - pnl_if_closed,
                    "protected_drawdown": protected_drawdown,
                    "raw_path_snapshot_available": False,
                },
            )

        summary = {
            "operation": {
                "id": OPERATION_ID,
                "symbol": operation["symbol"],
                "side": operation["side"],
                "time_horizon": operation["time_horizon"],
                "entry": float(operation["entry"]),
                "take_profit": float(operation["take_profit"]),
                "stop_loss": float(operation["stop_loss"]),
                "final_pnl": float(operation["final_pnl"]),
                "close_reason": operation["close_reason"],
                "started_at": operation["started_at"],
                "closed_at": operation["closed_at"],
            },
            "opening_analysis": {
                "recommendation_id": int(opening["id"]),
                "engine_version": opening["engine_version"],
                "tp_probability": float(opening["tp_probability"]),
                "sl_probability": float(opening["sl_probability"]),
                "range_probability": float(opening["range_probability"]),
            },
            "canonical_learning_evaluation": {
                "evaluation_id": int(learning["id"]),
                "result": learning["reconstructed_plan_result"],
                "r_multiple": float(learning["r_multiple"]),
                "evidence_status": learning["evidence_status"],
                "evidence_quality": learning["evidence_quality"],
                "candles": int(learning["evidence_candle_count"]),
                "expected_candles": int(learning["evidence_expected_candles"]),
                "coverage_ratio": float(learning["evidence_coverage_ratio"]),
            },
            "checkpoint_reconstruction": {
                "reported_total": REPORTED_CHECKPOINTS,
                "structured_numeric_checkpoints": len(CHECKPOINTS),
                "not_structured_due_to_missing_numeric_contract": (
                    REPORTED_CHECKPOINTS - len(CHECKPOINTS)
                ),
                "structured_range": "404o16-404o47",
                "decision_candidates": ["404o25", "404o32", "404o43"],
                "protection_reference": "404o39",
                "contract_quality": "reconstructed_partial",
                "formal_predictive_learning_eligible": False,
            },
            "learning_conclusions": {
                "entry_model": (
                    "opening probability and late-resolution curve were coherent "
                    "with the final TP"
                ),
                "exit_model": (
                    "full-horizon entry probability must not be used directly "
                    "as a remaining-life exit probability"
                ),
                "observational_hypotheses": [
                    "EMA and order-book signals may describe local adverse path risk",
                    "liquidation zones may describe route order rather than terminal winner",
                    "absorption requires more independent episodes",
                ],
            },
        }
        update_reconstructed_session_summary(
            db,
            session_id=int(session["id"]),
            reported_checkpoint_count=REPORTED_CHECKPOINTS,
            ended_at=operation["closed_at"],
            summary=summary,
        )
        report = observation_session_report(db, OPERATION_ID)
        inventory = unified_predictive_inventory(db)

    close_pool()
    print(
        {
            "operation_id": OPERATION_ID,
            "session_code": report["session_code"],
            "reported_checkpoints": report["reported_checkpoint_count"],
            "stored_checkpoints": report["stored_checkpoints"],
            "formal_cases": report["exact_cases"],
            "decision_candidates": report["decision_candidates"],
            "exit_counterfactuals": report["exit_counterfactuals"],
            "learning_inventory": inventory,
        }
    )


if __name__ == "__main__":
    main()
