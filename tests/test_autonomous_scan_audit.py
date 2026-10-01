import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import autonomous_contest as contest
import autonomous_scan_audit as audit
from tests.test_autonomous_contest import candidate


class AuditContractTests(unittest.TestCase):
    def test_all_twelve_results_keep_precision_without_snapshots(self):
        policy = contest.PARTICIPANT_POLICIES[1]
        values = []
        for symbol in policy.symbols:
            for side in ("long", "short"):
                value = candidate(edge=.08, symbol=symbol)
                value.side = side
                value.entry = 1.06781234
                value.take_profit = 1.08456789
                value.stop_loss = 1.05105679
                value.rejection_code = "edge_below_horizon_gate"
                value.analysis_result = {"snapshot": {"candles": "x" * 1_000_000}}
                value.observational_json = {"raw": "x" * 1_000_000}
                values.append(value)
        records = [audit.candidate_record(value, policy) for value in values]
        text = audit.encode_audit(records, policy)
        restored = audit.decode_audit(text)
        self.assertEqual(restored["coverage"], "complete")
        self.assertEqual(len(restored["analyses"]), 12)
        self.assertEqual(restored["analyses"][0]["entry"], 1.06781234)
        self.assertEqual(restored["analyses"][0]["tp_probability"], values[0].tp_probability)
        self.assertTrue(all(not row["eligible"] for row in restored["analyses"]))
        self.assertNotIn("candles", text)
        self.assertNotIn("snapshot", text)
        self.assertLess(len(text.encode("utf-8")), 6000)

    def test_initial_and_final_values_remain_distinct_after_mutation(self):
        policy = contest.PARTICIPANT_POLICIES[1]
        value = candidate(edge=.15)
        records = [audit.candidate_record(value, policy)]
        value.tp_probability = .65
        value.entry = 101.1234567
        records.append(audit.candidate_record(value, policy, phase="confirmation"))
        value.entry = 102.
        restored = audit.decode_audit(audit.encode_audit(records, policy, selected=value))
        self.assertEqual(restored["selected_index"], 1)
        self.assertEqual([r["tp_probability"] for r in restored["analyses"]], [.45, .65])
        self.assertEqual(restored["analyses"][1]["entry"], 101.1234567)

    def test_verbose_failure_is_bounded_but_the_attempt_and_fingerprint_remain(self):
        value = candidate(edge=0)
        value.analysis_status = "failed"
        value.rejection_code = "provider_error:" + "é" * 20_000
        row = audit.candidate_record(value, contest.PARTICIPANT_POLICIES[1])
        self.assertTrue(row["reason_truncated"])
        self.assertEqual(len(row["reason_sha256"]), 64)
        self.assertLessEqual(len(row["rejection_code"].encode()), 256)
        self.assertEqual(row["analysis_status"], "failed")

    def test_each_short_alternative_and_missing_price_are_recorded(self):
        policy = contest.PARTICIPANT_POLICIES[0]
        records = []
        calls = []
        def engine(proposal, **kwargs):
            calls.append(proposal)
            return {"tp_probability": .60, "sl_probability": .20, "range_probability": .20,
                    "snapshot": {}, "model_trace": {"artifact_id": "artifact",
                    "stage_traces": [{"selected_analogs": 240}]}}
        def plans(material, *, side, entry):
            sign = 1 if side == "long" else -1
            return [{"version": "test", "take_profit": entry + sign * step,
                     "stop_loss": entry - sign * step} for step in (1., 2.)]
        prices = {symbol: 100. for symbol in policy.symbols if symbol != "XRPUSDT"}
        with patch.object(contest, "load_horizon_material", return_value={}), \
             patch.object(contest.short_planner, "proposals", side_effect=plans):
            values = contest.analyze_candidates(
                policy, prices, datetime(2026, 10, 1, tzinfo=timezone.utc),
                analysis_runner=engine, sigma_loader=lambda *args: .01,
                audit_records=records,
            )
        self.assertEqual(len(values), 12)
        self.assertEqual(len(calls), 20)
        self.assertEqual(len(records), 22)
        missing = [row for row in records if row["symbol"] == "XRPUSDT"]
        self.assertEqual(len(missing), 2)
        self.assertTrue(all(row["rejection_code"] == "worker_price_unavailable" for row in missing))
        btc = [row for row in records if row["symbol"] == "BTCUSDT" and row["side"] == "long"]
        self.assertEqual([row["take_profit"] for row in btc], [101., 102.])


class AuditReportTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        connection = self.db
        class Schema:
            def executescript(self, script):
                for statement in script.split(";"):
                    if statement.strip().startswith("CREATE TABLE"):
                        connection.execute(statement.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY")
                                           .replace("jsonb_typeof", "json_type").replace("::jsonb", ""))
        contest.ensure_autonomous_storage(Schema())
        self.db.execute("""INSERT INTO autonomous_contest_participants
            (id,code,user_id,display_name,time_horizon,policy_version,cadence_minutes,
            daily_operation_limit,max_open_positions,edge_threshold,min_tp_probability,
            max_unresolved_probability,min_analogs_per_stage,margin,leverage,symbols_json)
            VALUES (1,'auto_intraday_wide',1,'Medium','intraday_wide','v',60,2,2,.1,.3,.35,80,100,1,'[]')""")
        self.start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        policy = contest.PARTICIPANT_POLICIES[1]
        self.payload = audit.encode_audit([audit.candidate_record(candidate(edge=.08), policy)], policy)
        for i in range(1, 5):
            at = (self.start + timedelta(hours=i)).isoformat()
            self.db.execute("""INSERT INTO autonomous_scan_runs
                (id,participant_id,contest_season_id,scan_slot_at,status,candidates_evaluated,
                engine_version,policy_version,dry_run,candidate_audit_json)
                VALUES (?,1,1,?,'no_trade',12,'engine','policy',FALSE,?)""",
                (i, at, self.payload if i > 1 else None))
        self.db.execute("""INSERT INTO autonomous_candidate_observations
            (scan_run_id,participant_id,contest_season_id,symbol,side,time_horizon,analyzed_at,
            evaluation_due_at,analysis_status,storage_reason,engine_version,observational_json)
            VALUES (1,1,1,'BTCUSDT','long','intraday_wide',?,?,'evaluated','boundary','engine',?)""",
            (self.start.isoformat(), self.start.isoformat(), '{"raw":"' + "x" * 100000 + '"}'))

    def tearDown(self):
        self.db.close()

    def report(self, **kwargs):
        return audit.scan_audit_report(self.db, participant_code="auto_intraday_wide",
            start_at=self.start, end_at=self.start + timedelta(days=1), **kwargs)

    def test_cursor_pages_show_every_scan_without_reading_snapshots(self):
        first = self.report(limit=2)
        second = self.report(limit=2, before_id=first["next_cursor"])
        self.assertEqual([row["id"] for row in first["scans"] + second["scans"]], [4,3,2,1])
        self.assertIsNone(second["next_cursor"])
        old = second["scans"][-1]["audit"]
        self.assertEqual(old["coverage"], "legacy_sample")
        self.assertEqual(old["missing_proposals"], 11)
        self.assertNotIn("observational_json", str(second))
        self.assertLess(second["database_payload_bytes"], 6000)

    def test_page_limits_reject_large_reads_without_querying(self):
        for limit in (0, 13):
            with self.assertRaisesRegex(ValueError, "page_invalid"):
                self.report(limit=limit)
        with self.assertRaisesRegex(ValueError, "timezone"):
            audit.scan_audit_report(self.db, participant_code="auto_intraday_wide",
                start_at=self.start.replace(tzinfo=None), end_at=self.start + timedelta(days=1))

    def test_owner_route_and_authentication(self):
        import app
        from fastapi import HTTPException
        with patch.object(app, "current_user", return_value={"username": "other"}), \
             patch.object(app, "connect") as connect:
            with self.assertRaises(HTTPException) as caught:
                app.bot_scan_audit(self.start, self.start + timedelta(days=1))
            self.assertEqual(caught.exception.status_code, 403)
            connect.assert_not_called()
        with patch.object(app, "current_user", return_value={"username": "mauriciomc"}), \
             patch.object(app, "connect") as connect:
            connect.return_value.__enter__.return_value = self.db
            response = app.bot_scan_audit(self.start, self.start + timedelta(days=1), limit=2)
            self.assertEqual(response.headers["cache-control"], "private, no-store")
            self.assertEqual(len(json.loads(response.body)["scans"]), 2)


if __name__ == "__main__":
    unittest.main()
