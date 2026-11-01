"""Regression: a pooled backend with an empty schema must still find app tables."""
from types import SimpleNamespace
import unittest
from psycopg.pq import TransactionStatus
from db import DbSession


class Connection:
    def __init__(self):
        self.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)
        self.path = ''
        self.statements = []

    def execute(self, query, params=()):
        self.statements.append(query)
        self.info.transaction_status = TransactionStatus.INTRANS
        if query == 'SET LOCAL search_path TO public':
            self.path = 'public'
        elif self.path != 'public':
            raise RuntimeError('relation operations does not exist')
        return SimpleNamespace(fetchone=lambda: {'id': 1})

    def executemany(self, query, rows):
        return self.execute(query)

    def commit(self):
        self.path = ''  # Next transaction may get a different pool backend.
        self.info.transaction_status = TransactionStatus.IDLE

    rollback = commit


class SearchPathTests(unittest.TestCase):
    def test_empty_backend_path_and_each_subsequent_transaction(self):
        connection = Connection()
        session = DbSession(connection)
        for boundary in (session.commit, session.rollback, session.commit):
            self.assertEqual(session.execute('SELECT id FROM operations').fetchone()['id'], 1)
            session.execute('SELECT id FROM recommendations')
            boundary()
        self.assertEqual(connection.statements.count('SET LOCAL search_path TO public'), 3)

    def test_bulk_paths_establish_schema_too(self):
        for action in (lambda db: db.executemany('SELECT id FROM operations', [()]),
                       lambda db: db.executescript('SELECT id FROM operations;SELECT id FROM users;')):
            connection = Connection()
            action(DbSession(connection))
            self.assertEqual(connection.statements[0], 'SET LOCAL search_path TO public')

    def test_schema_setup_errors_are_not_hidden(self):
        connection = Connection()
        def fail(*args):
            raise RuntimeError('connection_failed')
        connection.execute = fail
        with self.assertRaisesRegex(RuntimeError, 'connection_failed'):
            DbSession(connection).execute('SELECT id FROM operations')


if __name__ == '__main__':
    unittest.main()
