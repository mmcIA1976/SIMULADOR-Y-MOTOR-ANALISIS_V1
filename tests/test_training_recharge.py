import sqlite3
import unittest

from app import ensure_training_wallet_funded


class TrainingRechargeTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                starting_balance REAL NOT NULL,
                cash_balance REAL NOT NULL
            );
            CREATE TABLE operations (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                status TEXT NOT NULL,
                margin REAL NOT NULL,
                final_pnl REAL
            );
            CREATE TABLE wallet_events (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL,
                operation_id INTEGER,
                contest_season_id INTEGER,
                note TEXT
            );
            """
        )
        self.db.execute(
            "INSERT INTO users (id, username, starting_balance, cash_balance) VALUES (1, 'hector', 1000, 1000)"
        )

    def tearDown(self):
        self.db.close()

    def test_does_not_recharge_when_training_cash_is_enough(self):
        recharge_count = ensure_training_wallet_funded(self.db, 1)

        self.assertEqual(recharge_count, 0)
        user = self.db.execute("SELECT starting_balance, cash_balance FROM users WHERE id = 1").fetchone()
        self.assertEqual(float(user["starting_balance"]), 1000)
        events = self.db.execute("SELECT COUNT(*) AS count FROM wallet_events").fetchone()
        self.assertEqual(int(events["count"]), 0)

    def test_does_not_recharge_just_because_margin_request_is_too_large(self):
        self.db.execute(
            """
            INSERT INTO operations (user_id, mode, status, margin, final_pnl)
            VALUES (1, 'training', 'CLOSED', 100, -950)
            """
        )

        recharge_count = ensure_training_wallet_funded(self.db, 1)

        self.assertEqual(recharge_count, 0)
        user = self.db.execute("SELECT starting_balance, cash_balance FROM users WHERE id = 1").fetchone()
        self.assertEqual(float(user["starting_balance"]), 1000)
        events = self.db.execute("SELECT COUNT(*) AS count FROM wallet_events").fetchone()
        self.assertEqual(int(events["count"]), 0)

    def test_recharges_when_training_cash_is_depleted(self):
        self.db.execute(
            """
            INSERT INTO operations (user_id, mode, status, margin, final_pnl)
            VALUES (1, 'training', 'CLOSED', 100, -1050)
            """
        )

        recharge_count = ensure_training_wallet_funded(self.db, 1)

        self.assertEqual(recharge_count, 1)
        user = self.db.execute("SELECT starting_balance, cash_balance FROM users WHERE id = 1").fetchone()
        self.assertEqual(float(user["starting_balance"]), 2000)
        self.assertEqual(float(user["cash_balance"]), 950)
        event = self.db.execute(
            "SELECT event_type, amount, balance_after FROM wallet_events WHERE user_id = 1"
        ).fetchone()
        self.assertEqual(event["event_type"], "training_recharge")
        self.assertEqual(float(event["amount"]), 1000)
        self.assertEqual(float(event["balance_after"]), 950)

    def test_can_apply_multiple_training_recharges(self):
        self.db.execute(
            """
            INSERT INTO operations (user_id, mode, status, margin, final_pnl)
            VALUES (1, 'training', 'CLOSED', 100, -2400)
            """
        )

        recharge_count = ensure_training_wallet_funded(self.db, 1)

        self.assertEqual(recharge_count, 2)
        user = self.db.execute("SELECT starting_balance, cash_balance FROM users WHERE id = 1").fetchone()
        self.assertEqual(float(user["starting_balance"]), 3000)
        self.assertEqual(float(user["cash_balance"]), 600)
        events = self.db.execute("SELECT COUNT(*) AS count FROM wallet_events").fetchone()
        self.assertEqual(int(events["count"]), 2)


if __name__ == "__main__":
    unittest.main()
