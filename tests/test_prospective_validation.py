from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from data_quality_gate import validate_pretrade_candles
from prospective_validation import (
    ENABLED_ENV,
    build_prospective_probability_run,
    load_frozen_candidate,
    prospective_validation_enabled,
)
from m6_predictive_rules import (
    ACTIVE_EVIDENCE_FAMILIES,
    ACTIVE_PREDICTIVE_RULE_IDS,
)


ANALYSIS_AT = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
HOUR_MS = 3_600_000


def proposal(entry_type: str = "market"):
    return SimpleNamespace(
        symbol="BTCUSDT",
        side="long",
        entry=100.0,
        take_profit=103.0,
        stop_loss=98.0,
        entry_type=entry_type,
        time_horizon="intraday_wide",
        margin=100.0,
        leverage=2.0,
    )


def snapshot() -> dict:
    return {
        "analysis_at": ANALYSIS_AT.isoformat(),
        "evaluation_horizon_seconds": 24 * 60 * 60,
        "evaluation_expires_at": (
            ANALYSIS_AT + timedelta(days=1)
        ).isoformat(),
    }


def raw_candles() -> list[list]:
    count = 61 * 24 + 1
    final_close_ms = int(ANALYSIS_AT.timestamp() * 1000)
    first_close_ms = final_close_ms - (count - 1) * HOUR_MS
    rows = []
    for index in range(count):
        close_time = first_close_ms + index * HOUR_MS
        close = 100.0 + 0.01 * ((index % 17) - 8) + index * 0.0005
        rows.append(
            [
                close_time - HOUR_MS + 1,
                str(close - 0.02),
                str(close + 0.08),
                str(close - 0.08),
                str(close),
                "10",
                close_time,
            ]
        )
    return rows


def paged_loader(rows: list[list]):
    def loader(
        symbol,
        interval,
        limit,
        start_time_ms=None,
        end_time_ms=None,
    ):
        selected = [
            row
            for row in rows
            if (start_time_ms is None or row[0] >= start_time_ms)
            and (end_time_ms is None or row[0] <= end_time_ms)
        ]
        return selected[:limit]

    return loader


def live_rule_context() -> dict:
    end = int(ANALYSIS_AT.timestamp() * 1000)
    start = end - 24 * HOUR_MS
    return {
        "horizon_seconds": 24 * 60 * 60,
        "interval_seconds": 60 * 60,
        "request_cutoff_at": ANALYSIS_AT.isoformat(),
        "request_cutoff_ms": end,
        "captured_at_ms": end + 100,
        "taker_history": [
            {
                "timestamp": start + index * HOUR_MS,
                "buyVol": str(10 + index / 10),
                "sellVol": str(9 + index / 20),
            }
            for index in range(24)
        ],
        "open_interest_history": [
            {
                "timestamp": start + index * HOUR_MS,
                "sumOpenInterest": str(1000 + index),
            }
            for index in range(25)
        ],
        "futures_book": {
            "bidPrice": "99.99",
            "askPrice": "100.01",
            "receivedAt": end - 90,
        },
        "spot_book": {
            "bidPrice": "99.97",
            "askPrice": "99.99",
            "receivedAt": end - 80,
        },
        "spot_info": {
            "symbols": [{"symbol": "BTCUSDT", "status": "TRADING"}]
        },
        "depth": {
            "bids": [
                [str(99.99 - index * 0.01), "10"]
                for index in range(100)
            ],
            "asks": [
                [str(100.01 + index * 0.01), "10"]
                for index in range(100)
            ],
        },
        "funding_snapshot": {
            "lastFundingRate": "0.0001",
            "markPrice": "100.0",
            "indexPrice": "99.98",
            "nextFundingTime": end + 8 * HOUR_MS,
            "time": end - 70,
        },
        "funding_info": {
            "symbol": "BTCUSDT",
            "fundingIntervalHours": 8,
        },
        "funding_history": [
            {
                "fundingTime": end - (60 - index) * 8 * HOUR_MS,
                "fundingRate": str(0.00001 + index * 0.000001),
            }
            for index in range(60)
        ],
        "global_long_short_history": [
            {
                "timestamp": end - (60 - index) * HOUR_MS,
                "longShortRatio": str(0.8 + index * 0.005),
                "longAccount": str(
                    (0.8 + index * 0.005)
                    / (1.8 + index * 0.005)
                ),
                "shortAccount": str(
                    1.0 / (1.8 + index * 0.005)
                ),
            }
            for index in range(61)
        ],
        "market_breadth_assets": [
            {
                "id": f"asset-{index}",
                "symbol": f"A{index}",
                "market_cap_rank": index + 1,
                "last_updated": datetime.fromtimestamp(
                    (end - 1000 - index) / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                "price_change_percentage_1h_in_currency": index - 50,
                "price_change_percentage_24h_in_currency": index - 45,
                "price_change_percentage_7d_in_currency": index - 55,
            }
            for index in range(100)
        ],
        "fear_greed_history": [
            {
                "value": str(20 + index),
                "value_classification": "test",
                "timestamp": str(
                    (end - (60 - index) * 24 * HOUR_MS) // 1000
                ),
            }
            for index in range(61)
        ],
        "liquidation_context": {
            "available": True,
            "status": "available",
            "reason": None,
            "provider": "hyperperps",
            "scope": "hyperliquid",
            "symbol": "BTC",
            "schema": "hyperperps.whale-heatmap.v4",
            "as_of": ANALYSIS_AT.isoformat(),
            "age_seconds": 60,
            "reference_price": 100,
            "market_price": 100,
            "reference_basis_pct": 0,
            "sample_size": 2500,
            "clusters_above": [
                {
                    "position_side": "short",
                    "price": 102,
                    "notional_usd": 4_000_000,
                    "wallet_count": 10,
                }
            ],
            "clusters_below": [
                {
                    "position_side": "long",
                    "price": 99,
                    "notional_usd": 3_000_000,
                    "wallet_count": 8,
                }
            ],
            "cascade_mass": {
                "long": {
                    "within_1pct": 1_000_000,
                    "within_2pct": 3_000_000,
                    "within_5pct": 4_000_000,
                },
                "short": {
                    "within_1pct": 2_000_000,
                    "within_2pct": 4_000_000,
                    "within_5pct": 5_000_000,
                },
            },
            "short_to_long_mass_ratio_2pct": 4 / 3,
            "net_oi_skew": 0.1,
            "crowd_leverage": {
                "long_avg": 18,
                "short_avg": 20,
            },
        },
    }


class ProspectiveValidationTests(unittest.TestCase):
    def test_complete_closed_history_runs_m5_and_remediated_m6(self):
        result = build_prospective_probability_run(
            proposal(),
            snapshot(),
            loader=paged_loader(raw_candles()),
            analysis_id="prospective-test",
        )

        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["production_effect"], "none")
        self.assertEqual(
            result["m6_result"]["engine_version"],
            "M6-R1-internal-probability-engine-v0.1",
        )
        self.assertEqual(
            result["m6_result"]["coefficient_artifact_id"],
            "M6-HORIZON-INTRADAY-WIDE-PARTIAL-POOL-v0.1",
        )
        self.assertEqual(
            result["m6_result"]["calibration"]["time_horizon"],
            "intraday_wide",
        )
        self.assertIn(
            "tp_before_sl_within_horizon",
            result["m6_result"]["decision_probabilities"],
        )
        self.assertAlmostEqual(
            sum(result["m6_result"]["probabilities"].values()),
            1.0,
            places=12,
        )
        self.assertLessEqual(
            datetime.fromisoformat(result["data_cutoff_at"]),
            ANALYSIS_AT,
        )
        self.assertEqual(
            result["feature_snapshot"]["return_count_per_horizon"],
            24,
        )
        artifact = load_frozen_candidate()["coefficient_artifact"]
        self.assertEqual(
            artifact["coefficients"]["tp"][
                "directional_path_efficiency_h"
            ],
            0.0,
        )
        self.assertEqual(
            artifact["coefficients"]["sl"][
                "directional_path_efficiency_h"
            ],
            0.0,
        )
        required = {
            "M4-RULE-HORIZON-SAMPLING-001",
            "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
        }
        statuses = {
            trace["rule_id"]: trace["status"]
            for trace in result["m5_analysis"]["traces"]
        }
        self.assertTrue(all(statuses[rule_id] == "evaluated" for rule_id in required))

    def test_pending_entry_is_recorded_as_blocked(self):
        result = build_prospective_probability_run(
            proposal("pending"),
            snapshot(),
            loader=lambda *args, **kwargs: self.fail("loader must not run"),
            analysis_id="pending-test",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["block_code"], "m5_market_entry_required")
        self.assertIsNone(result["m6_result"])

    def test_invalid_candle_grid_blocks_before_rule_execution(self):
        rows = raw_candles()
        middle = len(rows) // 2
        rows[middle][0] += 1
        rows[middle][6] += 1

        result = build_prospective_probability_run(
            proposal(),
            snapshot(),
            loader=paged_loader(rows),
            analysis_id="invalid-grid-test",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            result["block_code"],
            "pretrade_candle_integrity_failed",
        )
        quality = result["details"]["data_quality"]
        self.assertEqual(quality["validation_pass_count"], 1)
        self.assertEqual(quality["status"], "blocked")
        self.assertEqual(quality["traces"][1]["status"], "failed")
        self.assertIn(
            "gapped_or_misaligned_candles",
            quality["traces"][1]["reason_codes"],
        )
        self.assertIsNone(result["m5_analysis"])

    def test_candle_quality_gate_runs_exactly_once_per_analysis(self):
        with patch(
            "m5_input_assembly.validate_pretrade_candles",
            wraps=validate_pretrade_candles,
        ) as quality_gate:
            result = build_prospective_probability_run(
                proposal(),
                snapshot(),
                loader=paged_loader(raw_candles()),
                analysis_id="single-quality-pass-test",
            )

        self.assertEqual(result["status"], "evaluated")
        quality_gate.assert_called_once()

    def test_live_context_executes_every_rule_branch_and_m6_uses_m5(self):
        result = build_prospective_probability_run(
            proposal(),
            snapshot(),
            loader=paged_loader(raw_candles()),
            analysis_id="integrated-live-test",
            active_output=True,
            live_context=live_rule_context(),
        )

        self.assertEqual(result["status"], "evaluated")
        self.assertEqual(result["m5_analysis"]["rule_count"], 27)
        self.assertEqual(
            result["m5_analysis"]["status_counts"],
            {
                "evaluated": 22,
                "blocked": 3,
                "not_applicable": 1,
                "deferred": 1,
                "error": 0,
            },
        )
        statuses = {
            trace["rule_id"]: trace
            for trace in result["m5_analysis"]["traces"]
        }
        for rule_id in (
            "M4-RULE-PATH-STRUCTURE-001",
            "M4-RULE-PRIOR-EXTREMA-001",
            "M4-RULE-VOLATILITY-RANK-001",
            "M4-RULE-MTF-HIERARCHY-001",
            "M4-RULE-AGGRESSOR-IMBALANCE-001",
            "M4-RULE-OPEN-INTEREST-CHANGE-001",
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            "M4-RULE-MARK-INDEX-PREMIUM-001",
            "M4-RULE-FUNDING-STATE-001",
            "M4-RULE-DERIVATIVES-CONTEXT-001",
            "M4-RULE-QUOTED-SPREAD-001",
            "M4-RULE-DEPTH-SWEEP-001",
            "M4-RULE-EVALUATION-READINESS-001",
        ):
            self.assertEqual(statuses[rule_id]["status"], "evaluated")
        self.assertEqual(
            statuses["M4-RULE-EXPONENTIAL-SMOOTHER-001"]["status"],
            "not_applicable",
        )
        self.assertEqual(
            statuses["M4-RULE-FEE-SCENARIOS-001"]["reason_codes"],
            ("missing_commission_rate",),
        )
        self.assertEqual(
            statuses["M4-RULE-FUNDING-CASHFLOW-001"]["status"],
            "deferred",
        )
        self.assertEqual(
            result["feature_snapshot"]["source_m5_analysis_id"],
            "integrated-live-test:m5-pre-probability",
        )
        self.assertEqual(
            result["m6_result"]["core_result"]["trace"]["m5_analysis_id"],
            "integrated-live-test:m5-pre-probability",
        )
        self.assertEqual(len(result["m5_rule_effects"]), 27)
        self.assertEqual(
            result["m5_rule_effects"][
                "M4-RULE-AGGRESSOR-IMBALANCE-001"
            ]["probability_effect_reason"],
            "owner_authorized_active_rule_with_live_data",
        )
        self.assertEqual(
            len(
                result["feature_snapshot"][
                    "active_predictive_rule_ids"
                ]
            ),
            11,
        )
        self.assertEqual(
            result["m5_rule_effects"][
                "M4-RULE-QUOTED-SPREAD-001"
            ]["probability_effect"],
            "separate_economic_layer",
        )
        for rule_id in ACTIVE_PREDICTIVE_RULE_IDS:
            effect = result["m5_rule_effects"][rule_id]
            self.assertIn("ablation_probability_delta", effect)
            self.assertIn(
                "ablation_probabilities_without_rule",
                effect,
            )
            self.assertAlmostEqual(
                sum(
                    effect[
                        "ablation_probabilities_without_rule"
                    ].values()
                ),
                1.0,
            )
            self.assertIn("family_ablation", effect)
        self.assertEqual(
            set(
                result["m6_result"][
                    "evidence_family_ablation"
                ]
            ),
            set(ACTIVE_EVIDENCE_FAMILIES),
        )
        observations = result["observational_rule_traces"]
        self.assertEqual(observations["status"], "evaluated_shadow")
        self.assertEqual(len(observations["traces"]), 16)
        self.assertEqual(observations["evaluated_rule_count"], 16)
        self.assertTrue(
            all(
                trace["probability_effect"]
                == "none_shadow_observation"
                for trace in observations["traces"]
            )
        )
        quality = result["data_quality"]
        self.assertEqual(quality["status"], "valid")
        self.assertEqual(quality["validation_pass_count"], 1)
        self.assertEqual(len(quality["traces"]), 2)
        self.assertTrue(
            all(trace["status"] == "passed" for trace in quality["traces"])
        )
        self.assertTrue(
            all(
                trace["probability_effect"] == "none_data_quality_gate"
                for trace in quality["traces"]
            )
        )
        self.assertEqual(
            result["feature_snapshot"]["data_quality"]["report_sha256"],
            quality["report_sha256"],
        )
        self.assertEqual(
            statuses["M4-RULE-LOG-RETURNS-001"]["outputs"][
                "data_quality_report_sha256"
            ],
            quality["report_sha256"],
        )

    def test_insufficient_depth_blocks_execution_not_market_probability(self):
        complete_context = live_rule_context()
        complete = build_prospective_probability_run(
            proposal(),
            snapshot(),
            loader=paged_loader(raw_candles()),
            analysis_id="complete-depth-test",
            active_output=True,
            live_context=complete_context,
        )
        shallow_context = live_rule_context()
        shallow_context["depth"]["asks"] = [
            [price, "0.001"]
            for price, _ in shallow_context["depth"]["asks"]
        ]
        shallow = build_prospective_probability_run(
            proposal(),
            snapshot(),
            loader=paged_loader(raw_candles()),
            analysis_id="shallow-depth-test",
            active_output=True,
            live_context=shallow_context,
        )

        self.assertEqual(shallow["status"], "evaluated")
        self.assertEqual(
            shallow["m6_result"]["probabilities"],
            complete["m6_result"]["probabilities"],
        )
        traces = {
            trace["rule_id"]: trace
            for trace in shallow["m5_analysis"]["traces"]
        }
        depth = traces["M4-RULE-DEPTH-SWEEP-001"]
        self.assertEqual(depth["status"], "evaluated")
        self.assertLess(depth["outputs"]["fill_ratio"], 1.0)
        self.assertIsNone(depth["outputs"]["complete_vwap"])
        self.assertEqual(
            depth["outputs"]["availability_status"],
            "insufficient_visible_depth",
        )
        readiness = traces["M4-RULE-EVALUATION-READINESS-001"]
        self.assertEqual(
            readiness["outputs"]["statuses"]["entry_execution"],
            "blocked",
        )
        self.assertEqual(
            shallow["m5_rule_effects"]["M4-RULE-DEPTH-SWEEP-001"][
                "probability_effect"
            ],
            "separate_economic_layer",
        )

    def test_environment_kill_switch_is_explicit(self):
        with patch.dict(os.environ, {ENABLED_ENV: "false"}):
            self.assertFalse(prospective_validation_enabled())
        with patch.dict(os.environ, {ENABLED_ENV: "true"}):
            self.assertTrue(prospective_validation_enabled())

    def test_schema_is_private_and_append_only(self):
        schema = Path("supabase/schema.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS m6_prospective_runs", schema)
        self.assertIn("m6_prospective_runs_no_update", schema)
        self.assertIn("m6_prospective_runs_no_delete", schema)
        self.assertIn(
            "REVOKE ALL PRIVILEGES ON TABLE public.m6_prospective_runs "
            "FROM anon, authenticated",
            schema,
        )


if __name__ == "__main__":
    unittest.main()
