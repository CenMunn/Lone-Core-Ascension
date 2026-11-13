import pytest
from duhe.tactics_v2 import validate_tactics, tactic_token, resolve_tactic
from duhe.combat import start_encounter, combat_step
from duhe.models_v2 import migrate_state
from duhe.rules import new_game, apply_action


def fight():
    old, _ = apply_action(new_game(), 'opening')
    state = migrate_state(old, story_turn=1, operation_seq=1)
    return start_encounter(state, 'polluted_beetle', 'start')[0]


def test_model_tactics_have_bounded_distinct_rule_effects():
    state = fight()
    choices = validate_tactics({'choices': [
        {'label': '瞄准关节', 'intent': '绕到甲虫侧面攻击腿部', 'multiplier': 1.3, 'energy_cost': 10, 'effect': 'weaken'},
        {'label': '从正面突刺', 'intent': '用维修刀刺向背甲缝隙', 'multiplier': 1.1, 'energy_cost': 6, 'effect': 'none'}]}, state)
    node = {'id': 'node-a', 'state': state, 'meta': {'tactics_v2': choices}}
    token = tactic_token(node, 0)
    proposal = resolve_tactic(node, token)
    changed, event = combat_step(state, {'action': 'tactic', 'proposal': proposal}, 'tactic')
    assert event['damage_to_enemy'] > state['base_attack']
    assert changed['energy'] == state['energy'] - 10
    assert changed['story_turn'] == state['story_turn']
    with pytest.raises(ValueError):
        resolve_tactic({**node, 'id': 'other-node'}, token)


def test_model_cannot_assign_unbounded_power_or_leak_system():
    state = fight()
    with pytest.raises(ValueError):
        validate_tactics({'choices': [{'label': '秒杀', 'intent': '秒杀', 'multiplier': 500, 'energy_cost': 0, 'effect': 'none'}]}, state)
    with pytest.raises(ValueError):
        combat_step(state, {'action': 'tactic', 'proposal': {'multiplier': 99}}, 'hack')
    with pytest.raises(ValueError):
        validate_tactics({'choices': [{'label': '用撬棍撬开甲壳', 'intent': '使用撬棍攻击',
            'multiplier': 1.1, 'energy_cost': 8, 'effect': 'none'}]}, state)


def test_controller_uses_only_tactic_bound_to_current_node(tmp_path):
    from duhe.storage import Store
    from duhe.controller_v2 import ControllerV2
    store = Store(tmp_path / 'test.sqlite'); controller = ControllerV2(store)
    cid = store.create('owner', fight())
    node = store.node('owner', cid)
    choices = validate_tactics({'choices': [{'label': '攻击关节', 'intent': '切向腿部关节',
        'multiplier': 1.3, 'energy_cost': 10, 'effect': 'weaken'}]}, node['state'])
    store.set_tactics_v2('owner', cid, node['id'], choices)
    token = tactic_token(store.node('owner', cid), 0)
    result = controller.act('owner', cid, {'action': 'use_tactic', 'token': token}, 0, 'use')
    assert result['event']['player_intent'] == '切向腿部关节'
    with pytest.raises(ValueError):
        controller.act('owner', cid, {'action': 'use_tactic', 'token': token}, 1, 'reuse')
