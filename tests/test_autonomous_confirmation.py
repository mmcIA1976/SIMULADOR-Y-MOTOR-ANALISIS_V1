import json
import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import autonomous_confirmation as confirmation
import autonomous_contest as contest
from tests.test_autonomous_contest import candidate, CountDb, OperationInsertDb


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.policy = contest.PARTICIPANT_POLICIES[0]
        self.start = datetime(2026, 9, 22, tzinfo=timezone.utc)

    def advance(self, minute, previous=(), edges=(.15,), symbols=("BTCUSDT",), scan_id=None):
        values = []
        for edge, symbol in zip(edges, symbols):
            item = candidate(edge=edge, symbol=symbol)
            item.analyzed_at = self.start + timedelta(minutes=minute)
            item.artifact_id = "frozen-artifact"
            item.sigma = .01
            values.append(item)
        confirmation.advance(values, self.policy, previous,
                             slot=self.start + timedelta(minutes=minute),
                             scan_run_id=scan_id or minute + 1,
                             engine_version=contest.EMPIRICAL_ENGINE_VERSION)
        return values

    def rows(self, values):
        return [dict(symbol=c.symbol, side=c.side, analyzed_at=c.analyzed_at.isoformat(),
                     artifact_id=c.artifact_id, engine_version=contest.EMPIRICAL_ENGINE_VERSION,
                     confirmation=json.loads(json.dumps(c.confirmation)))
                for c in values if c.confirmation]

    def mature(self):
        values = []
        for minute in (0, 15, 30, 45):
            values = self.advance(minute, self.rows(values))
        return values

    def test_four_controls_and_45_real_minutes_required(self):
        values = []
        for minute in (0, 15, 30):
            values = self.advance(minute, self.rows(values))
            self.assertIsNone(confirmation.select(values, self.policy))
        values = self.advance(45, self.rows(values))
        self.assertIs(confirmation.select(values, self.policy), values[0])
        self.assertEqual(values[0].confirmation["controls"], 4)
        self.assertEqual(values[0].confirmation["first_scan_run_id"], 1)

    def test_ranking_change_does_not_reset_either_eligible_candidate(self):
        values = []
        for minute in (0, 15, 30, 45):
            values = self.advance(minute, self.rows(values),
                                  edges=(.15, .16 if minute == 15 else .14),
                                  symbols=("BTCUSDT", "ETHUSDT"))
        self.assertEqual([c.confirmation["controls"] for c in values], [4, 4])
        self.assertEqual(confirmation.select(values, self.policy).symbol, "BTCUSDT")

    def test_new_higher_scoring_candidate_cannot_jump_confirmation(self):
        values = []
        for minute in (0, 15, 30):
            values = self.advance(minute, self.rows(values))
        values = self.advance(45, self.rows(values), edges=(.15, .25), symbols=("BTCUSDT", "ETHUSDT"))
        self.assertEqual(confirmation.select(values, self.policy).symbol, "BTCUSDT")
        self.assertEqual(values[1].confirmation["controls"], 1)

    def test_ineligible_proposals_have_no_tracking(self):
        values = self.advance(0, edges=(.09, .02), symbols=("BTCUSDT", "ETHUSDT"))
        self.assertTrue(all(not c.confirmation for c in values))
        stored = contest._candidate_storage_selection(CountDb(0), self.policy, self.start, values, None)
        self.assertEqual(stored, {})

    def test_threshold_loss_records_one_terminal_control_then_restarts(self):
        values = self.advance(0)
        values = self.advance(15, self.rows(values), edges=(.09,))
        self.assertEqual(values[0].confirmation["state"], "discarded")
        self.assertIsNone(confirmation.select(values, self.policy))
        values = self.advance(30, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 1)
        self.assertEqual(values[0].confirmation["first_scan_run_id"], 31)

    def test_gap_and_engine_or_artifact_changes_restart(self):
        for change in ("gap", "engine", "artifact"):
            with self.subTest(change=change):
                old = self.rows(self.advance(0))
                if change == "engine":
                    old[0]["engine_version"] = "old-engine"
                elif change == "artifact":
                    old[0]["artifact_id"] = "old-artifact"
                values = self.advance(30 if change == "gap" else 15, old)
                self.assertEqual(values[0].confirmation["controls"], 1)

    def test_late_first_scan_does_not_fake_45_minutes(self):
        values = self.advance(0)
        values[0].confirmation["first_analyzed_at"] = (self.start + timedelta(minutes=5)).isoformat()
        for minute in (15, 30, 45):
            values = self.advance(minute, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 4)
        self.assertIsNone(confirmation.select(values, self.policy))

    def test_consumed_confirmation_cannot_open_again_next_round(self):
        values = self.mature()
        confirmation.finish(values, values[0], status="opened", reason="confirmed", operation_id=123)
        self.assertEqual(values[0].confirmation["operation_id"], 123)
        self.assertEqual(values[0].confirmation["counterfactual_role"], "confirmed")
        values = self.advance(60, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 1)
        self.assertIsNone(confirmation.select(values, self.policy))

    def test_failed_execution_does_not_consume_confirmation(self):
        values = self.mature()
        confirmation.finish(values, values[0], status="no_trade", reason="price_drift", operation_id=None)
        values = self.advance(60, self.rows(values))
        self.assertIsNotNone(confirmation.select(values, self.policy))

    def test_other_bots_do_not_need_confirmation(self):
        values = self.advance(0)
        for policy in contest.PARTICIPANT_POLICIES[1:]:
            self.assertIs(confirmation.select(values, policy), contest.select_candidate(values, policy))
            fresh = candidate(edge=.15)
            confirmation.advance([fresh], policy, [], slot=self.start, scan_run_id=1, engine_version="v")
            self.assertEqual(fresh.confirmation, {})

    def test_initial_and_final_probabilities_are_not_boosted(self):
        values = self.mature()
        self.assertEqual(values[0].tp_probability, .45)
        self.assertAlmostEqual(values[0].sl_probability, .30)
        self.assertEqual(values[0].edge, .15)

    def test_provider_failure_ends_existing_tracking_without_starting_new_one(self):
        previous = self.rows(self.advance(0))
        value = candidate(edge=.15)
        value.analyzed_at = self.start + timedelta(minutes=15)
        value.analysis_status = "failed"
        value.artifact_id = None
        value.rejection_code = "provider_failed"
        confirmation.advance([value], self.policy, previous, slot=value.analyzed_at,
                             scan_run_id=2, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
        self.assertEqual(value.confirmation["state"], "discarded")
        self.assertEqual(value.confirmation["end_reason"], "provider_failed")

    def test_real_active_rule_context_fits_compact_budget(self):
        from tests.test_sequential_production_contract import synthetic_candles
        from multiscale_feature_runtime import build_stage_context
        from sequential_production_runtime import apply_target_rule_trace_scope
        from empirical_temporal_engine import load_production_artifact
        candles, at = synthetic_candles("intraday_short")
        context = build_stage_context(
            dict(symbol="BTCUSDT", side="long", entry=110., take_profit=115., stop_loss=105.,
                 time_horizon="intraday_short", horizon_seconds=14400, analysis_at=at.isoformat()), candles)
        apply_target_rule_trace_scope({"intraday_short": context}, "intraday_short", load_production_artifact())
        value = self.mature()[0]
        value.analysis_result = {"snapshot": {"stage_rule_traces": {"intraday_short": context["rule_traces"]}}}
        payload = confirmation.compact_payload(value)
        expected = {t["rule_id"] for t in context["rule_traces"] if t.get("active_probability_outputs")}
        self.assertEqual(set(payload["active_context"]), expected)
        self.assertTrue(expected)
        self.assertLess(len(json.dumps(payload, separators=(",", ":")).encode()), 1600)

    def test_compact_evidence_keeps_active_numbers_not_snapshots(self):
        value = self.mature()[0]
        value.analysis_result = {"snapshot": {"candles": ["x" * 100000], "stage_rule_traces": {
            "intraday_short": [{"rule_id": "ACTIVE", "active_probability_outputs": ["x"],
                                "outputs": {"x": .7, "raw": "z" * 100000}},
                               {"rule_id": "OBS", "outputs": {"x": 9}}]}}}
        payload = confirmation.compact_payload(value)
        self.assertEqual(payload["active_context"], {"ACTIVE": {"x": .7}})
        self.assertLess(len(json.dumps(payload).encode()), 1100)
        self.assertNotIn("candles", payload)

    def test_only_endpoints_are_sent_to_counterfactual_evaluator(self):
        values = []
        for minute in (0, 15, 30, 45):
            values = self.advance(minute, self.rows(values))
            selected = confirmation.select(values, self.policy)
            confirmation.finish(values, selected, status="opened" if selected else "no_trade",
                                reason="test", operation_id=1 if selected else None)
            db = OperationInsertDb()
            contest._persist_candidate_observations(
                db, scan_run_id=minute + 1, participant={"id": 1}, season_id=1,
                policy=self.policy, slot=self.start + timedelta(minutes=minute),
                candidates=values, selected=selected)
            params = next(params for query, params in db.calls if "INSERT INTO autonomous_candidate_observations" in query)
            self.assertEqual(params[-1], "pending" if minute in (0, 45) else "excluded")
            self.assertEqual(params[21], "confirmation")

    def test_read_is_bounded_to_previous_scan_season_and_mode(self):
        class Db:
            def execute(inner, query, params):
                self.assertIn("LIMIT 12", query)
                self.assertIn("s.dry_run = ?", query)
                self.assertNotIn("SELECT *", query)
                self.assertEqual(params, (1, 2, self.start.isoformat(), False))
                return inner
            def fetchall(inner):
                return []
        self.assertEqual(contest._previous_confirmation_rows(
            Db(), {"id": 1}, 2, self.policy, self.start + timedelta(minutes=15), False), [])

    def test_exact_endpoint_rejects_missing_minutes_and_boundary_touches(self):
        candles = [dict(open_time_ms=t, high=100.5, low=99.5, close=100.) for t in (0, 60000, 120000)]
        args = dict(start_ms=15000, end_ms=135000, side="long", entry=100., take_profit=101., stop_loss=99.)
        self.assertEqual(confirmation.evaluate_endpoint(candles, **args)["first_touch"], "unresolved")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            confirmation.evaluate_endpoint([candles[0], candles[2]], **args)
        for index in (0, 2):
            material = [dict(c) for c in candles]
            material[index]["high"] = 101.1
            outcome = confirmation.evaluate_endpoint(material, **args)
            self.assertEqual(outcome["first_touch"], "ambiguous")
            self.assertIsNone(outcome["r_multiple"])
        candles[1]["low"] = 98.9
        candles[2]["high"] = 102.
        self.assertEqual(confirmation.evaluate_endpoint(candles, **args)["first_touch"], "sl")

    def test_report_counts_episodes_not_four_independent_trades(self):
        rows, values = [], []
        for minute in (0, 15, 30, 45):
            values = self.advance(minute, self.rows(values))
            if minute == 45:
                confirmation.finish(values, values[0], status="opened", reason="test", operation_id=123)
            value = values[0]
            rows.append(dict(participant_id=1, symbol=value.symbol, side=value.side,
                             analyzed_at=value.analyzed_at, entry=100., stop_loss=99., terminal_price=101.,
                             confirmation=dict(value.confirmation), outcome_status="evaluated",
                             first_touch="sl" if minute == 0 else "tp", r_multiple=-1. if minute == 0 else 1.,
                             tp_probability=value.tp_probability))
        summary = confirmation.summarize_trials(rows, fee_per_side=.0005)
        self.assertEqual(summary["episodes"], 1)
        self.assertEqual(summary["improved"], 1)
        self.assertEqual(summary["paired_endpoints"][0]["delta_gross_r"], 2.)
        self.assertLess(summary["paired_endpoints"][0]["confirmed"]["fee_adjusted_r"], 1.)


class ScannerIntegrationTests(unittest.TestCase):
    """Real scanner transactions against a temporary in-memory SQL database.

    Only market providers and the actual trade insert are stubbed. The scan
    claims, checkpoint writes, restart state reads and quota gates run normally.
    No network connection or production database is used.
    """
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

        class Schema:
            def executescript(inner, script):
                for statement in script.split(";"):
                    if not statement.strip().startswith("CREATE TABLE"):
                        continue
                    statement = statement.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY")
                    statement = statement.replace("::jsonb", "").replace("jsonb_typeof", "json_type")
                    self.connection.execute(statement)
        contest.ensure_autonomous_storage(Schema())
        self.connection.execute("""INSERT INTO autonomous_contest_participants
            (id, code, user_id, display_name, time_horizon, policy_version, cadence_minutes,
             daily_operation_limit, max_open_positions, edge_threshold, min_tp_probability,
             max_unresolved_probability, min_analogs_per_stage, margin, leverage, symbols_json)
            VALUES (1,'auto_intraday_short',27,'Short','intraday_short','v',15,3,3,.1,.3,.55,80,100,1,'[]')""")
        self.connection.commit()
        self.opened = []
        self.start = datetime(2026, 9, 22, 0, 2, tzinfo=timezone.utc)

    def tearDown(self):
        self.connection.close()

    @contextmanager
    def connect(self):
        connection = self.connection

        class Adapter:
            def execute(inner, sql, params=()):
                return connection.execute(sql.replace("::jsonb", ""), params)
        try:
            yield Adapter()
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def scan(self, minute, *, bad=False, fail_insert=False):
        def analyze(policy, prices, at, **kwargs):
            value = candidate(edge=.09 if bad else .15)
            value.analyzed_at = at
            value.sigma = .01
            value.artifact_id = "frozen-artifact"
            return [value]

        def opening(db, **kwargs):
            if fail_insert:
                raise RuntimeError("injected_insert_failure")
            self.opened.append(kwargs["candidate"].analyzed_at)
            return 700 + len(self.opened), 900 + len(self.opened)

        with patch.object(contest, "PARTICIPANT_POLICIES", (contest.PARTICIPANT_POLICIES[0],)), \
             patch.object(contest, "ensure_contest_entries"), \
             patch.object(contest, "fresh_market_prices", return_value={s: 100. for s in contest.SYMBOLS}), \
             patch.object(contest, "_load_order_book_contexts", return_value={}), \
             patch.object(contest, "_load_liquidation_contexts", return_value={}), \
             patch.object(contest, "analyze_candidates", side_effect=analyze), \
             patch.object(contest, "_daily_operation_count", side_effect=lambda *a, **kw: len(self.opened)), \
             patch.object(contest, "_available_contest_cash", return_value=1000.), \
             patch.object(contest, "_open_selected_operation", side_effect=opening):
            return contest.run_due_scans(self.connect, lambda _: {"id": 1},
                                        dry_run=False, bootstrap=False,
                                        now=self.start + timedelta(minutes=minute))

    def test_four_scans_open_once_and_duplicate_scan_does_not_advance(self):
        for minute in (0, 15, 30):
            result = self.scan(minute)
            self.assertEqual(result["scans"][0]["reason"], "awaiting_45m_candidate_confirmation")
        self.assertEqual(self.scan(30)["scans"], [])
        self.assertEqual(self.scan(45)["scans"][0]["status"], "opened")
        self.assertEqual(self.scan(60)["scans"][0]["status"], "no_trade")
        self.assertEqual(len(self.opened), 1)
        rows = self.connection.execute("SELECT observational_json, outcome_status FROM autonomous_candidate_observations ORDER BY id").fetchall()
        self.assertEqual(len(rows), 5)
        self.assertEqual(json.loads(rows[3]["observational_json"])["confirmation"]["state"], "consumed")
        self.assertEqual([r["outcome_status"] for r in rows], ["pending", "excluded", "excluded", "pending", "pending"])

    def test_threshold_failure_prevents_open_and_restarts(self):
        self.scan(0)
        self.scan(15)
        self.scan(30, bad=True)
        self.assertEqual(self.scan(45)["scans"][0]["status"], "no_trade")
        self.assertEqual(self.opened, [])
        row = self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(row[0])["confirmation"]["controls"], 1)

    def test_failed_persistence_rolls_back_checkpoint_and_cannot_confirm_next_scan(self):
        for minute in (0, 15, 30):
            self.scan(minute)
        with self.assertLogs("autonomous_contest", level="ERROR"):
            self.assertEqual(self.scan(45, fail_insert=True)["scans"][0]["status"], "failed")
        self.assertEqual(self.scan(60)["scans"][0]["status"], "no_trade")
        self.assertEqual(self.opened, [])

    def test_endpoint_evaluator_and_report_use_actual_saved_checkpoints(self):
        for minute in (0, 15, 30, 45):
            self.scan(minute)

        def loader(symbol, interval, limit, start_time_ms, end_time_ms):
            rows = []
            for index, stamp in enumerate(range(start_time_ms, end_time_ms + 1, 60_000)):
                rows.append([stamp, 100., 101.1 if index == 1 else 100.5, 99.5,
                             100., 1., stamp + 59_999])
            return rows
        result = contest.evaluate_due_candidates(self.connect, now=self.start + timedelta(hours=6), loader=loader)
        self.assertEqual(result["evaluated_candidates"], 2)
        with self.connect() as db:
            report = contest.confirmation_trial_report(db, start_at=self.start.replace(hour=0, minute=0),
                                                       end_at=self.start + timedelta(hours=6))
        self.assertEqual(report["episodes"], 1)
        self.assertEqual(report["unchanged"], 1)
        self.assertEqual(report["paired_endpoints"][0]["confirmed"]["outcome"], "tp")
        self.assertIsNone(report["paired_endpoints"][0]["confirmed"]["fee_adjusted_r"])

    def test_three_daily_entries_without_open_position_cap(self):
        for minute in range(0, 240, 15):
            self.scan(minute)
        self.assertEqual(len(self.opened), 3)
        self.assertEqual(self.scan(240)["scans"], [])


if __name__ == "__main__":
    unittest.main()
