import pytest
from duhe.prompts import build_messages, character_card, validate_visual
from duhe.rules import new_game, apply_action, scene_for

def test_absorption_chinese_prompt_does_not_force_english():
    state,_=apply_action(new_game(),'opening')
    state['inventory']['clean_core']=1
    state,event=apply_action(state,'absorb_core')
    messages=build_messages(state,event,[],'zh-CN',scene_for(state,event))
    assert 'OUTPUT LANGUAGE FOR THIS TURN: ENGLISH' not in messages[0]['content']

def test_visual_cards_include_adult_age():
    state=new_game();scene=scene_for(state)
    assert '26岁' in character_card('protagonist',state,scene)
    assert '25岁' in character_card('heroine',state,scene)

def test_visual_rejects_names_missing_from_ids():
    scene={'present_character_ids':['protagonist','friend']}
    with pytest.raises(ValueError):
        validate_visual({'character_ids':['protagonist','friend'],'description':'沈霁月递上水'},scene)
