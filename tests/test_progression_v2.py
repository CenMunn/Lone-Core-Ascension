import copy
import pytest
from duhe.progression_v2 import growth_cost, advance_stage, start_realm_trial
from duhe.models_v2 import migrate_state
from duhe.rules import new_game,apply_action

def ready():
    old,_=apply_action(new_game(),'opening');old['inventory']['clean_core']=10
    return migrate_state(old,story_turn=1,operation_seq=1)

def test_stage_cost_increases_across_thirty_stages():
    costs=[growth_cost(i) for i in range(30)]
    assert costs[0]==60 and costs[-1]==848 and all(a<b for a,b in zip(costs,costs[1:]))

def test_small_stage_uses_experience_and_core_without_story_advance():
    s=ready();s['xp']=100;before=copy.deepcopy(s)
    result,event=advance_stage(s,'advance-1')
    assert s==before and result['realm_index']==0 and result['realm_stage']==1
    assert result['xp']==40 and result['inventory']['clean_core']==9
    assert result['story_turn']==1 and result['operation_seq']==2
    assert result['hp']==before['hp'] and result['max_hp']>before['max_hp']

def test_new_major_realm_requires_its_trial_and_never_spends_on_failure():
    s=ready();s['realm_stage']=2;s['xp']=500;before=copy.deepcopy(s)
    with pytest.raises(ValueError,match='试炼'):advance_stage(s,'no-trial')
    assert s==before
    s['flags']['trials_v2']={'0':True}
    result,event=advance_stage(s,'trial-complete')
    assert (result['realm_index'],result['realm_stage'])==(1,0)

def test_major_realm_trial_is_solo_once_and_enables_breakthrough():
    from duhe.combat import combat_step
    s=ready();s['realm_stage']=2;s['energy']=s['max_energy'];s['hp']=s['max_hp']
    battle,event=start_realm_trial(s,'trial-start')
    assert battle['combat']['monster_id']=='trial_realm_0' and battle['story_turn']==2
    battle['combat']['hp']=1
    won,event=combat_step(battle,{'action':'attack'},'trial-win')
    assert won['flags']['trials_v2']['0'] and won['combat'] is None
    assert won['xp']>=growth_cost(2)
    advanced,_=advance_stage(won,'advance-major')
    assert (advanced['realm_index'],advanced['realm_stage'])==(1,0)
    with pytest.raises(ValueError):start_realm_trial(won,'repeat')
