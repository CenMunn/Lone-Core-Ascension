"""Atomic resource operations for draft version-two states."""
from copy import deepcopy
from uuid import uuid4
from .models_v2 import base_stats, validate_state_v2
from .progression import info as growth_info, rank_for

GRADES=['F-','E','D','C','B','A','S','SS','SSS','UR','ULTRA']

def _simulate(state, request):
    validate_state_v2(state)
    if not isinstance(request,dict):raise ValueError('行动格式无效')
    action=request.get('action');quantity=request.get('quantity')
    if action not in ('refine','absorb_core'):raise ValueError('不支持的核心操作')
    if type(quantity) is not int or quantity<=0:raise ValueError('数量必须是正整数')
    if state.get('combat') or state.get('hp',0)<=0 or not state.get('flags',{}).get('system_bound'):
        raise ValueError('当前状态不能进行该核心操作')
    source='raw_core' if action=='refine' else 'clean_core'
    if quantity>state['inventory'].get(source,0):
        raise ValueError('当前污染核心数量不足' if action=='refine' else '当前净化核心数量不足')
    if quantity*8>state['energy']:
        raise ValueError(f'核心能量不足：需要 {quantity*8}，当前 {state["energy"]}')
    result=deepcopy(state)
    for key,inventory_key in (('core_grades','raw_core'),('clean_core_grades','clean_core')):
        grades=result.setdefault(key,{'ungraded':result['inventory'].get(inventory_key,0)})
        if (not isinstance(grades,dict) or any(k not in ['ungraded',*GRADES] or type(v) is not int or v<0 for k,v in grades.items())
                or sum(grades.values())!=result['inventory'].get(inventory_key,0)):
            raise ValueError('核心品质与库存数量不一致')
    grade=request.get('grade')
    selected=result['core_grades' if action=='refine' else 'clean_core_grades']
    if grade is not None and (grade not in ['ungraded',*GRADES] or selected.get(grade,0)<quantity):
        raise ValueError('所选品质的核心数量不足')
    for _ in range(quantity):
        grade_now=grade or next((g for g in ['ungraded',*GRADES] if selected.get(g,0)>0),None)
        if grade_now is None:raise ValueError('核心数量不足')
        if action=='refine':
            if result['pollution']>=95:raise ValueError('污染过高，无法继续净化')
            increase=2 if any(x.get('id')=='furnace_control' for x in result.get('abilities',[])) else 3
            result['inventory']['raw_core']-=1;result['inventory']['clean_core']+=1
            result['core_grades'][grade_now]-=1
            clean=result['clean_core_grades'];clean[grade_now]=clean.get(grade_now,0)+1
            result['pollution']=min(100,result['pollution']+increase)
        else:
            if result['pollution']>=65:raise ValueError('污染过高，无法继续吸收')
            gains=growth_info(result);previous_rank=result['ability_rank']
            result['inventory']['clean_core']-=1;result['pollution']+=2
            result['clean_core_grades'][grade_now]-=1
            rank='F-' if previous_rank=='UNRANKED' else previous_rank
            diff=max(0,GRADES.index(rank)-GRADES.index(grade_now)) if grade_now!='ungraded' else 0
            result['ability_xp']+=max(1,round(gains['core_xp']*(.45**diff)))
            result['xp']+=max(1,round(gains['cultivation_xp']*(.45**diff)))
            result['cores_absorbed']+=1
            if previous_rank!='ULTRA':result['ability_rank']=rank_for(result['ability_xp'])
            new_rank=result['ability_rank']
            if new_rank!=previous_rank:
                old_stats=base_stats(previous_rank,result['realm_index'],result['realm_stage'])
                new_stats=base_stats(new_rank,result['realm_index'],result['realm_stage'])
                result['max_hp']+=new_stats[0]-old_stats[0]
                result['max_energy']+=new_stats[1]-old_stats[1]
                result['base_attack']+=new_stats[2]-old_stats[2]
        result['energy']-=8
    changes={key:result[key]-state[key] for key in ('hp','max_hp','energy','max_energy','pollution','xp','ability_xp')}
    changes.update({key:result['inventory'][key]-state['inventory'][key] for key in ('raw_core','clean_core')})
    return result,{key:value for key,value in changes.items() if value}

def preview_resource_action(state,request):
    result,changes=_simulate(state,request)
    return {'changes':changes,'ability_rank':result['ability_rank'],'quantity':request['quantity']}

def apply_resource_action(state,request,operation_id):
    if not isinstance(operation_id,str) or not operation_id.strip():raise ValueError('操作编号无效')
    if operation_id in state.get('completed_operations',[]):raise ValueError('该操作已结算')
    result,changes=_simulate(state,request)
    result['operation_seq']+=1;result['completed_operations'].append(operation_id)
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':request['action'],
           'quantity':request['quantity'],'story_turn':result['story_turn'],'changes':changes}
    return result,event
