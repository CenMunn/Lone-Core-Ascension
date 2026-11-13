import pytest
from duhe.controller_v2 import ControllerV2
from duhe.storage import Store


def test_new_game_saves_operations_as_independent_branch_nodes(tmp_path):
    c = ControllerV2(Store(tmp_path / 'v2.sqlite'))
    cid = c.create('owner')
    opening = c.act('owner', cid, {'action': 'opening'}, 0, 'open')
    assert opening['state']['flags']['system_bound']
    assert opening['state']['story_turn'] == 1
    assert opening['state']['relationships']['heroine']['events']
    rest = c.act('owner', cid, {'action': 'rest'}, 1, 'rest')
    assert rest['state']['story_turn'] == 1
    assert rest['parent_id'] == opening['id']
    with pytest.raises(ValueError):
        c.act('owner', cid, {'action': 'rest'}, 1, 'stale')
    assert c.store.node('owner', cid)['id'] == rest['id']


def test_cross_owner_access_is_rejected(tmp_path):
    c = ControllerV2(Store(tmp_path / 'v2.sqlite'))
    cid = c.create('one')
    with pytest.raises(PermissionError):
        c.act('other', cid, {'action': 'opening'}, 0, 'other-open')


def test_demo_finale_is_explicit_and_can_start_the_last_guardian(tmp_path):
    c = ControllerV2(Store(tmp_path / 'v2.sqlite'))
    cid = c.create('owner', mode='demo', checkpoint='finale')
    state = c.store.node('owner', cid)['state']
    assert state['mode'] == 'demo' and state['demo_checkpoint'] == 'finale'
    assert state['ability_rank'] == 'UR' and state['tower_floor'] == 100
    started = c.act('owner', cid, {'action': 'start_encounter', 'monster_id': 'tower_100'}, 0, 'start')
    assert started['state']['combat']['monster_id'] == 'tower_100'
