from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone

from limit_order_contract import (
    CONDITIONAL_OUTCOME_CLASSES,
    LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES,
    LIMIT_ORDER_CONTRACT_VERSION,
    LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY,
    LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES,
    LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS,
    LifecycleEvent,
    LimitOrderContractError,
    OperationStatus,
    build_limit_order_contract,
    compose_limit_probability_tree,
    learning_label_for_terminal_event,
    transition_target,
    validate_limit_plan,
)
from m8_evaluation import HORIZON_SECONDS


class LimitOrderContractTests(unittest.TestCase):
    def valid_contract(self, **overrides):
        values = {
            "analysis_id": "limit-contract-test",
            "symbol": "BTCUSDT",
            "side": "long",
            "time_horizon": "intraday_short",
            "analysis_at": "2026-08-04T10:00:00+02:00",
            "current_price": 100.0,
            "requested_entry": 98.0,
            "stop_loss": 96.0,
            "take_profit": 103.0,
            "trigger_condition": "price_lte",
        }
        values.update(overrides)
        return build_limit_order_contract(**values)

    def test_long_limit_requires_drop_then_expects_upward_reaction(self):
        contract = self.valid_contract()

        self.assertEqual(
            contract["contract_version"],
            LIMIT_ORDER_CONTRACT_VERSION,
        )
        self.assertEqual(contract["order"]["entry_order_type"], "limit_pullback")
        self.assertEqual(contract["order"]["direction_to_activation"], "down")
        self.assertEqual(
            contract["order"]["expected_reaction_after_activation"],
            "up",
        )

    def test_short_limit_requires_rise_then_expects_downward_reaction(self):
        contract = self.valid_contract(
            side="short",
            current_price=100,
            requested_entry=102,
            stop_loss=104,
            take_profit=97,
            trigger_condition="price_gte",
        )

        self.assertEqual(contract["order"]["direction_to_activation"], "up")
        self.assertEqual(
            contract["order"]["expected_reaction_after_activation"],
            "down",
        )

    def test_stop_breakout_and_stop_breakdown_are_outside_limit_v1(self):
        with self.assertRaisesRegex(
            LimitOrderContractError,
            "limit_v1_supports_pullback_orders_only",
        ):
            validate_limit_plan(
                side="long",
                current_price=100,
                requested_entry=102,
                stop_loss=98,
                take_profit=105,
                trigger_condition="price_gte",
            )

    def test_limit_must_be_waiting_on_the_correct_side_of_market(self):
        for entry in (100, 101):
            with self.subTest(entry=entry):
                with self.assertRaisesRegex(
                    LimitOrderContractError,
                    "limit_trigger_already_satisfied",
                ):
                    validate_limit_plan(
                        side="long",
                        current_price=100,
                        requested_entry=entry,
                        stop_loss=99,
                        take_profit=103,
                        trigger_condition="price_lte",
                    )

    def test_barrier_geometry_is_relative_to_requested_entry(self):
        with self.assertRaisesRegex(
            LimitOrderContractError,
            "invalid_barrier_geometry",
        ):
            self.valid_contract(stop_loss=99)

    def test_activation_and_outcome_use_separate_clocks(self):
        contract = self.valid_contract()
        activation = contract["windows"]["activation"]
        outcome = contract["windows"]["outcome_after_activation"]

        self.assertEqual(
            activation["horizon_seconds"],
            HORIZON_SECONDS["intraday_short"],
        )
        self.assertEqual(
            activation["starts_at"],
            "2026-08-04T08:00:00+00:00",
        )
        self.assertEqual(
            activation["expires_at"],
            "2026-08-04T12:00:00+00:00",
        )
        self.assertEqual(
            outcome["policy"],
            "fresh_selected_horizon_from_activation",
        )
        self.assertEqual(
            outcome["starts_at"],
            "actual_activation_at",
        )

    def test_analysis_timestamp_must_be_timezone_aware(self):
        with self.assertRaisesRegex(
            LimitOrderContractError,
            "analysis_at_must_be_timezone_aware",
        ):
            self.valid_contract(analysis_at=datetime(2026, 8, 4, 10, 0))

        contract = self.valid_contract(
            analysis_at=datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(
            contract["windows"]["activation"]["starts_at"],
            "2026-08-04T10:00:00+00:00",
        )

    def test_lifecycle_uses_existing_stable_operation_statuses(self):
        self.assertEqual(
            transition_target(
                OperationStatus.PENDING_ENTRY,
                LifecycleEvent.ACTIVATED,
            ),
            OperationStatus.OPEN,
        )
        self.assertEqual(
            transition_target(
                OperationStatus.OPEN,
                LifecycleEvent.TAKE_PROFIT,
            ),
            OperationStatus.CLOSED,
        )
        with self.assertRaisesRegex(
            LimitOrderContractError,
            "invalid_lifecycle_transition",
        ):
            transition_target(
                OperationStatus.PENDING_ENTRY,
                LifecycleEvent.TAKE_PROFIT,
            )

    def test_cancelled_is_censored_but_expired_is_no_activation(self):
        self.assertEqual(
            learning_label_for_terminal_event(
                LifecycleEvent.PENDING_CANCELLED
            ),
            "censored_before_activation",
        )
        self.assertEqual(
            learning_label_for_terminal_event(
                LifecycleEvent.PENDING_EXPIRED
            ),
            "not_activated_by_expiry",
        )
        self.assertNotEqual(
            learning_label_for_terminal_event(
                LifecycleEvent.PENDING_CANCELLED
            ),
            learning_label_for_terminal_event(
                LifecycleEvent.PENDING_EXPIRED
            ),
        )

    def test_probability_tree_keeps_activation_and_outcome_separate(self):
        tree = compose_limit_probability_tree(
            0.60,
            {
                "tp_first_within_outcome_horizon": 0.50,
                "sl_first_within_outcome_horizon": 0.30,
                "neither_barrier_before_outcome_expiry": 0.20,
            },
        )

        self.assertAlmostEqual(
            tree["overall"]["activation_then_tp_first"],
            0.30,
        )
        self.assertAlmostEqual(
            tree["overall"]["activation_then_sl_first"],
            0.18,
        )
        self.assertAlmostEqual(
            tree["overall"]["activation_then_neither_barrier"],
            0.12,
        )
        self.assertAlmostEqual(
            tree["overall"]["not_activated_by_expiry"],
            0.40,
        )
        self.assertTrue(math.isclose(tree["overall_mass"], 1.0))

    def test_probability_tree_rejects_wrong_schema_or_mass(self):
        with self.assertRaisesRegex(
            LimitOrderContractError,
            "probability_keys_mismatch",
        ):
            compose_limit_probability_tree(0.5, {"tp": 1.0})
        with self.assertRaisesRegex(
            LimitOrderContractError,
            "probability_mass_not_one",
        ):
            compose_limit_probability_tree(
                0.5,
                dict.fromkeys(CONDITIONAL_OUTCOME_CLASSES, 0.5),
            )

    def test_contract_is_shadow_only_and_does_not_modify_market_engine(self):
        contract = self.valid_contract()

        self.assertEqual(contract["production_effect"], "none_contract_only")
        self.assertFalse(contract["market_engine_modified"])
        self.assertFalse(contract["legacy_engine_executed"])
        self.assertEqual(
            contract["probability_spaces"]["activation"]["status"],
            "baseline_model_available_shadow_only",
        )
        self.assertEqual(
            contract["context_rule_spaces"]["probability_effect"],
            "none_until_validated_coefficients",
        )

    def test_snapshot_policy_is_compact_and_excludes_raw_feeds(self):
        persistence = self.valid_contract()["persistence"]

        self.assertEqual(
            persistence["max_new_learning_payload_bytes_per_operation"],
            LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES,
        )
        self.assertFalse(persistence["persist_raw_candles"])
        self.assertFalse(persistence["persist_raw_order_book"])
        self.assertFalse(persistence["persist_raw_liquidation_heatmap"])
        self.assertFalse(persistence["persist_every_worker_poll"])
        self.assertTrue(persistence["persist_compact_derived_features_only"])
        self.assertFalse(persistence["persist_candidate_analyses"])
        self.assertEqual(
            persistence["snapshot_byte_budgets"],
            LIMIT_ORDER_SNAPSHOT_BYTE_BUDGETS,
        )
        self.assertEqual(
            persistence["allocated_snapshot_bytes_per_operation"],
            LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES,
        )
        self.assertLess(
            LIMIT_ORDER_ALLOCATED_SNAPSHOT_BYTES,
            LIMIT_ORDER_MAX_LEARNING_PAYLOAD_BYTES,
        )
        self.assertEqual(
            persistence["max_selected_cases_per_utc_day"],
            LIMIT_ORDER_MAX_SELECTED_CASES_PER_UTC_DAY,
        )

    def test_contract_hash_is_deterministic_and_plan_specific(self):
        first = self.valid_contract()
        second = self.valid_contract()
        changed = self.valid_contract(requested_entry=97.5, stop_loss=95.5)

        self.assertEqual(first["contract_sha256"], second["contract_sha256"])
        self.assertNotEqual(
            first["contract_sha256"],
            changed["contract_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
