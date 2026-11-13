import copy
import pytest
from duhe.rules import new_game, apply_action
from duhe.models_v2 import migrate_state
from duhe.ordinary_v2 import perform_ordinary


def ready():
    old, _ = apply_action(new_game(), 'opening')
    return migrate_state(old, story_turn=1, operation_seq=1)


def test_rest_and_training_are_operations_not_story_turns():
    state = ready()
    state['hp'] = 1
    state['energy'] = 1
    rested, _ = perform_ordinary(state, 'rest', 'rest-1')
    assert rested['story_turn'] == state['story_turn']
    assert rested['hp'] == 1 + round(rested['max_hp'] * .35)
    assert rested['energy'] == 1 + round(rested['max_energy'] * .45)
    trained, _ = perform_ordinary(rested, 'train', 'train-1')
    assert trained['story_turn'] == state['story_turn']
    assert trained['xp'] > rested['xp']
    trained_again,_=perform_ordinary(trained,'train','train-2')
    assert trained_again['xp']>trained['xp'] and trained_again['story_turn']==trained['story_turn']
    with pytest.raises(ValueError,match='20能量'):
        perform_ordinary(trained_again,'train','train-3')


def test_echo_fusion_is_specific_and_atomic():
    state = ready()
    state['energy'] = 100
    state['echoes'] = [{'id': 'echo-one', 'catalog_id': 'rending_charge', 'compatible': True}]
    fused, _ = perform_ordinary(state, 'fuse', 'fuse-1', target='echo-one')
    assert any(x.get('catalog_id') == 'rending_charge' for x in fused['skills'])
    assert 'echo-one' in fused['consumed_echoes']
    before = copy.deepcopy(fused)
    with pytest.raises(ValueError):
        perform_ordinary(fused, 'fuse', 'fuse-2', target='echo-one')
    assert fused == before


def test_outside_heal_requires_owned_ability_and_spends_energy():
    state = ready()
    state['skills'].append({'id': 'life_return'})
    state['hp'] = 1
    state['energy'] = 100
    healed, _ = perform_ordinary(state, 'use_ability', 'heal', target='life_return')
    assert healed['hp'] > state['hp'] and healed['energy'] == 75
    assert healed['story_turn'] == state['story_turn']


def test_scavenging_can_repeat_while_health_is_sufficient():
    state = ready()
    for i in range(3):
        state, _ = perform_ordinary(state, 'forage', f'forage-{i}')
    assert state['story_turn'] == 1
    state,_=perform_ordinary(state,'forage','forage-3')
    assert state['forage_count']==4 and state['story_turn']==1
    state['hp']=4;before=copy.deepcopy(state)
    with pytest.raises(ValueError,match='生命过低'):
        perform_ordinary(state,'forage','low-health')
    assert state==before


def test_detox_recovers_from_core_pollution_without_a_clean_core():
    state = ready()
    state['pollution'] = 70
    state['energy'] = 100
    state['inventory']['food'] = 2
    cleaned, _ = perform_ordinary(state, 'detox', 'detox')
    assert cleaned['pollution'] == 55
    assert cleaned['energy'] == 80 and cleaned['inventory']['food'] == 0
    assert cleaned['story_turn'] == state['story_turn']


def test_physique_only_improves_with_training_and_recovery():
    state = ready()
    state['training_days'] = 11
    state['recovery_days'] = 5
    state['body_stage'] = 'recovering'
    state['energy'] = 100
    trained, _ = perform_ordinary(state, 'train', 'twelfth-day')
    assert trained['body_stage'] == 'trained'
    assert state['body_stage'] == 'recovering'


def test_rest_full_consumes_only_needed_food_without_story_advance():
    state = ready()
    state['hp'] = 1; state['energy'] = 1; state['inventory']['food'] = 3
    rested, _ = perform_ordinary(state, 'rest_full', 'rest-full')
    assert rested['hp'] == rested['max_hp'] and rested['energy'] == rested['max_energy']
    assert rested['inventory']['food'] == 0 and rested['story_turn'] == state['story_turn']
    state['inventory']['food'] = 2
    before = copy.deepcopy(state)
    with pytest.raises(ValueError, match='食物不足'):
        perform_ordinary(state, 'rest_full', 'not-enough')
    assert state == before


def test_energy_recovery_spends_health_and_cannot_be_used_at_lethal_hp():
    state = ready()
    state['skills'].append({'id': 'energy_reflow'})
    state['hp'] = state['max_hp']; state['energy'] = 0
    recovered, _ = perform_ordinary(state, 'use_ability', 'energy', target='energy_reflow')
    assert recovered['energy'] > 0 and recovered['hp'] < state['hp']
    assert recovered['story_turn'] == state['story_turn']
    recovered['hp'] = 1; recovered['energy'] = 0
    with pytest.raises(ValueError):
        perform_ordinary(recovered, 'use_ability', 'lethal', target='energy_reflow')
