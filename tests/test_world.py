import pytest
from duhe.world import CHARACTERS, scene_for, appearance_for


def test_character_cards_have_independent_goals_and_limits():
    assert len(CHARACTERS) >= 8
    for card in CHARACTERS.values():
        for field in ('name', 'appearance', 'outfit', 'personality', 'goal', 'limits'):
            assert isinstance(card[field], str) and card[field]


@pytest.mark.parametrize('combat,core,expected', [(False,False,False),(False,True,False),(True,False,False),(True,True,True)])
def test_blue_glow_requires_both_recorded_flags(combat, core, expected):
    state = {'body_stage':'underfed', 'equipment':{}, 'chapter':1, 'system_bound':True}
    scene = {'combat_active':combat,'core_power_active':core}
    assert appearance_for('protagonist', state, scene)['eye_glow'] is expected


def test_tower_has_no_unearned_companions():
    state = {'chapter':6,'tower_floor':10,'body_stage':'trained','flags':{},'system_bound':True}
    scene = scene_for(state)
    assert scene['present_character_ids'] == ['protagonist']
    assert scene['romance_budget'] == 0


def test_latest_heroine_and_final_boss_canon():
    assert '至腰' in CHARACTERS['heroine']['appearance']
    assert '温柔敏感' in CHARACTERS['heroine']['personality']
    assert '非人类' in CHARACTERS['boss']['appearance']


def test_actual_event_controls_romance_and_hair():
    from duhe.rules import new_game,apply_action
    s=new_game(mode='demo',checkpoint='wall')
    s,event=apply_action(s,'heroine_sss')
    scene=scene_for(s,event)
    assert scene['romance_budget']==1 and 'heroine' in scene['present_character_ids']
    s,event=apply_action(s,'scan')
    assert scene_for(s,event)['romance_budget']==0
