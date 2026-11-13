import pytest
from duhe.combat import start_encounter, combat_step
from duhe.equipment import craft_equipment, equip, equipment_stats
from duhe.ordinary_v2 import perform_ordinary
from duhe.models_v2 import migrate_state
from duhe.rules import new_game, apply_action

def ready():
    state, _ = apply_action(new_game(), 'opening')
    state = migrate_state(state, story_turn=1, operation_seq=1)
    state['hp'] = state['max_hp']; state['energy'] = state['max_energy']
    return state

def win(state, enemy):
    state.setdefault('bestiary', {}).setdefault('seen', []).append(enemy)
    state, _ = start_encounter(state, enemy, 'fight-'+enemy, source='codex')
    state['combat']['hp'] = 1
    return combat_step(state, {'action':'attack'}, 'win-'+enemy)[0]

def test_elite_victory_unlocks_and_crafts_stat_only_equipment():
    before=ready(); won=win(before,'elite_iron_beetle')
    assert won['inventory']['elite_iron_shell']==1 and 'iron_basic_weapon' in won['unlocked_recipes']
    assert 'elite_iron_shell' not in before['inventory']
    crafted,event=craft_equipment(won,'iron_basic_weapon','craft')
    dressed,_=equip(crafted,event['instance_id'],'weapon','equip')
    assert equipment_stats(dressed)['attack'] > equipment_stats(won)['attack']
    assert dressed['inventory']['elite_iron_shell']==0

def test_multiple_echoes_allow_only_one_choice_per_enemy():
    state=win(ready(),'core_eater')
    echoes=state['echoes']; assert len(echoes)==2
    first,_=perform_ordinary(state,'fuse','fuse-one',target=echoes[0]['id'])
    with pytest.raises(ValueError,match='已选择融合其他能力'):
        perform_ordinary(first,'fuse','fuse-two',target=echoes[1]['id'])

def test_duplicate_echo_improves_the_ability_and_actual_damage():
    state=ready()
    for n in range(2):
        state,_=start_encounter(state,'rotted_hound',f'start-{n}')
        state['combat']['hp']=1
        state,_=combat_step(state,{'action':'attack'},f'win-{n}')
        echo=state['echoes'][-1]['id']
        state,_=perform_ordinary(state,'fuse',f'fuse-{n}',target=echo)
    skill=next(x for x in state['skills'] if x.get('id')=='corrosion_bite')
    assert skill['level']==2
    state,_=start_encounter(state,'polluted_beetle','start-target')
    state['energy']=state['max_energy']
    _,event=combat_step(state,{'action':'skill','skill_id':'corrosion_bite'},'skill-hit')
    from duhe.combat import _gear_stat
    assert event['damage_to_enemy']==round((state['base_attack']+_gear_stat(state,'attack'))*1.1)
