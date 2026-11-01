import sqlite3
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import autonomous_contest as c
from tests.test_autonomous_contest import OperationInsertDb, Cursor
from tests.test_autonomous_entry_standard import proposal


class LimitedDb(OperationInsertDb):
    engine = 'postgres'

    def __init__(self, count):
        super().__init__(); self.active_count=count

    def execute(self, query, params=None):
        if 'SELECT COUNT(*) AS count FROM operations' in ' '.join(query.split()) and 'contest_season_id' not in query:
            self.calls.append((query,params)); return Cursor({'count':self.active_count})
        return super().execute(query,params)


class OpenLimitTests(unittest.TestCase):
    def test_all_bots_have_eight_effective_slots(self):
        self.assertEqual([p.max_open_positions for p in c.PARTICIPANT_POLICIES],[8,8,8])

    def test_pending_capital_counts_and_other_users_or_closed_positions_do_not(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE operations(user_id INTEGER,mode TEXT,status TEXT)')
        db.executemany('INSERT INTO operations VALUES(?,?,?)',[(1,'contest','OPEN'),(1,'contest','PENDING_ENTRY'),
            (1,'contest','CLOSED'),(1,'training','OPEN'),(2,'contest','OPEN')])
        self.assertEqual(c._active_operation_count(db,1),2)
        db.close()

    def test_eighth_entry_allowed_and_ninth_rejected_for_every_bot(self):
        for policy in c.PARTICIPANT_POLICIES:
            item=proposal(policy,tp=.75,sl=.15,unresolved=.1)
            for count in (7,8):
                db=LimitedDb(count)
                with patch.object(c,'_assess_entry_guard',return_value={}), patch.object(c.market_guard,'apply'):
                    if count==8:
                        with self.assertRaisesRegex(ValueError,'open_position_limit'):
                            c._open_selected_operation(db,participant={'user_id':1,'id':1},season_id=2,
                                candidate=item,policy=policy,execution_entry=100.,executed_at=datetime.now(timezone.utc))
                        self.assertFalse(any('INSERT INTO operations' in q for q,_ in db.calls))
                    else:
                        item.entry_guard={'status':'allowed','reason':'test_allowed'}
                        ids=c._open_selected_operation(db,participant={'user_id':1,'id':1},season_id=2,
                            candidate=item,policy=policy,execution_entry=100.,executed_at=item.analyzed_at)
                        self.assertEqual(ids,(501,601))
                        self.assertEqual(sum('INSERT INTO operations' in q for q,_ in db.calls),1)
                self.assertIn('pg_advisory_xact_lock',db.calls[0][0])


if __name__=='__main__':unittest.main()
