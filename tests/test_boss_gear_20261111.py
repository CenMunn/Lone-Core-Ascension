import pytest
from duhe.catalog import EQUIPMENT, MONSTERS
from duhe.combat import combat_step, start_encounter
from duhe.equipment import craft_equipment, equip
from duhe.models_v2 import migrate_state
from duhe.rules import apply_action, new_game
from duhe.ordinary_v2 import perform_ordinary
from duhe.viewmodel_v2 import available_actions

def ready():
    state,_=apply_action(new_game(),'opening')
    state=migrate_state(state,story_turn=1,operation_seq=1)
    state['hp']=state['max_hp'];state['energy']=state['max_energy']
    return state

@pytest.mark.parametrize('item_id',['wall_blade','flame_gauntlet','corrosion_mask','thunder_blade','mirror_amulet','bone_greaves','void_boots']+[f'trial_{i}_seal' for i in range(10)])
def test_boss_awards_sufficient_material_to_unlock_and_craft(item_id):
    item=EQUIPMENT[item_id];state=ready();boss=item['boss_id']
    state['flags'].setdefault('unlocked_bosses',[]).append(boss)
    if MONSTERS[boss].get('floor'):state['tower_floor']=MONSTERS[boss]['floor']
    state['inventory']['material']=20
    state,_=start_encounter(state,boss,'start');state['combat']['hp']=1
    state,event=combat_step(state,{'action':'attack'},'win')
    assert event['outcome']=='victory' and state['inventory'][item['unlock_material']]==1
    assert item_id in state['unlocked_recipes']
    state,event=craft_equipment(state,item_id,'craft')
    state,_=equip(state,event['instance_id'],item['slot'],'equip')
    assert state['equipment_items'][state['equipment_slots'][item['slot']]]['item_id']==item_id

def test_mirror_guard_protects_next_exchange():
    state=ready();state['equipment_items']['mirror']={'instance_id':'mirror','item_id':'mirror_amulet'}
    state,_=equip(state,'mirror','accessory','equip')
    state,_=start_encounter(state,'rotted_hound','start')
    state,_=combat_step(state,{'action':'guard'},'guard')
    assert state['combat']['player_shield']==1
    before=state['hp'];state,_=combat_step(state,{'action':'attack'},'attack')
    assert before-state['hp'] < MONSTERS['rotted_hound']['attack']

def test_fire_boss_uses_and_drops_its_distinct_ability():
    state=ready();state['flags'].setdefault('unlocked_bosses',[]).append('tower_20');state['tower_floor']=20
    state,_=start_encounter(state,'tower_20','start')
    # Give the player enough health to observe the boss mechanic without changing its rules.
    state['max_hp']=100000;state['hp']=100000
    for n in range(3):state,event=combat_step(state,{'action':'guard'},f'guard-{n}')
    assert event['enemy_ability']=='scarlet_burn'
    assert any(x['type']=='burn' for x in state['combat']['player_effects'])
    state['combat']['hp']=1
    state,event=combat_step(state,{'action':'attack'},'win')
    assert event['outcome']=='victory'
    assert any(x['catalog_id']=='scarlet_burn' for x in state['echoes'])

def test_older_branch_can_claim_new_boss_reward_once():
    state=ready();state.setdefault('bestiary',{})['defeated_bosses']=['tower_20']
    assert 'claim_legacy_boss_rewards' in [a['id'] for a in available_actions(state)['ordinary']]
    claimed,_=perform_ordinary(state,'claim_legacy_boss_rewards','claim')
    assert claimed['inventory']['material_flame_gauntlet']==1 and 'flame_gauntlet' in claimed['unlocked_recipes']
    assert claimed['story_turn']==state['story_turn']
    with pytest.raises(ValueError, match='没有可补领'):
        perform_ordinary(claimed,'claim_legacy_boss_rewards','again')

def test_flame_gauntlet_changes_the_burn_damage():
    from duhe.combat import _gear_stat
    state=ready();state['equipment_items']['flame']={'instance_id':'flame','item_id':'flame_gauntlet'}
    state,_=equip(state,'flame','hands','equip')
    state['skills'].append({'id':'burning_core','name':'灼核弹','source':'test'})
    state,_=start_encounter(state,'polluted_beetle','start')
    attack=state['base_attack']+_gear_stat(state,'attack')
    state,_=combat_step(state,{'action':'skill','skill_id':'burning_core'},'burn')
    burn=next(x for x in state['combat']['effects'] if x['type']=='burn')
    assert burn['damage']==max(1,round(attack*.12*1.25))

def test_void_boots_reduce_first_direct_attack_only():
    from duhe.combat import _gear_stat
    state=ready();state['equipment_items']['void']={'instance_id':'void','item_id':'void_boots'}
    state,_=equip(state,'void','feet','equip');state,_=start_encounter(state,'rotted_hound','start')
    state['combat']['attack']=100;state['hp']=state['max_hp']=1000
    expected=max(1,100-_gear_stat(state,'defense'))
    state,first=combat_step(state,{'action':'attack'},'first')
    state,second=combat_step(state,{'action':'attack'},'second')
    assert first['damage_to_player']==max(1,round(expected*.5))
    assert second['damage_to_player']==expected
