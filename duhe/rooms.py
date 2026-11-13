"""Persistent invitation rooms; all vote and lock transitions are transactions."""
from __future__ import annotations

import hashlib
import json
import secrets
from collections import Counter

from .storage import _id, _json
from . import recommendations


def _hash(token):
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


def _actions(state):
    from .rules import actions_for
    return actions_for(state)


class RoomService:
    def __init__(self, store):
        self.store = store
        with store._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, owner TEXT NOT NULL, invite_hash TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS room_members(token_hash TEXT PRIMARY KEY, room_id TEXT NOT NULL, member_id TEXT NOT NULL, display_name TEXT NOT NULL, is_host INTEGER NOT NULL);
            ''')

    def _auth(self, db, token, host=False):
        member = db.execute('SELECT * FROM room_members WHERE token_hash=?', (_hash(token),)).fetchone()
        if member is None or (host and not member['is_host']):
            raise PermissionError('Invalid room token or host permission')
        room = db.execute('SELECT * FROM rooms WHERE id=?', (member['room_id'],)).fetchone()
        if room is None:
            raise PermissionError('Room unavailable')
        room = dict(room)
        room['data'] = json.loads(room['body'])
        return room, dict(member)

    def _save(self, db, room):
        db.execute('UPDATE rooms SET body=? WHERE id=?', (_json(room['data']), room['id']))

    def _sync(self, room, campaign):
        data = room['data']
        if not data['locked'] and data['revision'] != campaign['revision']:
            data.update(revision=campaign['revision'], votes={}, operation_id=None, action_id=None)

    def _snapshot(self, db, room):
        c = self.store._campaign(db, room['owner'], room['campaign_id'])
        self._sync(room, c)
        members = [dict(r) for r in db.execute('SELECT member_id,display_name,is_host FROM room_members WHERE room_id=? ORDER BY rowid', (room['id'],))]
        return dict(room_id=room['id'], campaign_id=room['campaign_id'], owner=room['owner'],
                    current_node=c['current_node'], revision=c['revision'], members=members,
                    votes=dict(room['data']['votes']), locked=room['data']['locked'],
                    round_revision=room['data']['revision'], retry_action_id=room['data'].get('action_id'))

    def create(self, owner, cid):
        invite, host, rid = secrets.token_urlsafe(32), secrets.token_urlsafe(32), _id()
        with self.store._db(True) as db:
            c = self.store._campaign(db, owner, cid)
            body = dict(revision=c['revision'], votes={}, locked=False, operation_id=None, action_id=None)
            db.execute('INSERT INTO rooms VALUES(?,?,?,?,?)', (rid, cid, owner, _hash(invite), _json(body)))
            db.execute('INSERT INTO room_members VALUES(?,?,?,?,1)', (_hash(host), rid, _id(), '房主'))
        return dict(room_id=rid, invite_token=invite, host_token=host)

    def join(self, invite_token, display_name):
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 40:
            raise ValueError('Display name must contain 1-40 characters')
        token = secrets.token_urlsafe(32)
        with self.store._db(True) as db:
            room = db.execute('SELECT * FROM rooms WHERE invite_hash=?', (_hash(invite_token),)).fetchone()
            if room is None:
                raise PermissionError('Invalid invitation')
            count = db.execute('SELECT COUNT(*) FROM room_members WHERE room_id=?', (room['id'],)).fetchone()[0]
            if count >= 4:
                raise ValueError('Room already has four members')
            db.execute('INSERT INTO room_members VALUES(?,?,?,?,0)', (_hash(token), room['id'], _id(), display_name.strip()))
            return dict(room_id=room['id'], member_token=token)

    def snapshot(self, token):
        with self.store._db(True) as db:
            room, _ = self._auth(db, token)
            result = self._snapshot(db, room)
            self._save(db, room)
            return result

    def vote(self, token, revision, action_id):
        with self.store._db(True) as db:
            room, member = self._auth(db, token)
            c = self.store._campaign(db, room['owner'], room['campaign_id'])
            self._sync(room, c)
            data = room['data']
            if revision != c['revision'] or data['locked']:
                raise ValueError('Stale or locked round')
            node = self.store._node(db, c['id'], c['current_node'])
            if isinstance(action_id,str) and action_id.startswith('ai:'):
                # Legacy unversioned tokens are unsafe to vote on after a refresh.
                if len(action_id.split(':'))!=4:raise ValueError('推荐已更新，请刷新后重新投票。')
                recommendations.resolve(node,action_id)
            elif action_id not in {a['id'] for a in _actions(node['state'])}:
                raise ValueError('Action is not legal in current state')
            data['votes'][member['member_id']] = action_id
            self._save(db, room)
            return self._snapshot(db, room)

    def lock_round(self, host_token, revision, tie_action_id=None):
        with self.store._db(True) as db:
            room, _ = self._auth(db, host_token, host=True)
            c = self.store._campaign(db, room['owner'], room['campaign_id'])
            self._sync(room, c)
            data = room['data']
            if revision != c['revision'] or data['locked']:
                raise ValueError('Stale or already locked round')
            node=self.store._node(db, c['id'], c['current_node'])
            legal = {a['id'] for a in _actions(node['state'])}
            for i,item in enumerate(node.get('meta',{}).get('recommendations',[])):
                if item.get('action_id') in legal:legal.add(recommendations.choice_token(node,i))
            retry=bool(data.get('action_id'))
            if retry:
                action = data['action_id']
                if tie_action_id is not None and tie_action_id != action:
                    raise ValueError('Retry must keep the original action and operation')
            else:
                counts = Counter(data['votes'].values())
                if not counts or any(a not in legal for a in counts):
                    raise ValueError('No valid votes')
                best = max(counts.values())
                winners = [a for a, count in counts.items() if count == best]
                if len(winners) > 1:
                    if tie_action_id not in winners:
                        raise ValueError('Host must choose one of the tied actions')
                    action = tie_action_id
                else:
                    action = winners[0]
            frozen_base=data.get('resolved_action_id')
            if retry and frozen_base in {a['id'] for a in _actions(node['state'])}:
                legal.add(action)
            if action not in legal:
                raise ValueError('Chosen action is no longer legal')
            if retry and frozen_base:
                base,intent=frozen_base,data.get('intent')
            else:base,intent=recommendations.resolve(node,action) if action.startswith('ai:') else (action,None)
            # A failed generation retries exactly the frozen narrative intent.
            if data.get('operation_id'):intent=data.get('intent',intent)
            data.update(locked=True, operation_id=data.get('operation_id') or _id(), action_id=action,intent=intent,resolved_action_id=base)
            self._save(db, room)
            return dict(campaign_id=c['id'], owner=room['owner'], action_id=base,choice_id=action,intent=intent,
                        parent_id=c['current_node'], revision=c['revision'], operation_id=data['operation_id'])

    def finish_round(self, host_token, revision, success: bool):
        with self.store._db(True) as db:
            room, _ = self._auth(db, host_token, host=True)
            data = room['data']
            if not data['locked'] or data['revision'] != revision:
                raise ValueError('No matching locked round')
            c = self.store._campaign(db, room['owner'], room['campaign_id'])
            if success:
                committed = db.execute('SELECT node_id FROM operations WHERE campaign_id=? AND operation_id=?', (c['id'], data['operation_id'])).fetchone()
                if committed is None:
                    raise ValueError('Round has not committed')
                data.update(locked=False, revision=c['revision'], votes={}, operation_id=None, action_id=None)
            else:
                data['locked'] = False
                self._sync(room, c)
            self._save(db, room)
