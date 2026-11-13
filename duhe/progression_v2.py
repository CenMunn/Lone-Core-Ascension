"""Thirty-stage cultivation rules for the new state version."""
from copy import deepcopy
from uuid import uuid4
from .models_v2 import validate_state_v2,base_stats
from .equipment import equipment_stats,_consume

def growth_cost(step):
    if type(step) is not int or not 0<=step<30:raise ValueError('境界阶段无效')
    return 60+16*step+4*(step//3)**2

def start_realm_trial(state,operation_id):
    validate_state_v2(state)
    realm=state['realm_index']
    if state['realm_stage']!=2:raise ValueError('达到当前大境界后期才能进入试炼')
    if state.get('flags',{}).get('trials_v2',{}).get(str(realm)):
        raise ValueError('本大境界试炼已完成')
    temporary=deepcopy(state);monster_id=f'trial_realm_{realm}'
    unlocked=temporary.setdefault('flags',{}).setdefault('unlocked_bosses',[])
    if monster_id not in unlocked:unlocked.append(monster_id)
    from .combat import start_encounter
    return start_encounter(temporary,monster_id,operation_id,source='story')

def advance_stage(state,operation_id):
    validate_state_v2(state)
    if not isinstance(operation_id,str) or not operation_id.strip():raise ValueError('操作编号无效')
    if operation_id in state['completed_operations']:raise ValueError('该操作已结算')
    if state.get('combat') or state['hp']<=0:raise ValueError('当前不能突破境界')
    if not state.get('flags',{}).get('system_bound'):raise ValueError('尚未绑定系统')
    realm=state['realm_index'];stage=state['realm_stage'];step=realm*3+stage
    if step==29:raise ValueError('已达到最高境界阶段')
    cost=growth_cost(step)
    if state['xp']<cost:raise ValueError(f'修炼经验不足，需要{cost}')
    if stage==2 and not state.get('flags',{}).get('trials_v2',{}).get(str(realm)):
        raise ValueError('当前大境界的独行试炼尚未完成')
    result=deepcopy(state);_consume(result,'clean_core',1);result['xp']-=cost
    result['realm_index'],result['realm_stage']=divmod(step+1,3)
    result['base_attack']=base_stats(result['ability_rank'],result['realm_index'],result['realm_stage'])[2]
    stats=equipment_stats(result);result['max_hp']=stats['max_hp'];result['max_energy']=stats['max_energy']
    result['hp']=min(result['hp'],result['max_hp']);result['energy']=min(result['energy'],result['max_energy'])
    result['operation_seq']+=1;result['completed_operations'].append(operation_id)
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':'breakthrough',
           'story_turn':result['story_turn'],'xp_cost':cost,'clean_core_cost':1,
           'realm_index':result['realm_index'],'realm_stage':result['realm_stage']}
    return result,event
