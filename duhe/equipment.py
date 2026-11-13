"""Draft v2 equipment operations with branch-local item instances."""
from copy import deepcopy
from uuid import uuid4
from .catalog import EQUIPMENT
from .models_v2 import base_stats,validate_state_v2
from .inventory import GRADES

SLOTS=('weapon','head','chest','hands','legs','feet','accessory')

def craftable_items(state):
    validate_state_v2(state)
    if state.get('combat') or state['hp']<=0:return []
    inventory=state['inventory'];recipes=set(state.get('unlocked_recipes',[]))
    return [item for item in EQUIPMENT.values() if item['recipe']
            and (not item.get('unlock_material') or item['id'] in recipes or inventory.get(item['unlock_material'],0)>0)
            and all(inventory.get(key,0)>=amount for key,amount in item['recipe'].items())]

def equipment_stats(state):
    validate_state_v2(state)
    base_hp,base_energy,base_attack=base_stats(state['ability_rank'],state['realm_index'],state['realm_stage'])
    stats={'max_hp':base_hp,'max_energy':base_energy,'attack':base_attack,'defense':0}
    slots=state.get('equipment_slots') or {};items=state.get('equipment_items') or {};seen=set()
    for slot,instance in slots.items():
        if slot not in SLOTS:raise ValueError('未知装备部位')
        if instance is None:continue
        if instance in seen or instance not in items:raise ValueError('装备实例无效')
        seen.add(instance);item=EQUIPMENT.get(items[instance].get('item_id'))
        if not item:continue  # Keep unknown legacy items without inventing stats.
        if item['slot']!=slot:raise ValueError('装备部位不匹配')
        for key,value in item['stats'].items():stats[key]=stats.get(key,0)+value
    return stats

def _check(state,operation_id):
    validate_state_v2(state)
    if state.get('combat') or state['hp']<=0:raise ValueError('当前不能调整装备')
    if not isinstance(operation_id,str) or not operation_id.strip():raise ValueError('操作编号无效')
    if operation_id in state['completed_operations']:raise ValueError('该操作已结算')

def _finish(state,operation_id,action,instance_id):
    state['operation_seq']+=1;state['completed_operations'].append(operation_id)
    return {'id':uuid4().hex,'operation_id':operation_id,'action_id':action,
            'instance_id':instance_id,'story_turn':state['story_turn']}

def _consume(state,key,amount):
    if type(amount) is not int or amount<0 or state['inventory'].get(key,0)<amount:
        raise ValueError('打造材料不足')
    if key in ('raw_core','clean_core'):
        grades=state['core_grades' if key=='raw_core' else 'clean_core_grades']
        left=amount
        for grade in ['ungraded',*GRADES]:
            used=min(left,grades.get(grade,0));grades[grade]=grades.get(grade,0)-used;left-=used
            if not left:break
        if left:raise ValueError('核心品质与库存不一致')
    state['inventory'][key]-=amount

def craft_equipment(state,item_id,operation_id):
    _check(state,operation_id);item=EQUIPMENT.get(item_id)
    if not item or not item['recipe']:raise ValueError('没有可用的打造配方')
    material=item.get('unlock_material')
    if material and item_id not in state.get('unlocked_recipes',[]) and state['inventory'].get(material,0)<1:
        raise ValueError('尚未获得该装备的制作方法')
    result=deepcopy(state)
    for key,amount in item['recipe'].items():_consume(result,key,amount)
    if material and item_id not in result.setdefault('unlocked_recipes',[]):result['unlocked_recipes'].append(item_id)
    instance=uuid4().hex
    result['equipment_items'][instance]={'instance_id':instance,'item_id':item_id}
    return result,_finish(result,operation_id,'craft_equipment',instance)

def equip(state,instance_id,slot,operation_id):
    _check(state,operation_id)
    item_instance=(state.get('equipment_items') or {}).get(instance_id)
    item=EQUIPMENT.get(item_instance.get('item_id')) if item_instance else None
    if slot not in SLOTS or not item or item['slot']!=slot:raise ValueError('装备与部位不匹配')
    if any(value==instance_id for value in state['equipment_slots'].values()):raise ValueError('该装备已经穿戴')
    result=deepcopy(state);result['equipment_slots'][slot]=instance_id
    if slot=='weapon':result['equipment']['weapon']=item['id']
    elif slot=='chest':result['equipment']['armor']=item['id']
    stats=equipment_stats(result)
    result['max_hp']=stats['max_hp'];result['max_energy']=stats['max_energy']
    result['hp']=min(result['hp'],result['max_hp']);result['energy']=min(result['energy'],result['max_energy'])
    return result,_finish(result,operation_id,'equip',instance_id)

def unequip(state,slot,operation_id):
    _check(state,operation_id)
    if slot not in SLOTS:raise ValueError('未知装备部位')
    instance=state['equipment_slots'].get(slot)
    if not instance:raise ValueError('该部位没有装备')
    result=deepcopy(state);result['equipment_slots'][slot]=None
    if slot=='weapon':result['equipment']['weapon']=None
    elif slot=='chest':result['equipment']['armor']=None
    stats=equipment_stats(result);result['max_hp']=stats['max_hp'];result['max_energy']=stats['max_energy']
    result['hp']=min(result['hp'],result['max_hp']);result['energy']=min(result['energy'],result['max_energy'])
    return result,_finish(result,operation_id,'unequip',instance)
