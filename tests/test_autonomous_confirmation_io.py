import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import autonomous_confirmation_io as io
import autonomous_contest as contest
from tests.test_autonomous_contest import candidate
from tests import test_autonomous_confirmation as scanner_fixture


NOW = datetime(2026, 10, 21, 9, 2, tzinfo=timezone.utc)


class ClosedCacheTests(unittest.TestCase):
    def provider(self, calls):
        def load(symbol, interval, limit, start_time_ms=None, end_time_ms=None):
            calls.append((symbol, interval, limit, start_time_ms, end_time_ms))
            step = io.INTERVAL_MS[interval]
            first = -(-start_time_ms // step) * step
            return [[n, 1., 2., .5, 1.5, 10., n + step - 1]
                    for n in range(first, end_time_ms + 1, step)][:limit]
        return load

    def test_confirmation_reuses_identical_closed_material_not_forming_candles(self):
        for interval, step in io.INTERVAL_MS.items():
            with self.subTest(interval=interval):
                calls = []
                provider = self.provider(calls)
                cache = contest.MemoizedKlineLoader(provider)
                at = int(NOW.timestamp() * 1000)
                for stamp in (at, at + 17000):
                    start = stamp - 1603 * step
                    expected = self.provider([])("BTCUSDT", interval, 1500, start, stamp)
                    expected = [r for r in expected if r[6] <= stamp]
                    actual = cache("BTCUSDT", interval, 1500, start, stamp)
                    self.assertEqual(actual, expected)
                self.assertEqual(len(calls), 1)
                self.assertEqual(cache.stats()["cache_hits"], 1)

    def test_paginated_range_preserves_all_closed_candles_and_reuses_pages(self):
        calls = []
        cache = contest.MemoizedKlineLoader(self.provider(calls))
        at = int(NOW.timestamp() * 1000)
        step = io.INTERVAL_MS["5m"]
        a = contest.fetch_klines_range("BTCUSDT", "5m", at-3003*step, at, loader=cache)
        count = len(calls)
        b = contest.fetch_klines_range("BTCUSDT", "5m", at+10000-3003*step, at+10000, loader=cache)
        self.assertEqual(a, b)
        self.assertEqual(len(calls), count)
        self.assertEqual(len(a), 3002)
        self.assertEqual(len({r[0] for r in a}), len(a))
        self.assertTrue(all(r[6] <= at for r in a))

    def test_crossing_close_fetches_new_data_and_does_not_reuse_forming_value(self):
        calls = []
        cache = contest.MemoizedKlineLoader(self.provider(calls))
        step = io.INTERVAL_MS["5m"]
        at = int(NOW.timestamp()*1000)
        before = cache("BTCUSDT", "5m", 80, at-10*step, at)
        after_at = at + 3*60000
        after = cache("BTCUSDT", "5m", 80, after_at-10*step, after_at)
        self.assertEqual(len(calls), 2)
        self.assertEqual(after[-1][6] - before[-1][6], step)
        after[-1][4] = -999
        self.assertEqual(cache("BTCUSDT", "5m", 80, after_at-10*step, after_at)[-1][4], 1.5)

    def test_hourly_sigma_and_selected_history_unchanged(self):
        calls = []
        provider = self.provider(calls)
        # Give the causal material genuine variation, still deterministic by time.
        def prices(*args, **kwargs):
            rows = provider(*args, **kwargs)
            for row in rows:
                row[4] = 100 + (row[0] // 3600000) % 17 / 10
                row[1], row[2], row[3] = row[4], row[4] + 1, row[4] - 1
            return rows
        old = contest.load_horizon_material("BTCUSDT", "intraday_wide", NOW, loader=prices)
        cache = contest.MemoizedKlineLoader(prices)
        new = contest.load_horizon_material("BTCUSDT", "intraday_wide", NOW, loader=cache)
        later = contest.load_horizon_material("BTCUSDT", "intraday_wide", NOW+timedelta(seconds=20), loader=cache)
        for name in ("selected", "current_variance", "signed_efficiencies", "data_sha256"):
            self.assertEqual(old[name], new[name])
            self.assertEqual(new[name], later[name])


class RetryTests(unittest.TestCase):
    def test_only_explicit_deferrals_are_retried(self):
        self.assertIsNone(io.deferred_seconds(ValueError("bad candles")))
        self.assertEqual(io.deferred_seconds(contest.market_data.BinanceDeferred("quota", retry_after_seconds=12)), 12)
        self.assertEqual(io.deferred_seconds(contest.NewEngineAnalysisError("data", {"provider_deferred": True, "retry_after_seconds": 31})), 31)
        self.assertIsNone(io.deferred_seconds(contest.market_data.BinanceDeferred("bad", retry_after_seconds=float("nan"))))

    def run_retry(self, results, *, interrupt=False, elapsed_extra=0):
        clock_at = [NOW]
        waits = []
        def wait(delay):
            waits.append(delay)
            clock_at[0] += timedelta(seconds=delay + elapsed_extra)
            return interrupt
        attempt = Mock(side_effect=results)
        cache = Mock()
        answer = io.confirm_with_retry(attempt, clock=lambda: clock_at[0], wait=wait, cache=cache, panel_at=NOW)
        return answer, attempt, cache, waits

    def failed(self, delay=12):
        return contest.Candidate("BTCUSDT", "long", "intraday_wide", NOW,
            analysis_status="failed", rejection_code="sigma:BinanceDeferred:quota", data_retry_seconds=delay)

    def test_one_deferral_recovers_without_waiting_for_next_hour(self):
        good = candidate(edge=.15)
        (value, evidence), attempt, cache, waits = self.run_retry([self.failed(), good])
        self.assertIs(value, good)
        self.assertEqual(attempt.call_args_list[1].args[0], NOW+timedelta(seconds=12))
        self.assertEqual(waits, [12])
        cache.resume_deferred.assert_called_once()
        self.assertEqual(evidence["attempts"], 2)

    def test_repeated_deferrals_are_bounded_and_recorded(self):
        (value, evidence), attempt, cache, waits = self.run_retry([self.failed()] * 3)
        self.assertEqual(attempt.call_count, 3)
        self.assertEqual(len(waits), 2)
        self.assertEqual(evidence["stop_reason"], "confirmation_retry_budget_exhausted")
        self.assertEqual(value.analysis_status, "failed")
        self.assertLess(len(json.dumps(evidence)), 1200)

    def test_long_circuit_shutdown_and_expired_panel_never_retry(self):
        for options, delay in (({}, 600), ({"interrupt": True}, 12), ({"elapsed_extra": 200}, 12)):
            with self.subTest(options=options):
                (value, evidence), attempt, cache, waits = self.run_retry([self.failed(delay)], **options)
                self.assertEqual(attempt.call_count, 1)
                self.assertIsNotNone(evidence["stop_reason"])
                cache.resume_deferred.assert_not_called()
                self.assertFalse(value.eligible_base)

    def test_analysis_rejection_is_not_retried(self):
        failed = self.failed()
        failed.data_retry_seconds = None
        (_, evidence), attempt, _, waits = self.run_retry([failed])
        self.assertEqual(attempt.call_count, 1)
        self.assertEqual(waits, [])
        self.assertEqual(evidence["deferrals"], [])

    def test_sigma_deferral_preserves_provider_retry_delay(self):
        def sigma(*args):
            raise contest.market_data.BinanceDeferred("binance_shared_budget_exhausted", retry_after_seconds=19)
        result = contest.analyze_candidates(contest.PARTICIPANT_POLICIES[1], {"BTCUSDT":100.}, NOW,
            sigma_loader=sigma, symbols=("BTCUSDT",), sides=("long",))
        self.assertEqual(result[0].data_retry_seconds, 19)
        self.assertFalse(result[0].eligible_base)

    def test_confirmation_reads_fresh_price_after_wait_outside_transaction(self):
        clock_at = [NOW]
        in_transaction = [False]
        @contextmanager
        def connect():
            in_transaction[0] = True
            try:
                yield object()
            finally:
                in_transaction[0] = False
        def wait(delay):
            self.assertFalse(in_transaction[0])
            clock_at[0] += timedelta(seconds=delay)
            return False
        seen_prices = []
        def analyze(policy, prices, at, **kwargs):
            seen_prices.append(prices["BTCUSDT"])
            value = self.failed() if len(seen_prices) == 1 else candidate(edge=.15)
            value.analyzed_at = at
            return [value]
        cache = Mock()
        with patch.object(contest, "fresh_market_prices", side_effect=[{"BTCUSDT":100.}, {"BTCUSDT":101.}]), \
             patch.object(contest, "_load_order_book_contexts", return_value={}), \
             patch.object(contest, "_load_liquidation_contexts", return_value={}), \
             patch.object(contest, "analyze_candidates", side_effect=analyze):
            value, evidence = contest._confirm_selected_candidate(connect, contest.PARTICIPANT_POLICIES[1], candidate(edge=.15),
                analysis_runner=Mock(), sigma_loader=Mock(), kline_loader=cache, audit_records=[],
                clock=lambda: clock_at[0], retry_wait=wait, panel_at=NOW)
        self.assertEqual(seen_prices, [100., 101.])
        self.assertEqual(value.analyzed_at, NOW+timedelta(seconds=12))
        self.assertEqual(evidence["attempts"], 2)

    def test_missing_fresh_price_cannot_open_or_reuse_previous_quote(self):
        @contextmanager
        def connect():
            yield object()
        analyze = Mock()
        with patch.object(contest, "fresh_market_prices", return_value={}), \
             patch.object(contest, "_load_order_book_contexts", return_value={}), \
             patch.object(contest, "analyze_candidates", analyze):
            value, _ = contest._confirm_selected_candidate(connect, contest.PARTICIPANT_POLICIES[1], candidate(edge=.15),
                analysis_runner=Mock(), sigma_loader=Mock(), kline_loader=Mock(), audit_records=[],
                clock=lambda: NOW, retry_wait=Mock(), panel_at=NOW)
        self.assertFalse(value.eligible_base)
        self.assertEqual(value.rejection_code, "selected_confirmation_worker_price_unavailable")
        analyze.assert_not_called()


class ScannerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scanner_fixture.ScannerIntegrationTests()
        self.fixture.setUp()
        self.fixture.policy = contest.PARTICIPANT_POLICIES[1]
        self.fixture.connection.execute(
            "UPDATE autonomous_contest_participants SET code=?,time_horizon=?",
            (self.fixture.policy.code, self.fixture.policy.time_horizon))
        self.fixture.connection.commit()

    def tearDown(self):
        self.fixture.tearDown()

    def scan_recovery(self, on_wait=None, *, always_deferred=False, interrupt=False):
        original = contest._confirm_selected_candidate
        attempted = []
        def wrapper(*args, **kwargs):
            def analyze(policy, prices, at, **ignored):
                value = candidate(edge=.15)
                value.time_horizon, value.analyzed_at = policy.time_horizon, at
                value.entry = prices[value.symbol]
                value.take_profit, value.stop_loss = value.entry*1.01, value.entry*.99
                value.sigma, value.artifact_id = .01, "frozen-artifact"
                if not attempted or always_deferred:
                    value.analysis_status = "failed"
                    value.rejection_code = "sigma:BinanceDeferred:binance_shared_budget_exhausted"
                    value.data_retry_seconds = 2
                attempted.append(value)
                kwargs["audit_records"].append(contest.scan_audit.candidate_record(value, policy, phase="confirmation"))
                return [value]
            def wait(delay):
                if on_wait:
                    on_wait()
                return interrupt
            kwargs["retry_wait"] = wait
            with patch.object(contest, "analyze_candidates", side_effect=analyze):
                return original(*args, **kwargs)
        with patch.object(contest, "_confirm_selected_candidate", side_effect=wrapper):
            outcome = self.fixture.scan(0)["scans"][0]
        saved = json.loads(self.fixture.connection.execute(
            "SELECT candidate_audit_json FROM autonomous_scan_runs").fetchone()[0])
        return outcome, saved, attempted

    def test_recovered_confirmation_opens_once_in_same_hour_and_keeps_audit(self):
        outcome, saved, attempts = self.scan_recovery()
        self.assertEqual(outcome["status"], "opened")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(self.fixture.opened), 1)
        self.assertEqual(saved["gates"]["confirmation_io"]["attempts"], 2)
        self.assertEqual(saved["record_count"], 3)
        self.assertEqual(self.fixture.scan(1)["scans"], [])
        self.assertEqual(len(self.fixture.opened), 1)
        self.assertEqual(self.fixture.connection.execute("SELECT COUNT(*) FROM autonomous_scan_runs").fetchone()[0], 1)

    def test_final_market_guard_still_blocks_after_recovery(self):
        self.fixture.connection.execute("""INSERT INTO operations(user_id,contest_season_id,symbol,side,entry,margin,leverage)
            VALUES(27,1,'ETHUSDT','long',100,100,10)""")
        self.fixture.connection.commit()
        def turn():
            self.fixture.guard_prices = {s:99. for s in contest.SYMBOLS}
        outcome, saved, _ = self.scan_recovery(turn)
        self.assertEqual(outcome["reason"], "market_against_losing_long_exposure")
        self.assertEqual(self.fixture.opened, [])
        self.assertEqual(saved["gates"]["market_exposure_guard"]["execution"]["decisions"]["long"]["status"], "blocked")

    def test_final_daily_quota_still_checked_after_wait(self):
        def quota():
            self.fixture.opened[:] = [NOW, NOW]
        outcome, _, _ = self.scan_recovery(quota)
        self.assertEqual(outcome["status"], "quota_reached")
        self.assertEqual(len(self.fixture.opened), 2)

    def test_persistent_deferral_and_shutdown_never_open(self):
        outcome, saved, attempted = self.scan_recovery(always_deferred=True)
        self.assertEqual(outcome["status"], "no_trade")
        self.assertEqual(len(attempted), 3)
        self.assertEqual(saved["gates"]["confirmation_io"]["stop_reason"], "confirmation_retry_budget_exhausted")
        self.assertEqual(self.fixture.opened, [])

    def test_shutdown_interrupts_wait_without_another_analysis(self):
        outcome, saved, attempted = self.scan_recovery(interrupt=True)
        self.assertEqual(outcome["status"], "no_trade")
        self.assertEqual(len(attempted), 1)
        self.assertEqual(saved["gates"]["confirmation_io"]["stop_reason"], "confirmation_retry_interrupted")
        self.assertEqual(self.fixture.opened, [])


if __name__ == "__main__":
    unittest.main()
