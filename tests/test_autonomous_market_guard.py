import copy
import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import autonomous_market_guard as guard
import autonomous_contest as contest
import autonomous_scan_audit as audit
from tests.test_autonomous_contest import candidate, OperationInsertDb


NOW = datetime(2026, 10, 18, 12, 2, tzinfo=timezone.utc)


def context():
    interval = guard.INTERVAL_MS
    count = guard.REQUIRED_CANDLES - 1
    end = int(NOW.timestamp() * 1000) // interval * interval - 1
    materials = {s: {"interval_seconds": interval // 1000,
                    "selected": [{"close": 100., "close_time_ms": end - i * interval}
                                 for i in range(count, -1, -1)]} for s in contest.SYMBOLS}
    return guard.capture_context(materials, contest.SYMBOLS, NOW), materials


def book(side="long", entry=100., symbol="BTCUSDT"):
    return [{"symbol": symbol, "side": side, "open_count": 1, "min_entry": entry,
             "max_entry": entry, "notional": 1000., "units": 1000. / entry, "invalid_count": 0}]


class MarketExposureGuardTests(unittest.TestCase):
    def test_day_direction_cannot_hide_recent_reversal_in_either_direction(self):
        for side, mark, background, wanted in (("long", 99., 90., "bearish"),
                                                ("short", 101., 110., "bullish")):
            with self.subTest(side=side):
                ctx, _ = context()
                for anchor in ctx["anchors"].values():
                    anchor["prices"].update({name: background for name in guard.CONTEXT_WINDOWS})
                state = guard.assess(ctx, book(side), {s: mark for s in contest.SYMBOLS}, NOW)
                self.assertEqual(state["market"]["direction"], wanted)
                self.assertNotEqual(state["market"]["windows"]["24h"]["direction"], wanted)
                self.assertEqual(state["decisions"][side]["status"], "blocked")

    def test_recent_conflict_defers_losing_exposure_instead_of_averaging_signs(self):
        ctx, _ = context()
        for anchor in ctx["anchors"].values():
            anchor["prices"]["15m"] = 101.
            anchor["prices"]["1h"] = 98.
        positions = book("long", entry=101.) + book("short", entry=98., symbol="ETHUSDT")
        state = guard.assess(ctx, positions, {s: 99. for s in contest.SYMBOLS}, NOW)
        self.assertEqual(state["market"]["direction"], "conflict")
        for side in ("long", "short"):
            self.assertEqual(state["decisions"][side]["status"], "deferred")
            self.assertEqual(state["decisions"][side]["reason"], "market_recent_conflict_with_losing_exposure")

    def test_identical_cached_context_for_three_bots_without_more_provider_calls(self):
        calls = []
        def provider(symbol, interval, count, start_time_ms=None, end_time_ms=None):
            calls.append((symbol, interval))
            step = guard.INTERVAL_MS
            end = int(NOW.timestamp()*1000) // step * step - 1
            rows = [[end - i*step - step + 1, 100., 101., 89., 100., 1., end - i*step]
                    for i in range(guard.REQUIRED_CANDLES - 1, -1, -1)]
            rows[0][4] = 90.  # Day up, current hour down.
            return rows
        loader = contest.MemoizedKlineLoader(provider)
        for symbol in contest.SYMBOLS:
            loader(symbol, "5m", guard.REQUIRED_CANDLES)
        results = []
        for policy in contest.PARTICIPANT_POLICIES:
            ctx = contest._common_market_context(loader, NOW)
            state = guard.assess(ctx, book(), {s: 99. for s in contest.SYMBOLS}, NOW)
            value = candidate(edge=.15)
            guard.apply([value], state, ctx)
            self.assertFalse(value.eligible_for(policy))
            results.append(state)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        self.assertEqual(len(calls), len(contest.SYMBOLS))

    def test_never_substitutes_swing_six_hour_candles_for_common_source(self):
        _, materials = context()
        for item in materials.values():
            item["interval_seconds"] = 21600
        invalid = guard.capture_context(materials, contest.SYMBOLS, NOW)
        state = guard.assess(invalid, book(), {s: 99. for s in contest.SYMBOLS}, NOW)
        self.assertEqual(state["market"]["direction"], "unknown")
        self.assertEqual(state["decisions"]["long"]["status"], "deferred")

    def test_cache_does_not_accept_open_candles_or_conflicting_closed_prices(self):
        step = guard.INTERVAL_MS
        end = int(NOW.timestamp()*1000) // step * step - 1
        closed = [end-step+1, 100., 101., 99., 100., 1., end]
        future = [end+1, 100., 120., 99., 120., 1., end+step]
        def provider(symbol, interval, count, **kwargs):
            row = list(closed)
            if count == 3:
                row[4] = 99.
            return [row, future]
        loader = contest.MemoizedKlineLoader(provider)
        loader("BTCUSDT", "5m", 2)
        self.assertEqual(loader.closed_tail("BTCUSDT", "5m", int(NOW.timestamp()*1000), 2), [closed])
        loader("BTCUSDT", "5m", 3)
        with self.assertRaisesRegex(ValueError, "conflicting_closed_prices"):
            loader.closed_tail("BTCUSDT", "5m", int(NOW.timestamp()*1000), 2)

    def test_symmetric_veto_on_all_three_bots_without_changing_forecast(self):
        for policy in contest.PARTICIPANT_POLICIES:
            for side, mark, direction in (("long", 99., "bearish"), ("short", 101., "bullish")):
                with self.subTest(horizon=policy.time_horizon, side=side):
                    ctx, _ = context()
                    state = guard.assess(ctx, book(side), {s: mark for s in contest.SYMBOLS}, NOW)
                    self.assertEqual(state["market"]["direction"], direction)
                    value = candidate(edge=.95, tp=.975, unresolved=0.)
                    value.side = side
                    value.analysis_result = {"snapshot": {"original": True}}
                    original = copy.deepcopy(value.analysis_result)
                    guard.apply([value], state, ctx)
                    self.assertFalse(value.eligible_for(policy))
                    self.assertEqual(value.tp_probability, .975)
                    self.assertEqual(value.analysis_result, original)
                    self.assertEqual(state["decisions"][side]["status"], "blocked")
                    opposite = "short" if side == "long" else "long"
                    self.assertEqual(state["decisions"][opposite]["status"], "allowed")

    def test_no_positions_no_forced_direction_or_position_cap(self):
        ctx, _ = context()
        state = guard.assess(ctx, [], {s: 99. for s in contest.SYMBOLS}, NOW)
        self.assertTrue(all(d["status"] == "allowed" for d in state["decisions"].values()))
        positions = book(entry=90.)
        positions[0]["open_count"] = 10000
        state = guard.assess(ctx, positions, {s: 99. for s in contest.SYMBOLS}, NOW)
        self.assertEqual(state["decisions"]["long"]["status"], "allowed")

    def test_one_losing_position_is_not_hidden_by_profitable_aggregate(self):
        ctx, _ = context()
        positions = book(entry=90.)
        positions[0].update(open_count=2, max_entry=110., notional=2000., units=1000/90+1000/110)
        state = guard.assess(ctx, positions, {s: 99.5 for s in contest.SYMBOLS}, NOW)
        self.assertGreater(state["book"]["long"]["gross_pnl"], 0)
        self.assertEqual(state["decisions"]["long"]["status"], "blocked")

    def test_btc_and_four_of_six_are_required_not_candidate_alone(self):
        ctx, _ = context()
        marks = {s: 101. for s in contest.SYMBOLS}
        marks["BTCUSDT"] = 99.
        state = guard.assess(ctx, book(), marks, NOW)
        self.assertEqual(state["market"]["direction"], "mixed")
        for symbol in ("ETHUSDT", "SOLUSDT", "BNBUSDT"):
            marks[symbol] = 99.
        state = guard.assess(ctx, book(), marks, NOW)
        self.assertEqual(state["decisions"]["long"]["status"], "blocked")
        marks["BTCUSDT"] = 101.
        marks["XRPUSDT"] = 99.
        self.assertEqual(guard.assess(ctx, book(), marks, NOW)["market"]["direction"], "mixed")

    def test_missing_fresh_quote_defers_not_passes_or_probability_zero(self):
        ctx, _ = context()
        marks = {s: 99. for s in contest.SYMBOLS if s != "BTCUSDT"}
        state = guard.assess(ctx, book(), marks, NOW)
        self.assertEqual(state["decisions"]["long"]["status"], "deferred")
        self.assertIsNone(state["book"]["long"]["gross_pnl"])

    def test_closed_context_expiry_and_future_are_not_usable(self):
        ctx, materials = context()
        marks = {s: 99. for s in contest.SYMBOLS}
        for at in (NOW - timedelta(seconds=1), NOW + timedelta(seconds=301)):
            self.assertEqual(guard.assess(ctx, book(), marks, at)["decisions"]["long"]["status"], "deferred")
        for change in ("future", "gap", "nan"):
            altered = copy.deepcopy(materials)
            row = altered["BTCUSDT"]["selected"][-1]
            if change == "future": row["close_time_ms"] = int(NOW.timestamp()*1000) + 300000
            if change == "gap": row["close_time_ms"] -= 300000
            if change == "nan": row["close"] = float("nan")
            invalid = guard.capture_context(altered, contest.SYMBOLS, NOW)
            self.assertIn("BTCUSDT", invalid["missing"])
            self.assertEqual(guard.assess(invalid, book(), marks, NOW)["decisions"]["long"]["status"], "deferred")

    def test_recovers_on_new_scan_without_hysteresis_or_deleted_positions(self):
        ctx, _ = context()
        value = candidate(edge=.15)
        state = guard.assess(ctx, book(), {s: 99. for s in contest.SYMBOLS}, NOW)
        guard.apply([value], state, ctx)
        state = guard.assess(ctx, book(), {s: 101. for s in contest.SYMBOLS}, NOW)
        guard.apply([value], state, ctx)
        self.assertIsNone(value.rejection_code)
        self.assertEqual(value.entry_guard["status"], "allowed")

    def test_compact_evidence_and_audit_no_candles_no_new_analyses(self):
        ctx, _ = context()
        state = guard.assess(ctx, book(), {s: 99. for s in contest.SYMBOLS}, NOW)
        records = [audit.candidate_record(candidate(edge=.15), contest.PARTICIPANT_POLICIES[0])]
        audit.apply_entry_guard(records, state, phase="panel")
        encoded = audit.encode_audit(records, contest.PARTICIPANT_POLICIES[0],
                                     gates={"market_exposure_guard": {"panel": state}})
        result = audit.decode_audit(encoded)
        self.assertEqual(result["evaluated_analyses"], 1)
        self.assertFalse(result["analyses"][0]["eligible"])
        self.assertEqual(result["analyses"][0]["tp_probability"], .45)
        self.assertNotIn("candles", encoded)
        self.assertLess(len(json.dumps(state).encode()), 6000)

    def test_aggregated_query_scopes_account_season_and_actual_open_positions(self):
        from contextlib import closing
        with closing(sqlite3.connect(":memory:")) as db:
            db.row_factory = sqlite3.Row
            db.execute("CREATE TABLE operations(user_id,mode,contest_season_id,status,symbol,side,entry,margin,leverage)")
            for user, mode, season, status, entry in (
                (1, "contest", 2, "OPEN", 110.), (1, "contest", 2, "OPEN", 90.),
                (2, "contest", 2, "OPEN", 200.), (1, "training", 2, "OPEN", 200.),
                (1, "contest", 3, "OPEN", 200.), (1, "contest", 2, "CLOSED", 200.),
                (1, "contest", 2, "PENDING_ENTRY", 200.)):
                db.execute("INSERT INTO operations VALUES(?,?,?,?,?,?,?,?,?)",
                           (user, mode, season, status, "BTCUSDT", "long", entry, 100., 10.))
            rows = guard.read_book(db, 1, 2)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["open_count"], 2)
            self.assertEqual(rows[0]["max_entry"], 110.)
            self.assertAlmostEqual(rows[0]["units"], 1000/110 + 1000/90)

    def test_direct_insert_cannot_bypass_final_guard_even_with_high_tp(self):
        for side, mark in (("long", 99.), ("short", 101.)):
            with self.subTest(side=side):
                db = OperationInsertDb()
                value = candidate(edge=.95, tp=.975, unresolved=0., symbol="ETHUSDT")
                value.side = side
                value.analysis_result = {"snapshot": {}}
                value.market_guard_context = context()[0]
                with patch.object(guard, "read_book", return_value=book(side)), \
                     patch.object(contest, "fresh_market_prices", return_value={s: mark for s in contest.SYMBOLS}):
                    with self.assertRaisesRegex(ValueError, "market_against_losing_" + side):
                        contest._open_selected_operation(db, participant={"id": 1, "user_id": 27},
                            season_id=1, candidate=value, policy=contest.PARTICIPANT_POLICIES[0],
                            execution_entry=100., executed_at=NOW)
                self.assertFalse(any("INSERT" in sql or "UPDATE" in sql for sql, _ in db.calls))

    def test_grouped_evidence_stays_bounded_when_position_count_grows(self):
        ctx, _ = context()
        positions = [row for symbol in contest.SYMBOLS for side in ("long", "short")
                     for row in book(side=side, symbol=symbol)]
        for row in positions:
            row["open_count"] = 10000
        state = guard.assess(ctx, positions, {s: 99. for s in contest.SYMBOLS}, NOW)
        self.assertLess(len(json.dumps(state, separators=(",", ":")).encode()), 6000)

    def test_missing_anchors_cannot_be_called_mixed(self):
        ctx, _ = context()
        ctx["anchors"]["BTCUSDT"]["last_closed_at_ms"] -= 300000
        state = guard.assess(ctx, book(), {s: 99. for s in contest.SYMBOLS}, NOW)
        self.assertEqual(state["market"]["direction"], "unknown")
        self.assertEqual(state["decisions"]["long"]["status"], "deferred")


if __name__ == "__main__":
    unittest.main()
