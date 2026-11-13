import copy
import pytest
from duhe.controller_v2 import ControllerV2
from duhe.storage import Store
from duhe.rules import new_game,apply_action
from duhe.models_v2 import migrate_state
from duhe.story_flow import continue_narrative,reading_node
from duhe.viewmodel_v2 import available_actions,render_codex,render_equipment
from duhe.campaign import perform_milestone
from duhe.equipment import craftable_items,craft_equipment
from duhe.suggestions_v2 import legal_requests

def ready():
    old,_=apply_action(new_game(),'opening')
    return migrate_state(old,story_turn=1,operation_seq=1)

def test_continuation_always_available_without_growth_or_cores():
    state=ready();state['energy']=0;state['inventory']['food']=0
    before=copy.deepcopy(state)
    for n in range(4):
        assert 'continue_story' in [x['id'] for x in available_actions(state)['story']]
        state,event=continue_narrative(state,'continue_story',f'continue-{n}')
        assert event['continuation']
    for key in ('inventory','hp','energy','xp','ability_xp','ability_rank','equipment','skills','flags'):
        assert state[key]==before[key]
    assert state['story_turn']==5
    with pytest.raises(ValueError,match='剧情条件'):
        perform_milestone(state,'rival_refuse','locked')

def test_management_and_rewind_preserve_branch_story(tmp_path):
    store=Store(tmp_path/'save.sqlite');c=ControllerV2(store);cid=c.create('owner')
    first=c.act('owner',cid,{'action':'opening'},0,'opening')
    story=c.act('owner',cid,{'action':'story_investigate'},1,'investigate')
    c.act('owner',cid,{'action':'rest'},2,'rest')
    assert reading_node(store,'owner',cid)['id']==story['id']
    store.select('owner',cid,first['id'])
    rev=store.campaign('owner',cid)['revision']
    alternative=c.act('owner',cid,{'action':'story_converse'},rev,'talk')
    assert reading_node(store,'owner',cid)['id']==alternative['id']
    assert story['id'] not in [n['id'] for n in store.history('owner',cid)]

def test_equipment_codex_has_player_names_and_recipe_shortages():
    state=ready();html=render_codex(state)
    assert '部位：胸甲' in html and '防御力 +8' in html and '最大生命 +30' in html
    assert '通用材料 ×3' in html and '净化核心 ×2' in html and '还缺' in html
    assert "'defense'" not in html and "'max_hp'" not in html and '部位：chest' not in html
    assert "'defense'" not in render_equipment(state)

def test_unavailable_ordinary_actions_stay_visible_but_are_not_ai_suggestions():
    state=ready();state['inventory']['food']=0;state['energy']=0
    actions=available_actions(state)['ordinary']
    assert {'rest','rest_full','train','forage','detox'} <= {x['id'] for x in actions}
    train=next(x for x in actions if x['id']=='train')
    assert not train['available'] and '20能量' in train['reason']
    assert 'ordinary:train' not in legal_requests(state)

def test_crafting_list_requires_recipe_and_sufficient_materials():
    state=ready()
    assert 'black_iron_armor' not in {x['id'] for x in craftable_items(state)}
    state['inventory'].update(material=3,clean_core=2);state['clean_core_grades']={'ungraded':2}
    assert 'black_iron_armor' in {x['id'] for x in craftable_items(state)}
    crafted,_=craft_equipment(state,'black_iron_armor','craft')
    assert 'black_iron_armor' not in {x['id'] for x in craftable_items(crafted)}
    state['inventory'].update(material=99)
    assert 'flame_gauntlet' not in {x['id'] for x in craftable_items(state)}
