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
        for minute in (0, 15, 30):
            values = self.advance(minute, self.rows(values))
        return values

    def test_three_controls_and_30_real_minutes_required(self):
        values = []
        for minute in (0, 15):
            values = self.advance(minute, self.rows(values))
            self.assertIsNone(confirmation.select(values, self.policy))
        values = self.advance(30, self.rows(values))
        self.assertIs(confirmation.select(values, self.policy), values[0])
        self.assertEqual(values[0].confirmation["controls"], 3)
        self.assertEqual(values[0].confirmation["first_scan_run_id"], 1)

    def test_ranking_change_does_not_reset_either_eligible_candidate(self):
        values = []
        for minute in (0, 15, 30):
            values = self.advance(minute, self.rows(values),
                                  edges=(.15, .16 if minute == 15 else .14),
                                  symbols=("BTCUSDT", "ETHUSDT"))
        self.assertEqual([c.confirmation["controls"] for c in values], [3, 3])
        self.assertEqual(confirmation.select(values, self.policy).symbol, "BTCUSDT")

    def test_new_higher_scoring_candidate_cannot_jump_confirmation(self):
        values = []
        for minute in (0, 15):
            values = self.advance(minute, self.rows(values))
        values = self.advance(30, self.rows(values), edges=(.15, .25), symbols=("BTCUSDT", "ETHUSDT"))
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

    def test_engine_or_artifact_changes_restart(self):
        for change in ("engine", "artifact"):
            with self.subTest(change=change):
                old = self.rows(self.advance(0))
                if change == "engine":
                    old[0]["engine_version"] = "old-engine"
                elif change == "artifact":
                    old[0]["artifact_id"] = "old-artifact"
                values = self.advance(15, old)
                self.assertEqual(values[0].confirmation["controls"], 1)

    def test_missing_scanner_rounds_preserve_episode_but_require_new_valid_analysis(self):
        values = self.advance(15, self.rows(self.advance(0)))
        resumed = self.advance(120, self.rows(values))
        self.assertEqual(resumed[0].confirmation["controls"], 3)
        self.assertEqual(resumed[0].confirmation["first_scan_run_id"], 1)
        self.assertEqual(resumed[0].confirmation["last_valid_gap_seconds"], 105 * 60)
        self.assertIs(confirmation.select(resumed, self.policy), resumed[0])

    def test_one_missing_scan_retains_two_valid_controls(self):
        values = self.advance(0)
        values = self.advance(30, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 2)
        self.assertIsNone(confirmation.select(values, self.policy))
        values = self.advance(45, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 3)
        self.assertIs(confirmation.select(values, self.policy), values[0])

    def test_late_first_scan_does_not_fake_30_minutes(self):
        values = self.advance(0)
        values[0].confirmation["first_analyzed_at"] = (self.start + timedelta(minutes=5)).isoformat()
        for minute in (15, 30):
            values = self.advance(minute, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 3)
        self.assertIsNone(confirmation.select(values, self.policy))
        values = self.advance(45, self.rows(values))
        self.assertIs(confirmation.select(values, self.policy), values[0])

    def test_consumed_confirmation_cannot_open_again_next_round(self):
        values = self.mature()
        confirmation.finish(values, values[0], status="opened", reason="confirmed", operation_id=123)
        self.assertEqual(values[0].confirmation["operation_id"], 123)
        self.assertEqual(values[0].confirmation["counterfactual_role"], "confirmed")
        values = self.advance(45, self.rows(values))
        self.assertEqual(values[0].confirmation["controls"], 1)
        self.assertIsNone(confirmation.select(values, self.policy))

    def test_failed_execution_does_not_consume_confirmation(self):
        values = self.mature()
        confirmation.finish(values, values[0], status="no_trade", reason="price_drift", operation_id=None)
        values = self.advance(45, self.rows(values))
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

    def test_provider_failure_pauses_and_next_valid_check_resumes(self):
        previous = self.rows(self.advance(15, self.rows(self.advance(0))))
        value = candidate(edge=.15)
        value.analyzed_at = self.start + timedelta(minutes=30)
        value.analysis_status = "failed"
        value.artifact_id = None
        value.rejection_code = "provider_failed"
        confirmation.advance([value], self.policy, previous, slot=value.analyzed_at,
                             scan_run_id=3, engine_version=contest.EMPIRICAL_ENGINE_VERSION)
        self.assertEqual(value.confirmation["state"], "paused")
        self.assertEqual(value.confirmation["controls"], 2)
        self.assertEqual(value.confirmation["pause_reason"], "provider_failed")
        self.assertIsNone(confirmation.select([value], self.policy))
        resumed = self.advance(45, self.rows([value]))
        self.assertEqual(resumed[0].confirmation["controls"], 3)
        self.assertEqual(resumed[0].confirmation["deferred_checks"], 1)
        self.assertIs(confirmation.select(resumed, self.policy), resumed[0])

    def test_repeated_provider_failures_never_open_on_stale_evidence(self):
        previous = self.rows(self.advance(15, self.rows(self.advance(0))))
        for minute in (30, 45, 60, 75):
            value = candidate(edge=.15)
            value.analyzed_at = self.start + timedelta(minutes=minute)
            value.analysis_status = "failed"
            value.rejection_code = "provider_failed"
            value.artifact_id = None
            confirmation.advance([value], self.policy, previous, slot=value.analyzed_at,
                                 scan_run_id=minute + 1,
                                 engine_version=contest.EMPIRICAL_ENGINE_VERSION)
            self.assertEqual(value.confirmation["state"], "paused")
            self.assertEqual(value.confirmation["controls"], 2)
            self.assertIsNone(confirmation.select([value], self.policy))
            previous = self.rows([value])
        resumed = self.advance(90, previous)
        self.assertEqual(resumed[0].confirmation["controls"], 3)
        self.assertEqual(resumed[0].confirmation["deferred_checks"], 4)
        self.assertEqual(resumed[0].confirmation["first_scan_run_id"], 1)
        self.assertIs(confirmation.select(resumed, self.policy), resumed[0])

    def test_paused_v2_episode_resumes_without_restarting_after_long_outage(self):
        previous = self.rows(self.advance(15, self.rows(self.advance(0))))
        previous[0]["confirmation"].update(
            version="short-entry-confirmation-v2", state="paused", deferred_checks=2,
        )
        previous[0]["artifact_id"] = None
        resumed = self.advance(60, previous)
        self.assertEqual(resumed[0].confirmation["version"], confirmation.CONFIRMATION_VERSION)
        self.assertEqual(resumed[0].confirmation["controls"], 3)
        self.assertIsNotNone(confirmation.select(resumed, self.policy))

    def test_real_threshold_loss_after_outage_discards_instead_of_resuming(self):
        previous = self.rows(self.advance(15, self.rows(self.advance(0))))
        values = self.advance(90, previous, edges=(.05,))
        self.assertEqual(values[0].confirmation["state"], "discarded")
        self.assertIsNone(confirmation.select(values, self.policy))

    def test_existing_v1_episode_can_finish_under_three_control_policy(self):
        previous = self.rows(self.advance(15, self.rows(self.advance(0))))
        previous[0]["confirmation"]["version"] = confirmation.LEGACY_CONFIRMATION_VERSION
        previous[0]["confirmation"].pop("last_valid_analyzed_at")
        previous[0]["confirmation"].pop("artifact_id")
        values = self.advance(30, previous)
        self.assertEqual(values[0].confirmation["version"], confirmation.CONFIRMATION_VERSION)
        self.assertEqual(values[0].confirmation["controls"], 3)
        self.assertIs(confirmation.select(values, self.policy), values[0])

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
        for minute in (0, 15, 30):
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
            self.assertEqual(params[-1], "pending" if minute in (0, 30) else "excluded")
            self.assertEqual(params[21], "confirmation")

    def test_read_returns_only_latest_pair_state_in_season_and_mode(self):
        class Db:
            def execute(inner, query, params):
                self.assertIn("LIMIT 12", query)
                self.assertIn("PARTITION BY c.symbol, c.side", query)
                self.assertIn("WHERE recency = 1", query)
                self.assertIn("s.contest_season_id = ?", query)
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

    def test_report_counts_episodes_not_three_independent_trades(self):
        rows, values = [], []
        for minute in (0, 15, 30):
            values = self.advance(minute, self.rows(values))
            if minute == 30:
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
        self.connection.execute("""CREATE TABLE operations (
            id INTEGER PRIMARY KEY, user_id INTEGER, contest_season_id INTEGER,
            mode TEXT DEFAULT 'contest', status TEXT DEFAULT 'OPEN',
            symbol TEXT, side TEXT, entry REAL, margin REAL, leverage REAL)""")
        self.connection.execute("""INSERT INTO autonomous_contest_participants
            (id, code, user_id, display_name, time_horizon, policy_version, cadence_minutes,
             daily_operation_limit, max_open_positions, edge_threshold, min_tp_probability,
             max_unresolved_probability, min_analogs_per_stage, margin, leverage, symbols_json)
            VALUES (1,'auto_intraday_short',27,'Short','intraday_short','v',15,3,3,.1,.3,.55,80,100,1,'[]')""")
        self.connection.commit()
        self.opened = []
        self.policy = contest.PARTICIPANT_POLICIES[0]
        self.side = "long"
        self.candidate_symbol = "BTCUSDT"
        self.guard_prices = {s: 100. for s in contest.SYMBOLS}
        self.execution_guard_prices = None
        self.guard_material_missing = False
        self.guard_anchor_prices = {}
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

    def scan(self, minute, *, bad=False, fail_insert=False,
             fail_analysis=False, fail_final=False, worker_price_fail=False, planned=False,
             dry_run=False, cash=1000.):
        original_analyze = contest.analyze_candidates
        def analyze(policy, prices, at, **kwargs):
            if not kwargs.get("symbols") and not self.guard_material_missing:
                for symbol in contest.SYMBOLS:
                    kwargs["kline_loader"](symbol, "5m", contest.market_guard.REQUIRED_CANDLES,
                                           end_time_ms=int(at.timestamp()*1000))
            if planned and not fail_analysis and not fail_final:
                from tests.test_short_trade_planner import material
                data, _ = material()
                data = {**data, "data_cutoff_at_ms": data["data_cutoff_at_ms"] + minute * 60000}
                def engine(proposal, **ignored):
                    return dict(tp_probability=.60, sl_probability=.25, range_probability=.15,
                                snapshot={}, model_trace={"artifact_id": "frozen-artifact",
                                "stage_traces": [{"selected_analogs": 100}]})
                with patch.object(contest, "load_horizon_material", return_value=data):
                    return original_analyze(policy, prices, at, analysis_runner=engine,
                        liquidation_contexts={}, order_book_contexts={}, symbols=("BTCUSDT",),
                        sides=("long",), fixed_candidate=kwargs.get("fixed_candidate"),
                        previous_confirmations=kwargs.get("previous_confirmations", ()))
            value = candidate(edge=.09 if bad else .15, symbol=self.candidate_symbol)
            value.side = self.side
            value.time_horizon = policy.time_horizon
            value.entry = prices[value.symbol]
            value.take_profit, value.stop_loss = value.entry * 1.01, value.entry * .99
            if self.side == "short":
                value.take_profit, value.stop_loss = value.entry * .99, value.entry * 1.01
            value.analyzed_at = at
            value.sigma = .01
            value.artifact_id = "frozen-artifact"
            if fail_analysis or (fail_final and kwargs.get("symbols")):
                value.analysis_status = "failed"
                value.rejection_code = "sigma:BinanceDeferred:binance_shared_budget_exhausted"
                value.artifact_id = None
            return [value]

        def fresh_prices(db, symbols, **kwargs):
            if worker_price_fail and len(tuple(symbols)) == 1:
                return {}
            if self.execution_guard_prices is not None and len(tuple(symbols)) == 1:
                self.guard_prices = dict(self.execution_guard_prices)
            return dict(self.guard_prices)

        def opening(db, **kwargs):
            if fail_insert:
                raise RuntimeError("injected_insert_failure")
            self.opened.append(kwargs["candidate"].analyzed_at)
            return 700 + len(self.opened), 900 + len(self.opened)

        def klines(symbol, interval, count, start_time_ms=None, end_time_ms=None):
            self.assertEqual(interval, "5m")
            step = contest.market_guard.INTERVAL_MS
            end = end_time_ms // step * step - 1
            rows = [[end - i*step - step + 1, 100., 110., 90., 100., 1., end - i*step]
                    for i in range(count - 1, -1, -1)]
            for name, value in self.guard_anchor_prices.items():
                rows[-contest.market_guard.WINDOWS[name] - 1][4] = value
            return rows

        with patch.object(contest, "PARTICIPANT_POLICIES", (self.policy,)), \
             patch.object(contest, "ensure_contest_entries"), \
             patch.object(contest, "fresh_market_prices", side_effect=fresh_prices), \
             patch.object(contest, "_load_order_book_contexts", return_value={}), \
             patch.object(contest, "_load_liquidation_contexts", return_value={}), \
             patch.object(contest, "analyze_candidates", side_effect=analyze), \
             patch.object(contest, "_daily_operation_count", side_effect=lambda *a, **kw: len(self.opened)), \
             patch.object(contest, "_available_contest_cash", return_value=cash), \
             patch.object(contest, "_open_selected_operation", side_effect=opening):
            return contest.run_due_scans(self.connect, lambda _: {"id": 1},
                                        dry_run=dry_run, bootstrap=False,
                                        kline_loader=klines,
                                        now=self.start + timedelta(minutes=minute))

    def configure_guard_position(self, policy, side):
        self.policy, self.side, self.candidate_symbol = policy, side, "ETHUSDT"
        self.connection.execute("UPDATE autonomous_contest_participants SET code=?,time_horizon=?,last_scan_slot_at=NULL",
                                (policy.code, policy.time_horizon))
        self.connection.execute("DELETE FROM operations")
        self.connection.execute("DELETE FROM autonomous_candidate_observations")
        self.connection.execute("DELETE FROM autonomous_scan_runs")
        self.connection.execute("""INSERT INTO operations(user_id,contest_season_id,symbol,side,entry,margin,leverage)
            VALUES(27,1,'BTCUSDT',?,100,100,10)""", (side,))
        self.connection.commit()
        self.guard_prices = {s: (99. if side == "long" else 101.) for s in contest.SYMBOLS}

    def test_all_bots_veto_cross_pair_losing_exposure_in_real_scanner_and_dry_run(self):
        for policy in contest.PARTICIPANT_POLICIES:
            for side in ("long", "short"):
                for dry_run in (False, True):
                    with self.subTest(bot=policy.code, side=side, dry_run=dry_run):
                        self.configure_guard_position(policy, side)
                        outcome = self.scan(0, dry_run=dry_run)["scans"][0]
                        self.assertEqual(outcome["status"], "no_trade")
                        self.assertEqual(outcome["reason"], "market_against_losing_" + side + "_exposure")
                        self.assertEqual(self.opened, [])
                        raw = self.connection.execute("SELECT candidate_audit_json FROM autonomous_scan_runs").fetchone()[0]
                        saved = json.loads(raw)
                        evidence = saved["gates"]["market_exposure_guard"]["panel"]
                        self.assertEqual(evidence["groups"][0]["symbol"], "BTCUSDT")
                        self.assertEqual(evidence["decisions"][side]["status"], "blocked")
                        self.assertEqual(saved["record_count"], 1)
                        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM operations WHERE status='OPEN'").fetchone()[0], 1)

    def test_execution_recheck_blocks_market_turn_after_candidate_confirmation(self):
        self.configure_guard_position(contest.PARTICIPANT_POLICIES[2], "long")
        self.guard_prices = {s: 100. for s in contest.SYMBOLS}
        self.execution_guard_prices = {s: 99. for s in contest.SYMBOLS}
        # Candidate still has a valid price; the rest of the market moves against the BTC book.
        self.execution_guard_prices["ETHUSDT"] = 100.
        result = self.scan(0)["scans"][0]
        self.assertEqual(result["reason"], "market_against_losing_long_exposure")
        self.assertEqual(result["status"], "no_trade")
        self.assertEqual(self.opened, [])
        raw = json.loads(self.connection.execute("SELECT candidate_audit_json FROM autonomous_scan_runs").fetchone()[0])
        checks = raw["gates"]["market_exposure_guard"]
        self.assertEqual(checks["panel"]["decisions"]["long"]["status"], "allowed")
        self.assertEqual(checks["execution"]["decisions"]["long"]["status"], "blocked")

    def test_all_bots_share_recent_direction_despite_opposite_day_background(self):
        for side, background in (("long", 90.), ("short", 110.)):
            market_states = []
            for policy in contest.PARTICIPANT_POLICIES:
                self.configure_guard_position(policy, side)
                self.guard_anchor_prices = {"4h": background, "24h": background}
                result = self.scan(0)["scans"][0]
                self.assertEqual(result["reason"], "market_against_losing_" + side + "_exposure")
                raw = json.loads(self.connection.execute("SELECT candidate_audit_json FROM autonomous_scan_runs").fetchone()[0])
                market_states.append(raw["gates"]["market_exposure_guard"]["panel"]["market"])
            self.assertEqual(market_states[0], market_states[1])
            self.assertEqual(market_states[1], market_states[2])
        self.assertEqual(self.opened, [])

    def test_market_conflict_is_persisted_and_does_not_open_even_with_valid_forecast(self):
        self.configure_guard_position(contest.PARTICIPANT_POLICIES[2], "long")
        self.guard_anchor_prices = {"15m": 101., "1h": 98.}
        result = self.scan(0)["scans"][0]
        self.assertEqual(result["status"], "no_trade")
        self.assertEqual(result["reason"], "market_recent_conflict_with_losing_exposure")
        self.assertEqual(self.opened, [])

    def test_guard_missing_data_pauses_short_lineage_and_resumes_without_losing_controls(self):
        self.configure_guard_position(contest.PARTICIPANT_POLICIES[0], "long")
        self.guard_prices = {s: 101. for s in contest.SYMBOLS}
        self.scan(0)
        self.scan(15)
        self.guard_material_missing = True
        self.guard_prices = {s: 99. for s in contest.SYMBOLS}
        self.assertEqual(self.scan(30)["scans"][0]["reason"], "market_exposure_guard_data_unavailable")
        raw = json.loads(self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()[0])
        self.assertEqual(raw["confirmation"]["state"], "paused")
        self.assertEqual(raw["confirmation"]["controls"], 2)
        self.assertEqual(self.opened, [])
        self.guard_material_missing = False
        self.guard_prices = {s: 101. for s in contest.SYMBOLS}
        self.assertEqual(self.scan(45)["scans"][0]["status"], "opened")

    def test_guard_does_not_mix_other_bots_and_has_no_forced_short_opening(self):
        self.configure_guard_position(contest.PARTICIPANT_POLICIES[2], "long")
        self.connection.execute("UPDATE operations SET user_id=99")
        result = self.scan(0)["scans"][0]
        self.assertEqual(result["status"], "opened")
        raw = json.loads(self.connection.execute("SELECT candidate_audit_json FROM autonomous_scan_runs").fetchone()[0])
        self.assertEqual(raw["gates"]["market_exposure_guard"]["panel"]["book"]["long"]["open_count"], 0)

    def test_three_scans_open_once_and_duplicate_scan_does_not_advance(self):
        for minute in (0, 15):
            result = self.scan(minute)
            self.assertEqual(result["scans"][0]["reason"], "awaiting_30m_candidate_confirmation")
        self.assertEqual(self.scan(15)["scans"], [])
        self.assertEqual(self.scan(30)["scans"][0]["status"], "opened")
        self.assertEqual(self.scan(45)["scans"][0]["status"], "no_trade")
        self.assertEqual(len(self.opened), 1)
        rows = self.connection.execute("SELECT observational_json, outcome_status FROM autonomous_candidate_observations ORDER BY id").fetchall()
        self.assertEqual(len(rows), 4)
        self.assertEqual(json.loads(rows[2]["observational_json"])["confirmation"]["state"], "consumed")
        self.assertEqual([r["outcome_status"] for r in rows], ["pending", "excluded", "pending", "pending"])

    def test_real_plans_resume_from_sql_after_missing_data_without_erasing_levels(self):
        self.scan(0, planned=True)
        self.scan(15, planned=True, fail_analysis=True)
        self.scan(30, planned=True)
        self.assertEqual(self.scan(45, planned=True)["scans"][0]["status"], "opened")
        rows = self.connection.execute("""SELECT take_profit, stop_loss, observational_json
            FROM autonomous_candidate_observations ORDER BY id""").fetchall()
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({(r["take_profit"], r["stop_loss"]) for r in rows}), 1)
        states = [json.loads(r["observational_json"])["confirmation"] for r in rows]
        self.assertEqual([s["controls"] for s in states], [1, 1, 2, 3])
        self.assertEqual([s["state"] for s in states], ["watching", "paused", "watching", "consumed"])
        self.assertEqual(len({s["plan_key"] for s in states}), 1)
        self.assertTrue(all(len(r["observational_json"].encode()) <= 2048 for r in rows))

    def test_threshold_failure_prevents_open_and_restarts(self):
        self.scan(0)
        self.scan(15)
        self.scan(30, bad=True)
        self.assertEqual(self.scan(45)["scans"][0]["status"], "no_trade")
        self.assertEqual(self.opened, [])
        row = self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(row[0])["confirmation"]["controls"], 1)

    def test_provider_failure_during_scan_resumes_without_opening_on_missing_data(self):
        self.scan(0)
        self.scan(15)
        self.assertEqual(self.scan(30, fail_analysis=True)["scans"][0]["status"], "no_trade")
        row = self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(row[0])["confirmation"]["state"], "paused")
        self.assertEqual(self.opened, [])
        self.assertEqual(self.scan(45)["scans"][0]["status"], "opened")

    def test_multiple_failed_rounds_keep_two_controls_and_resume_on_third_valid(self):
        self.scan(0)
        self.scan(15)
        for minute in (30, 45, 60):
            result = self.scan(minute, fail_analysis=True)
            self.assertEqual(result["scans"][0]["reason"], "candidate_market_data_unavailable")
            self.assertEqual(self.opened, [])
        self.assertEqual(self.scan(75)["scans"][0]["status"], "opened")
        row = self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()
        meta = json.loads(row[0])["confirmation"]
        self.assertEqual(meta["controls"], 3)
        self.assertEqual(meta["deferred_checks"], 3)

    def test_entire_missing_scanner_rounds_do_not_lose_saved_controls(self):
        self.scan(0)
        self.scan(15)
        # No scan claims or candidate writes occurred during the outage.
        self.assertEqual(self.scan(180)["scans"][0]["status"], "opened")
        self.assertEqual(len(self.opened), 1)

    def test_latest_terminal_state_prevents_resurrection_after_long_gap(self):
        self.scan(0)
        self.scan(15)
        self.scan(30, bad=True)
        self.assertEqual(self.scan(180)["scans"][0]["status"], "no_trade")
        self.assertEqual(self.opened, [])

    def test_consumed_state_prevents_duplicate_open_after_long_gap(self):
        for minute in (0, 15, 30):
            self.scan(minute)
        self.assertEqual(self.scan(180)["scans"][0]["status"], "no_trade")
        self.assertEqual(len(self.opened), 1)

    def test_real_filter_failure_is_not_reported_as_provider_outage(self):
        result = self.scan(0, bad=True)
        self.assertEqual(result["scans"][0]["reason"], "no_candidate_passed_horizon_policy")

    def test_provider_failure_during_final_reanalysis_preserves_tracking(self):
        self.scan(0)
        self.scan(15)
        result = self.scan(30, fail_final=True)
        self.assertEqual(result["scans"][0]["status"], "no_trade")
        row = self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(row[0])["confirmation"]["state"], "paused")
        self.assertEqual(self.opened, [])
        self.assertEqual(self.scan(45)["scans"][0]["status"], "opened")

    def test_missing_worker_price_during_final_reanalysis_preserves_tracking(self):
        self.scan(0)
        self.scan(15)
        result = self.scan(30, worker_price_fail=True)
        self.assertEqual(result["scans"][0]["status"], "no_trade")
        row = self.connection.execute("SELECT observational_json FROM autonomous_candidate_observations ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(json.loads(row[0])["confirmation"]["state"], "paused")
        self.assertEqual(self.opened, [])
        self.assertEqual(self.scan(45)["scans"][0]["status"], "opened")

    def test_failed_persistence_rolls_back_checkpoint_and_next_valid_scan_can_confirm(self):
        for minute in (0, 15):
            self.scan(minute)
        with self.assertLogs("autonomous_contest", level="ERROR"):
            self.assertEqual(self.scan(30, fail_insert=True)["scans"][0]["status"], "failed")
        self.assertEqual(self.opened, [])
        self.assertEqual(self.scan(45)["scans"][0]["status"], "opened")
        self.assertEqual(len(self.opened), 1)

    def test_endpoint_evaluator_and_report_use_actual_saved_checkpoints(self):
        for minute in (0, 15, 30):
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

    def test_discarded_candidate_has_complete_audit_without_learning_sample(self):
        result = self.scan(0, bad=True)
        row = self.connection.execute("SELECT candidate_audit_json FROM autonomous_scan_runs").fetchone()
        audit = contest.scan_audit.decode_audit(row[0])
        self.assertEqual(result["scans"][0]["status"], "no_trade")
        self.assertEqual(audit["coverage"], "complete")
        self.assertEqual(len(audit["analyses"]), 1)
        self.assertFalse(audit["analyses"][0]["eligible"])
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM autonomous_candidate_observations").fetchone()[0], 0)

    def test_confirmation_is_a_separate_analysis_in_complete_audit(self):
        for minute in (0, 15, 30):
            self.scan(minute)
        row = self.connection.execute("SELECT candidate_audit_json FROM autonomous_scan_runs ORDER BY id DESC LIMIT 1").fetchone()
        audit = contest.scan_audit.decode_audit(row[0])
        self.assertEqual([r["phase"] for r in audit["analyses"]], ["panel", "confirmation"])
        self.assertEqual(audit["selected_index"], 1)

    def test_failed_trade_insert_preserves_analysis_audit_after_rollback(self):
        for minute in (0, 15):
            self.scan(minute)
        with self.assertLogs("autonomous_contest", level="ERROR"):
            self.scan(30, fail_insert=True)
        row = self.connection.execute("SELECT status,candidate_audit_json FROM autonomous_scan_runs ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertEqual(len(contest.scan_audit.decode_audit(row["candidate_audit_json"])["analyses"]), 2)


if __name__ == "__main__":
    unittest.main()
