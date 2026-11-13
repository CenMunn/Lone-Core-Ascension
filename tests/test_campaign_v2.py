import copy
import pytest
from duhe.campaign import next_story_beats, advance_tower_segment, purify_final_core, finish_epilogue
from duhe.models_v2 import migrate_state,BASE_STATS
from duhe.progression import START
from duhe.rules import new_game

def tower_ready():
    old=new_game(mode='demo',checkpoint='wall');s=migrate_state(old,story_turn=45,operation_seq=70)
    s['flags']['wall_saved']=True;s['tower_floor']=1;s['cleared_floors']=[]
    return s

def test_compresses_ordinary_floors_but_stops_at_guardian():
    state=tower_ready();before=copy.deepcopy(state)
    result,event=advance_tower_segment(state,'tower-segment')
    assert state==before and result['story_turn']==46 and result['countdown']==4954
    assert result['cleared_floors']==list(range(1,10)) and result['tower_floor']==10
    assert 'tower_10' in result['flags']['unlocked_bosses']
    assert result['inventory']==state['inventory'] and event['floors']==[1,9]
    with pytest.raises(ValueError,match='守卫'):advance_tower_segment(result,'again')

def test_tower_segment_cannot_skip_earlier_guardian():
    state=tower_ready();state['tower_floor']=11
    with pytest.raises(ValueError,match='守卫'):advance_tower_segment(state,'skip')

def test_ur_reveals_final_route_without_fabricating_completed_events():
    state=tower_ready();state['ability_rank']='UR';state['ability_xp']=START['UR']
    state['max_hp'],state['max_energy'],state['base_attack']=BASE_STATS['UR'];state['hp']=100;state['energy']=100
    before=copy.deepcopy(state);beats=next_story_beats(state)
    assert any(x['id']=='final_route' for x in beats)
    assert state==before and not state['flags'].get('boss_defeated')

def test_final_purification_and_wedding_follow_boss_defeat():
    state=tower_ready();state['ability_rank']='ULTRA';state['ability_xp']=START['UR']
    state['max_hp'],state['max_energy'],state['base_attack']=BASE_STATS['ULTRA']
    state['heroine_rank']='UR';state['flags'].update(boss_defeated=True,final_phase='purification')
    purified,event=purify_final_core(state,'purify-final')
    assert purified['flags']['civilization_saved'] and not purified['flags'].get('victory')
    assert purified['inventory']['purified_final_fragment']==1 and 'purified_final_seal' in purified['unlocked_recipes']
    assert purified['inventory']['clean_core']==state['inventory']['clean_core']-3
    ended,event=finish_epilogue(purified,'wedding')
    assert ended['flags']['victory'] and ended['flags']['final_phase']=='finished'
    assert {'heroine','friend'} <= set(event['present_character_ids'])
    assert 'wedding' in ended['relationships']['heroine']['events']

def test_finale_cannot_be_claimed_before_awakening_or_won_boss():
    state=tower_ready();before=copy.deepcopy(state)
    with pytest.raises(ValueError):purify_final_core(state,'early')
    assert state==before
