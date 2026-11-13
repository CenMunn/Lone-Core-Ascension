import pytest
from duhe.controller_v2 import ControllerV2
from duhe.rooms_v2 import RoomServiceV2, choice_token
from duhe.storage import Store
from duhe.tactics_v2 import validate_tactics, tactic_token


def test_vote_preserves_ai_tactic_intent_and_stale_vote_is_rejected(tmp_path):
    store = Store(tmp_path / 'rooms.sqlite'); c = ControllerV2(store); rooms = RoomServiceV2(store)
    cid = c.create('owner')
    c.act('owner', cid, {'action': 'opening'}, 0, 'opening')
    node = c.act('owner', cid, {'action': 'start_encounter', 'monster_id': 'polluted_beetle'}, 1, 'fight')
    choices = validate_tactics({'choices': [{'label': '攻击关节', 'intent': '切向甲虫左腿',
        'multiplier': 1.3, 'energy_cost': 10, 'effect': 'weaken'}]}, node['state'])
    store.set_tactics_v2('owner', cid, node['id'], choices)
    node = store.node('owner', cid)
    token = choice_token(node, {'action': 'use_tactic', 'token': tactic_token(node, 0)})
    room = rooms.create('owner', cid)
    guest = rooms.join(room['invite_token'], '玩家乙')
    rooms.vote(room['host_token'], 2, token); rooms.vote(guest['member_token'], 2, token)
    locked = rooms.lock_round(room['host_token'], 2)
    assert locked['request']['action'] == 'frozen_tactic'
    result = c.act('owner', cid, locked['request'], locked['revision'], locked['operation_id'])
    assert result['event']['player_intent'] == '切向甲虫左腿'
    rooms.finish_round(room['host_token'], 2, True)
    with pytest.raises(ValueError):
        rooms.vote(guest['member_token'], 2, token)


def test_failed_round_retries_frozen_tactic_after_recommendations_refresh(tmp_path):
    store = Store(tmp_path / 'rooms.sqlite'); c = ControllerV2(store); rooms = RoomServiceV2(store)
    cid = c.create('owner'); c.act('owner', cid, {'action':'opening'}, 0, 'open')
    node = c.act('owner', cid, {'action':'start_encounter','monster_id':'polluted_beetle'}, 1, 'fight')
    proposal = {'label':'攻击关节','intent':'切向甲虫左腿','multiplier':1.3,'energy_cost':10,'effect':'weaken'}
    store.set_tactics_v2('owner', cid, node['id'], validate_tactics({'choices':[proposal]}, node['state']))
    node = store.node('owner', cid)
    vote = choice_token(node, {'action':'use_tactic','token':tactic_token(node, 0)})
    room = rooms.create('owner', cid); rooms.vote(room['host_token'], 2, vote)
    locked = rooms.lock_round(room['host_token'], 2)
    rooms.finish_round(room['host_token'], 2, False)
    replacement = dict(proposal, label='另一战术', intent='攻击背部', multiplier=1.1)
    store.set_tactics_v2('owner', cid, node['id'], validate_tactics({'choices':[replacement]}, node['state']))
    retry = rooms.lock_round(room['host_token'], 2)
    assert retry['operation_id'] == locked['operation_id'] and retry['request'] == locked['request']
    result = c.act('owner', cid, retry['request'], retry['revision'], retry['operation_id'])
    assert result['event']['player_intent'] == '切向甲虫左腿'
