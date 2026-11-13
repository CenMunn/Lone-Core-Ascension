import copy
import pytest
from duhe.combat import start_encounter, combat_step
from duhe.combat import auto_attack
from duhe.models_v2 import migrate_state
from duhe.models_v2 import BASE_STATS
from duhe.progression import START
from duhe.rules import new_game,apply_action

def ready():
    state,_=apply_action(new_game(),'opening')
    state=migrate_state(state,story_turn=1,operation_seq=1)
    state['hp']=state['max_hp'];state['energy']=state['max_energy']
    state['bestiary']={'seen':['polluted_beetle']}
    return state

def test_battle_counts_once_and_each_skill_is_player_selected():
    s=ready();s['skills'].append({'id':'rending_charge','name':'裂爪突进','source':'test'})
    started,event=start_encounter(s,'polluted_beetle','start',source='codex')
    assert started['story_turn']==2 and started['combat']['hp']==140
    attacked,hit=combat_step(started,{'action':'attack'},'attack')
    skilled,skill=combat_step(started,{'action':'skill','skill_id':'rending_charge'},'skill')
    assert attacked['story_turn']==skilled['story_turn']==2
    assert skilled['combat']['hp']<attacked['combat']['hp']
    assert skill['skill_id']=='rending_charge' and skilled['energy']==started['energy']-15
    assert any(effect['type']=='bleed' for effect in skilled['combat']['effects'])
    assert s['combat'] is None


def test_encounter_unlocks_corresponding_dungeon_on_current_branch():
    state = ready()
    started, _ = start_encounter(state, 'polluted_beetle', 'discover')
    assert 'ruins' in started['bestiary']['dungeons_seen']
    assert 'dungeons_seen' not in state['bestiary']

def test_victory_reward_once_and_defeated_boss_not_farmable():
    s=ready();started,_=start_encounter(s,'polluted_beetle','start',source='codex')
    started['combat']['hp']=1
    won,event=combat_step(started,{'action':'attack'},'win')
    assert won['combat'] is None and event['outcome']=='victory'
    assert won['inventory']['raw_core']==s['inventory']['raw_core']+2
    assert won['core_grades']['F-']==2
    with pytest.raises(ValueError):combat_step(won,{'action':'attack'},'win')
    with pytest.raises(ValueError):start_encounter(won,'tower_100','boss-retry',source='codex')

def test_unlearned_or_unaffordable_skill_does_not_consume_resources():
    started,_=start_encounter(ready(),'polluted_beetle','start',source='codex')
    before=copy.deepcopy(started)
    with pytest.raises(ValueError):combat_step(started,{'action':'skill','skill_id':'time_gap'},'bad')
    assert started==before
    started['energy']=0;before=copy.deepcopy(started)
    with pytest.raises(ValueError):combat_step(started,{'action':'skill','skill_id':'core_pulse'},'bad')
    assert started==before


def test_unseen_higher_rank_monster_cannot_be_selected_as_story_encounter():
    state = ready()
    with pytest.raises(ValueError, match='评级'):
        start_encounter(state, 'thunder_lizard', 'too-early')

def test_failed_or_retreat_battle_does_not_increment_clock_twice():
    started,_=start_encounter(ready(),'polluted_beetle','start',source='codex')
    retreated,event=combat_step(started,{'action':'retreat'},'escape')
    assert retreated['combat'] is None and retreated['story_turn']==2 and event['outcome']=='retreat'


def test_monster_uses_its_known_ability_and_reports_status():
    state = ready()
    started, _ = start_encounter(state, 'rotted_hound', 'start')
    started['combat']['hp'] = 1000
    first, _ = combat_step(started, {'action': 'guard'}, 'guard-1')
    second, _ = combat_step(first, {'action': 'guard'}, 'guard-2')
    third, event = combat_step(second, {'action': 'guard'}, 'guard-3')
    assert event['enemy_ability'] == 'corrosion_bite'
    assert any(x['type'] == 'poison' for x in third['combat']['player_effects'])
    assert third['story_turn'] == started['story_turn']


def test_auto_attack_is_bounded_and_keeps_one_story_turn():
    state = ready()
    started, _ = start_encounter(state, 'polluted_beetle', 'start')
    ended, event = auto_attack(started, 'auto', max_steps=3)
    assert 1 <= event['exchange_count'] <= 3
    assert ended['story_turn'] == started['story_turn']
    assert 'auto' in ended['completed_operations']
    assert started['combat']['exchange'] == 0
    with pytest.raises(ValueError):
        auto_attack(ended, 'auto')

def test_final_boss_requires_combat_awakening_before_defeat():
    state=ready();state['ability_rank']='UR';state['ability_xp']=START['UR']
    state['max_hp'],state['max_energy'],state['base_attack']=BASE_STATS['UR']
    state['hp']=state['max_hp'];state['energy']=state['max_energy']
    state['flags']['unlocked_bosses']=['tower_100'];state['tower_floor']=100
    state['cleared_floors']=list(range(1,100))
    state['heroine_rank']='UR'
    state['inventory']['clean_core']=3;state['clean_core_grades']={'ungraded':3}
    started,_=start_encounter(state,'tower_100','final-start')
    started['combat']['hp']=1
    hit,_=combat_step(started,{'action':'attack'},'first')
    assert hit['combat']['hp']==1 and hit['ability_rank']=='UR'
    with pytest.raises(ValueError):combat_step(hit,{'action':'awaken'},'early')
    hit,_=combat_step(hit,{'action':'guard'},'second')
    awakened,event=combat_step(hit,{'action':'awaken'},'awaken')
    assert awakened['ability_rank']=='ULTRA' and awakened['combat'] is not None
    assert not awakened['flags'].get('boss_defeated') and event['outcome']=='ongoing'
    won,event=combat_step(awakened,{'action':'attack'},'victory')
    assert event['outcome']=='victory' and won['flags']['boss_defeated']
    assert 100 in won['cleared_floors'] and won['flags']['final_phase']=='purification'


def test_final_boss_requires_purification_resources_before_entry():
    state=ready();state['ability_rank']='UR';state['ability_xp']=START['UR']
    state['flags']['unlocked_bosses']=['tower_100'];state['tower_floor']=100
    state['cleared_floors']=list(range(1,100));state['heroine_rank']='UR'
    state['inventory']['clean_core']=0;state['clean_core_grades']={'ungraded':0}
    with pytest.raises(ValueError,match='净核'):
        start_encounter(state,'tower_100','unprepared')


def test_retreat_after_final_awakening_can_retry_the_final_boss():
    state=ready();state['ability_rank']='UR';state['ability_xp']=START['UR']
    state['max_hp'],state['max_energy'],state['base_attack']=BASE_STATS['UR']
    state['hp']=state['max_hp'];state['energy']=state['max_energy'];state['heroine_rank']='UR'
    state['inventory']['clean_core']=3;state['clean_core_grades']={'ungraded':3}
    state['flags']['unlocked_bosses']=['tower_100'];state['tower_floor']=100
    state['cleared_floors']=list(range(1,100))
    state,_=start_encounter(state,'tower_100','first-start')
    state,_=combat_step(state,{'action':'guard'},'first-guard')
    state,_=combat_step(state,{'action':'guard'},'second-guard')
    state,_=combat_step(state,{'action':'awaken'},'awaken')
    escaped,event=combat_step(state,{'action':'retreat'},'retreat')
    assert escaped['ability_rank']=='UR' and escaped['hp']<=escaped['max_hp']
    assert '未稳定' in event['summary']
    retry,_=start_encounter(escaped,'tower_100','retry')
    assert retry['combat']['final_phase']=='suppression'
