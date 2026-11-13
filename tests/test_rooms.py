import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from duhe.storage import Store
from duhe.rooms import RoomService


class RoomTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / 'test.db')
        self.cid = self.store.create('owner', {'mode': 'demo'})
        self.rooms = RoomService(self.store)
        self.room = self.rooms.create('owner', self.cid)
        self.host = self.room['host_token']
        # Rule legality is owned by another module; deterministic legal actions here.
        self.patch = patch('duhe.rooms._actions', return_value=[{'id': 'a'}, {'id': 'b'}])
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_capacity_tokens_and_reconnect(self):
        people = [self.rooms.join(self.room['invite_token'], str(x)) for x in range(3)]
        with self.assertRaises(ValueError):
            self.rooms.join(self.room['invite_token'], 'fifth')
        snapshot = RoomService(self.store).snapshot(people[0]['member_token'])
        self.assertEqual(len(snapshot['members']), 4)
        self.assertNotIn('host_token', str(snapshot))
        with self.assertRaises(PermissionError):
            self.rooms.snapshot('invalid')
        with self.assertRaises(PermissionError):
            self.rooms.lock_round(people[0]['member_token'], 0)

    def test_votes_tie_lock_and_failure_retry(self):
        guest = self.rooms.join(self.room['invite_token'], 'guest')['member_token']
        self.rooms.vote(self.host, 0, 'b')
        self.rooms.vote(self.host, 0, 'a')
        self.rooms.vote(guest, 0, 'b')
        with self.assertRaises(ValueError):
            self.rooms.lock_round(self.host, 0)
        lock = self.rooms.lock_round(self.host, 0, 'b')
        self.assertEqual(lock['action_id'], 'b')
        with self.assertRaises(ValueError):
            self.rooms.vote(guest, 0, 'a')
        with self.assertRaises(ValueError):
            self.rooms.lock_round(self.host, 0, 'b')
        self.rooms.finish_round(self.host, 0, False)
        again = self.rooms.lock_round(self.host, 0, 'b')
        self.assertEqual(again['operation_id'], lock['operation_id'])
        self.store.commit('owner', self.cid, lock['parent_id'], 0, lock['operation_id'], {'mode': 'demo'}, 'new', {})
        self.rooms.finish_round(self.host, 0, True)
        with self.assertRaises(ValueError):
            self.rooms.vote(guest, 0, 'a')
        self.assertEqual(self.rooms.snapshot(guest)['revision'], 1)

    def test_simultaneous_locks_one_winner(self):
        self.rooms.vote(self.host, 0, 'a')
        def lock(_):
            try:
                return self.rooms.lock_round(self.host, 0)
            except ValueError:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lock, range(2)))
        self.assertEqual(sum(x is not None for x in results), 1)

    def test_illegal_action_and_stale_revision(self):
        with self.assertRaises(ValueError):
            self.rooms.vote(self.host, 0, 'invented')
        with self.assertRaises(ValueError):
            self.rooms.vote(self.host, 99, 'a')


if __name__ == '__main__':
    unittest.main()
