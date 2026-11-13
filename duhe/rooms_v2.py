"""Voting over exact, node-bound v2 requests."""
import base64
from collections import Counter
import hashlib
import json
from .controller_v2 import ControllerV2
from .rooms import RoomService
from .storage import _id


def choice_token(node, request):
    if not isinstance(request, dict):
        raise ValueError('行动请求无效')
    raw = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    payload = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    digest = hashlib.sha256((node['id'] + ':' + payload).encode()).hexdigest()[:12]
    return f"v2:{node['id']}:{payload}:{digest}"


def decode_choice(node, token):
    parts = str(token).split(':')
    if len(parts) != 4 or parts[0] != 'v2' or parts[1] != node['id'] or len(parts[2]) > 4000:
        raise ValueError('投票行动已过期')
    digest = hashlib.sha256((node['id'] + ':' + parts[2]).encode()).hexdigest()[:12]
    if digest != parts[3]:
        raise ValueError('投票行动内容无效')
    try:
        raw = base64.urlsafe_b64decode(parts[2] + '=' * (-len(parts[2]) % 4))
        request = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('投票行动格式无效') from None
    if not isinstance(request, dict) or not isinstance(request.get('action'), str):
        raise ValueError('投票行动格式无效')
    return request


class RoomServiceV2(RoomService):
    def _validate(self, owner, cid, revision, node, token):
        request = decode_choice(node, token)
        if request['action'] in ('frozen_tactic', 'frozen_suggestion'):
            raise ValueError('冻结方案只能由房间在锁定时生成')
        ControllerV2(self.store).prepare(owner, cid, request, revision, 'vote-check-' + _id())
        return request

    def vote(self, token, revision, action_id):
        with self.store._db(True) as db:
            room, member = self._auth(db, token)
            c = self.store._campaign(db, room['owner'], room['campaign_id'])
            self._sync(room, c); data = room['data']
            if revision != c['revision'] or data['locked']:
                raise ValueError('投票已过期或已锁定')
            node = self.store._node(db, c['id'], c['current_node'])
            self._validate(room['owner'], c['id'], revision, node, action_id)
            data['votes'][member['member_id']] = action_id
            self._save(db, room)
            return self._snapshot(db, room)

    def lock_round(self, host_token, revision, tie_action_id=None):
        with self.store._db(True) as db:
            room, _ = self._auth(db, host_token, host=True)
            c = self.store._campaign(db, room['owner'], room['campaign_id'])
            self._sync(room, c); data = room['data']
            if revision != c['revision'] or data['locked']:
                raise ValueError('投票已过期或已锁定')
            node = self.store._node(db, c['id'], c['current_node'])
            action = data.get('action_id')
            if action:
                if tie_action_id is not None and tie_action_id != action:
                    raise ValueError('重试必须保留原行动')
            else:
                counts = Counter(data['votes'].values())
                if not counts:
                    raise ValueError('请先投票')
                winners = [item for item, n in counts.items() if n == max(counts.values())]
                if len(winners) > 1 and tie_action_id not in winners:
                    raise ValueError('票数相同时请由房主选择')
                action = tie_action_id if len(winners) > 1 else winners[0]
            if data.get('frozen_request') and data.get('operation_id'):
                request = data['frozen_request']
            else:
                request = self._validate(room['owner'], c['id'], revision, node, action)
                if request['action'] == 'use_tactic':
                    from .tactics_v2 import resolve_tactic
                    request = {'action':'frozen_tactic','proposal':resolve_tactic(node,request['token'])}
                elif request['action'] == 'use_suggestion':
                    from .suggestions_v2 import resolve
                    actual,intent=resolve(node,request['token'])
                    request = {'action':'frozen_suggestion','request':actual,'intent':intent}
            data.update(locked=True, operation_id=data.get('operation_id') or _id(),
                        action_id=action, resolved_action_id=request['action'], frozen_request=request)
            self._save(db, room)
            return {'campaign_id': c['id'], 'owner': room['owner'], 'request': request,
                    'parent_id': c['current_node'], 'revision': c['revision'], 'operation_id': data['operation_id']}
