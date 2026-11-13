import copy
import pytest
from duhe.inventory import preview_resource_action, apply_resource_action
from duhe.models_v2 import migrate_state
from duhe.rules import new_game, apply_action

def state_with_cores():
    state,_=apply_action(new_game(),'opening');state['inventory']['raw_core']=10
    state['inventory']['clean_core']=10;state['energy']=100;state['pollution']=0
    return migrate_state(state,story_turn=1,operation_seq=1)

@pytest.mark.parametrize('action,key,message', [
    ('refine','raw_core','当前污染核心数量不足'),
    ('absorb_core','clean_core','当前净化核心数量不足'),
])
def test_insufficient_core_has_specific_message_and_does_not_change_state(action, key, message):
    state = state_with_cores(); state['inventory'][key] = 0
    state['core_grades' if key == 'raw_core' else 'clean_core_grades'] = {'ungraded': 0}
    before = copy.deepcopy(state)
    for operation in (lambda: preview_resource_action(state, {'action': action, 'quantity': 1}),
                      lambda: apply_resource_action(state, {'action': action, 'quantity': 1}, 'insufficient')):
        with pytest.raises(ValueError, match=message): operation()
        assert state == before

def test_core_energy_shortage_explains_required_and_available():
    state = state_with_cores(); state['energy'] = 3
    with pytest.raises(ValueError, match='核心能量不足：需要 8，当前 3'):
        preview_resource_action(state, {'action':'refine', 'quantity':1})

def test_bulk_refine_is_one_operation_no_story_turn_and_preview_matches():
    state=state_with_cores();before=copy.deepcopy(state)
    preview=preview_resource_action(state,{'action':'refine','quantity':5})
    result,event=apply_resource_action(state,{'action':'refine','quantity':5},'bulk-1')
    assert state==before and result['story_turn']==1 and result['operation_seq']==2
    assert result['inventory']['raw_core']==5 and result['inventory']['clean_core']==15
    assert result['energy']==60 and result['pollution']==15
    assert event['changes']==preview['changes']

def test_absorption_calculates_each_core_after_rank_upgrade():
    state=state_with_cores()
    result,event=apply_resource_action(state,{'action':'absorb_core','quantity':4},'bulk-2')
    assert result['ability_rank']=='E' and result['ability_xp']==90
    assert result['xp']==22 and result['max_hp']==180 and result['hp']==80
    assert result['max_energy']==120 and result['energy']==68 and result['pollution']==8
    assert result['inventory']['clean_core']==6 and event['changes']['ability_xp']==90

@pytest.mark.parametrize('action_request',[
    {'action':'refine','quantity':0},{'action':'refine','quantity':-1},
    {'action':'refine','quantity':True},{'action':'refine','quantity':11},
    {'action':'refine','quantity':2.5},
])
def test_invalid_bulk_is_atomic(action_request):
    state=state_with_cores();before=copy.deepcopy(state)
    with pytest.raises(ValueError):apply_resource_action(state,action_request,'bulk-bad')
    assert state==before

def test_pollution_boundary_and_duplicate_operation_are_atomic():
    state=state_with_cores();state['pollution']=94;before=copy.deepcopy(state)
    with pytest.raises(ValueError):apply_resource_action(state,{'action':'refine','quantity':2},'bad')
    assert state==before
    state['pollution']=0
    result,_=apply_resource_action(state,{'action':'refine','quantity':1},'once')
    with pytest.raises(ValueError):apply_resource_action(result,{'action':'refine','quantity':1},'once')

def test_core_quality_is_preserved_through_refining_and_low_grade_xp_decays():
    state=state_with_cores();state['core_grades']={'F-':2,'ungraded':8}
    refined,_=apply_resource_action(state,{'action':'refine','quantity':2,'grade':'F-'},'refine-f')
    assert refined['core_grades'].get('F-',0)==0 and refined['clean_core_grades']['F-']==2
    refined['ability_rank']='E';refined['ability_xp']=60
    result,event=apply_resource_action(refined,{'action':'absorb_core','quantity':2,'grade':'F-'},'absorb-f')
    assert 0<event['changes']['ability_xp']<60
    assert sum(result['clean_core_grades'].values())==result['inventory']['clean_core']

def test_missing_selected_quality_rejects_entire_batch():
    state=state_with_cores();before=copy.deepcopy(state)
    with pytest.raises(ValueError):apply_resource_action(state,{'action':'refine','quantity':2,'grade':'UR'},'bad')
    assert state==before
