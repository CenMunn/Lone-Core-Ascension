"""Non-story actions: every change is committed as its own branch-local operation."""
from copy import deepcopy
from uuid import uuid4
from math import ceil

from .catalog import ABILITIES, EQUIPMENT
from .combat import _known_skills
from .models_v2 import validate_state_v2
from .progression_v2 import growth_cost


def perform_ordinary(state, action, operation_id, *, target=None):
    validate_state_v2(state)
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError('操作编号无效')
    if operation_id in state['completed_operations']:
        raise ValueError('该操作已结算')
    if state.get('combat') or state['hp'] <= 0:
        raise ValueError('战斗中或失去行动能力时不能执行此操作')
    if not state.get('flags', {}).get('system_bound') and action in ('train', 'fuse', 'use_ability'):
        raise ValueError('尚未绑定系统')
    result = deepcopy(state)
    inv = result['inventory']
    if action == 'claim_legacy_boss_rewards':
        defeated=set(result.get('bestiary',{}).get('defeated_bosses',[]))
        recipes=result.setdefault('unlocked_recipes',[]); granted=[]
        for item in EQUIPMENT.values():
            if (item.get('special_effect') and item.get('boss_id') in defeated and item['id'] not in recipes
                    and (not item.get('unlock_after_purification') or result.get('flags',{}).get('civilization_saved'))):
                material=item['unlock_material'];inv[material]=inv.get(material,0)+1
                recipes.append(item['id']);granted.append(item['name'])
        if not granted:raise ValueError('当前没有可补领的首领奖励')
        summary='补领已击败首领的装备材料与配方：'+'、'.join(granted)
    elif action in ('rest', 'rest_full'):
        if result['hp']==result['max_hp'] and result['energy']==result['max_energy']:
            raise ValueError('生命和核心能量已满，无需休整')
        hp_recovery = max(1, round(result['max_hp'] * .35))
        energy_recovery = max(1, round(result['max_energy'] * .45))
        portions = (max(1, ceil((result['max_hp']-result['hp'])/hp_recovery),
                        ceil((result['max_energy']-result['energy'])/energy_recovery))
                    if action == 'rest_full' else 1)
        if inv.get('food', 0) < portions:
            raise ValueError(f'食物不足，连续休整需要{portions}份')
        inv['food'] -= portions
        result['hp'] = min(result['max_hp'], result['hp'] + hp_recovery * portions)
        result['energy'] = min(result['max_energy'], result['energy'] + energy_recovery * portions)
        result['day'] += portions
        result['recovery_days'] = result.get('recovery_days', 0) + portions
        summary = f'进食休整{portions}次，恢复生命和能量。'
    elif action == 'detox':
        if not result['pollution']:
            raise ValueError('当前没有污染')
        if inv.get('food', 0) < 2 or result['energy'] < 20:
            raise ValueError('排毒需要2份食物和20能量')
        inv['food'] -= 2
        result['energy'] -= 20
        result['pollution'] = max(0, result['pollution'] - 15)
        summary = '隔离排毒与呼吸恢复，污染降低15。'
    elif action == 'forage':
        if result.get('forage_story_turn') != result['story_turn']:
            result['forage_story_turn'] = result['story_turn']
            result['forage_count'] = 0
        if result['hp'] <= 4:
            raise ValueError('生命过低，无法安全拾荒')
        result['hp'] -= 4
        inv['food'] = inv.get('food', 0) + 3
        result['forage_count'] += 1
        summary = '在废墟拾荒，获得3份食物，损失4生命。'
    elif action == 'train':
        if inv.get('food', 0) < 1 or result['energy'] < 20:
            raise ValueError('训练需要1份食物和20能量')
        inv['food'] -= 1
        result['energy'] -= 20
        result['day'] += 1
        result['training_days'] += 1
        gain = max(1, round(growth_cost(result['realm_index'] * 3 + result['realm_stage']) * .08))
        result['xp'] += gain
        summary = f'完成训练与复盘，获得{gain}修炼经验。'
    elif action == 'fuse':
        echo = next((x for x in result.get('echoes', []) if x.get('id') == target), None)
        if not echo or target in result['consumed_echoes'] or not echo.get('compatible'):
            raise ValueError('残响不存在、已使用或无法融合')
        if any(x.get('enemy_id') == echo.get('enemy_id') and x.get('id') in result['consumed_echoes']
               for x in result.get('echoes', []) if x.get('id') != target):
            raise ValueError('该敌人的残响已选择融合其他能力')
        skill_id = echo.get('catalog_id')
        if skill_id not in ABILITIES:
            raise ValueError('能力不可用')
        known=next((x for x in result['skills'] if x.get('catalog_id',x.get('id'))==skill_id),None)
        if known and known.get('level',1)>=3:
            raise ValueError('该能力已达到最高等级')
        if known and ABILITIES[skill_id]['effect'] in ('passive','survival','control'):
            raise ValueError('该能力目前不能通过重复残响升级')
        if result['energy'] < 15 or result['pollution'] >= 65:
            raise ValueError('融合需要15能量且污染低于65')
        result['energy'] -= 15
        result['pollution'] += 8
        result['consumed_echoes'].append(target)
        if known:
            known['level']=known.get('level',1)+1
            summary = '融合重复残响，提升能力：' + ABILITIES[skill_id]['name'] + f"（{known['level']}级）"
        else:
            result['skills'].append({'id': skill_id, 'catalog_id': skill_id,
                                     'name': ABILITIES[skill_id]['name'], 'rank':ABILITIES[skill_id]['rank'], 'source': target, 'level':1})
            summary = '融合残响，获得能力：' + ABILITIES[skill_id]['name']
    elif action == 'use_ability':
        if target not in _known_skills(result) or target not in ABILITIES:
            raise ValueError('尚未掌握该能力')
        ability = ABILITIES[target]
        if not ability.get('outside_combat') or ability['effect'] not in ('heal', 'energy_heal'):
            raise ValueError('该能力不能在战外主动使用')
        if result['energy'] < ability['energy_cost']:
            raise ValueError('能量不足')
        if ability['effect'] == 'heal':
            if result['hp'] == result['max_hp']:
                raise ValueError('生命已经全满')
            result['energy'] -= ability['energy_cost']
            level=next((x.get('level',1) for x in result['skills'] if x.get('catalog_id',x.get('id'))==target),1)
            result['hp'] = min(result['max_hp'], result['hp'] + round(result['max_hp'] * (.35+.05*(level-1))))
            summary = '使用' + ability['name'] + '恢复生命。'
        else:
            cost = max(1, round(result['max_hp'] * .1))
            if result['hp'] <= cost:
                raise ValueError('生命不足以转换能量')
            if result['energy'] == result['max_energy']:
                raise ValueError('能量已经全满')
            result['hp'] -= cost
            level=next((x.get('level',1) for x in result['skills'] if x.get('catalog_id',x.get('id'))==target),1)
            result['energy'] = min(result['max_energy'], result['energy'] + max(1, round(result['max_energy'] * (.25+.05*(level-1)))))
            summary = '使用' + ability['name'] + '以生命恢复能量。'
    else:
        raise ValueError('不支持的普通行动')
    if action in ('rest', 'rest_full', 'train'):
        training = result.get('training_days', 0)
        recovery = result.get('recovery_days', 0)
        if training >= 30 and recovery >= 15:
            result['body_stage'] = 'hardened'
        elif training >= 12 and recovery >= 5:
            result['body_stage'] = 'trained'
        elif training >= 3 and recovery >= 1:
            result['body_stage'] = 'recovering'
    result['operation_seq'] += 1
    result['last_ordinary_action'] = action
    result['completed_operations'].append(operation_id)
    event = {'id': uuid4().hex, 'operation_id': operation_id, 'action_id': action,
             'target': target, 'story_turn': result['story_turn'], 'summary': summary}
    return validate_state_v2(result), event


def ordinary_options(state):
    """Keep actions visible; derive explanations from the same authoritative rules."""
    options=[]
    for action,label in (('rest','进食休整'),('rest_full','连续休整至恢复'),('train','训练与复盘'),('forage','废墟拾荒'),('detox','隔离排毒')):
        reason=''
        try:
            if not state.get('flags',{}).get('system_bound'):
                raise ValueError('请先完成初遇')
            perform_ordinary(state,action,'ui-preview-'+uuid4().hex)
        except ValueError as exc:
            reason=str(exc)
        options.append({'id':action,'label':label+(f'（暂不可用：{reason}）' if reason else ''),
                        'available':not bool(reason),'reason':reason})
    return options
