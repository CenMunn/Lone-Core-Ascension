"""Version-two state migration primitives; not yet connected to the live game."""
from copy import deepcopy
from .progression import migrate as migrate_growth

# Preliminary values from the approved design. Balance simulation is still required.
BASE_STATS={
    'UNRANKED':(100,100,20),'F-':(100,100,20),'E':(180,120,32),
    'D':(300,145,50),'C':(480,175,78),'B':(760,210,120),
    'A':(1200,250,185),'S':(1900,300,285),'SS':(3000,360,440),
    'SSS':(4700,430,680),'UR':(7400,520,1050),'ULTRA':(12000,700,1700),
}
STORY_ACTIONS={'opening','explore','trial','wall_defend','enter_floor','rival_refuse',
               'rival_trade','reject_harvest','heroine_sss','heroine_ur','final_purify'}

def base_stats(rank,realm_index,realm_stage):
    if rank not in BASE_STATS or not 0<=realm_index<10 or not 0<=realm_stage<3:
        raise ValueError('等级或境界无效')
    multiplier=1+.02*(realm_index*3+realm_stage)
    return tuple(round(value*multiplier) for value in BASE_STATS[rank])

def validate_state_v2(state):
    if not isinstance(state,dict) or state.get('schema')!=2 or state.get('rules_version')!=2:
        raise ValueError('需要新版状态')
    limits={'story_turn':(0,5000),'operation_seq':(0,1000000),'realm_index':(0,9),
            'realm_stage':(0,2),'hp':(0,10000000),'max_hp':(1,10000000),
            'energy':(0,10000000),'max_energy':(1,10000000),'base_attack':(0,10000000),
            'pollution':(0,100),'xp':(0,10000000),'ability_xp':(0,10000000),
            'cores_absorbed':(0,10000000),'countdown':(0,5000)}
    for key,(low,high) in limits.items():
        value=state.get(key)
        if type(value) is not int or not low<=value<=high:raise ValueError('状态字段无效：'+key)
    if state['hp']>state['max_hp'] or state['energy']>state['max_energy']:
        raise ValueError('生命或能量超过上限')
    if state['countdown']!=5000-state['story_turn']:raise ValueError('剧情倒计时不一致')
    if state.get('ability_rank') not in BASE_STATS:raise ValueError('异能等级无效')
    inventory=state.get('inventory')
    if not isinstance(inventory,dict) or any(type(v) is not int or v<0 for v in inventory.values()):
        raise ValueError('库存无效')
    allowed={'ungraded',*BASE_STATS.keys()}-{'UNRANKED'}
    for field,item in (('core_grades','raw_core'),('clean_core_grades','clean_core')):
        values=state.get(field)
        if (not isinstance(values,dict) or any(k not in allowed or type(v) is not int or v<0 for k,v in values.items())
                or sum(values.values())!=inventory.get(item,0)):
            raise ValueError('核心品质与库存数量不一致')
    operations=state.get('completed_operations')
    if (not isinstance(operations,list) or any(not isinstance(x,str) or not x for x in operations)
            or len(set(operations))!=len(operations)):
        raise ValueError('操作记录无效')
    if state.get('combat') is not None and not isinstance(state['combat'],dict):raise ValueError('战斗状态无效')
    slots=state.get('equipment_slots');items=state.get('equipment_items')
    expected={'weapon','head','chest','hands','legs','feet','accessory'}
    if not isinstance(slots,dict) or set(slots)!=expected or not isinstance(items,dict):
        raise ValueError('装备栏或装备实例无效')
    if any(not isinstance(k,str) or not isinstance(v,dict) or not isinstance(v.get('item_id'),str)
           or v.get('instance_id')!=k for k,v in items.items()):
        raise ValueError('装备实例无效')
    worn=[v for v in slots.values() if v is not None]
    if any(not isinstance(v,str) or v not in items for v in worn) or len(set(worn))!=len(worn):
        raise ValueError('装备实例重复或缺失')
    from .catalog import EQUIPMENT
    for slot,instance in slots.items():
        item=EQUIPMENT.get(items[instance]['item_id']) if instance is not None else None
        if item and item['slot']!=slot:raise ValueError('装备部位不匹配')
    if not isinstance(state.get('skills'),list) or any(not isinstance(x,dict) for x in state['skills']):
        raise ValueError('能力记录无效')
    for row in (state.get('relationships') or {}).values():
        if isinstance(row,dict) and 'affinity' in row and (type(row['affinity']) is not int or not -100<=row['affinity']<=100):
            raise ValueError('好感度数值无效')
    if 'affinity_recent' in state and (not isinstance(state['affinity_recent'],list) or any(
        not isinstance(x,dict) or type(x.get('turn')) is not int or not isinstance(x.get('fingerprint'),str)
        for x in state['affinity_recent'])):
        raise ValueError('好感度记录无效')
    return state

def derive_story_turn(previous_turn, previous_state, event):
    """Derive a history-local story clock without counting combat exchanges."""
    if not isinstance(previous_turn,int) or previous_turn<0:raise ValueError('剧情回合无效')
    action=event.get('action_id','')
    advances=action in STORY_ACTIONS and not previous_state.get('combat')
    return previous_turn+int(advances)

def migrate_state(old, *, story_turn, operation_seq):
    """Convert a copy of a schema-1 snapshot; the old snapshot is untouched."""
    if old.get('schema')!=1:raise ValueError('只支持从旧版状态迁移')
    if type(story_turn) is not int or type(operation_seq) is not int or min(story_turn,operation_seq)<0 or story_turn>5000:
        raise ValueError('迁移计数无效')
    rank=old.get('ability_rank')
    if rank not in BASE_STATS:raise ValueError('未知异能等级')
    old_max_hp=old['max_hp'];old_max_energy=old.get('max_energy',100)
    if old_max_hp<=0 or old_max_energy<=0:raise ValueError('旧状态上限无效')
    result=migrate_growth(deepcopy(old))
    old_stage=result['realm_stage'];result['realm_stage']=min(old_stage,2)
    base_hp,base_energy,base_attack=base_stats(rank,result['realm_index'],result['realm_stage'])
    from .catalog import EQUIPMENT
    slots={key:None for key in ('weapon','head','chest','hands','legs','feet','accessory')}
    items={}
    for legacy_slot,new_slot in (('weapon','weapon'),('armor','chest')):
        item_id=result.get('equipment',{}).get(legacy_slot)
        if item_id:
            instance='legacy:'+new_slot+':'+str(item_id)
            items[instance]={'instance_id':instance,'item_id':item_id}
            slots[new_slot]=instance
    result['equipment_slots']=slots;result['equipment_items']=items
    gear=[EQUIPMENT.get(v['item_id'],{}).get('stats',{}) for v in items.values()]
    result['max_hp']=base_hp+sum(v.get('max_hp',0) for v in gear)
    result['max_energy']=base_energy+sum(v.get('max_energy',0) for v in gear)
    result['base_attack']=base_attack
    result['hp']=min(result['max_hp'],max(0,round(old['hp']*result['max_hp']/old_max_hp)))
    result['energy']=min(result['max_energy'],max(0,round(old['energy']*result['max_energy']/old_max_energy)))
    result['legacy_turn']=old['turn'];result['legacy_realm_stage']=old_stage
    result['legacy_countdown']=old['countdown'];result['countdown']=5000-story_turn
    result['legacy_battle_requires_old_rules']=bool(old.get('combat'))
    completed_trials={str(realm):True for realm in range(10)
                      if old.get('flags',{}).get(f'trial_{realm*4+3}')}
    if completed_trials:result['flags']['trials_v2']=completed_trials
    result['core_grades']={'ungraded':result['inventory'].get('raw_core',0)}
    result['clean_core_grades']={'ungraded':result['inventory'].get('clean_core',0)}
    result['story_turn']=story_turn;result['operation_seq']=operation_seq
    result['schema']=2;result['rules_version']=2
    return validate_state_v2(result)
