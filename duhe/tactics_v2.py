"""Validate model-proposed tactical outcomes and bind them to a story node."""
import hashlib
import json
import math
from .content_guard import assert_private, normalize_text


def validate_proposal(item):
    if not isinstance(item, dict):
        raise ValueError('战术格式无效')
    multiplier, cost, effect = item.get('multiplier'), item.get('energy_cost'), item.get('effect')
    if type(multiplier) not in (int, float) or not math.isfinite(multiplier) or not .8 <= multiplier <= 1.4:
        raise ValueError('战术威力超出范围')
    if type(cost) is not int or not 4 <= cost <= 20 or effect not in ('none', 'weaken'):
        raise ValueError('战术消耗或效果无效')
    if multiplier > 1.2 and cost < 10:
        raise ValueError('高威力战术需要至少10能量')
    if effect == 'weaken' and cost < 8:
        raise ValueError('削弱效果需要至少8能量')
    label, intent = item.get('label'), item.get('intent')
    if not isinstance(label, str) or not isinstance(intent, str) or not label.strip() or not intent.strip():
        raise ValueError('战术缺少名称或做法')
    label, intent = normalize_text(label)[:80], normalize_text(intent)[:300]
    assert_private(label + intent)
    return {'label': label, 'intent': intent, 'multiplier': float(multiplier),
            'energy_cost': cost, 'effect': effect}


def validate_tactics(data, state):
    if not state.get('combat'):
        raise ValueError('只有战斗中可以推荐战术')
    items = data.get('choices') if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError('战术推荐格式无效')
    result = []
    from .catalog import EQUIPMENT
    from .i18n_v2 import GEAR_EN
    worn = [state.get('equipment_items', {}).get(instance, {}).get('item_id')
            for instance in state.get('equipment_slots', {}).values() if instance]
    gear_names = {EQUIPMENT[item]['name'] for item in worn if item in EQUIPMENT}
    gear_names.update(GEAR_EN.get(item, '').lower() for item in worn)
    forbidden = ('撬棍', '手雷', '炸弹', '枪械', '手枪', '步枪', '长剑', '弓箭', '火箭筒', '药剂', '治疗药水',
                 'crowbar', 'grenade', 'bomb', 'pistol', 'rifle', 'sword', 'crossbow', 'potion')
    for item in items[:3]:
        try:
            proposal = validate_proposal(item)
        except ValueError:
            continue
        text = (proposal['label'] + proposal['intent']).lower()
        if any(tool in text and not any(tool in name.lower() for name in gear_names) for tool in forbidden):
            continue
        if proposal['energy_cost'] <= state['energy'] and proposal['label'] not in {x['label'] for x in result}:
            result.append(proposal)
    if not result:
        raise ValueError('没有符合条件的战术推荐')
    return result


def tactic_token(node, index):
    item = node['meta']['tactics_v2'][index]
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return f"tactic:{node['id']}:{index}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def resolve_tactic(node, token):
    parts = str(token).split(':')
    if len(parts) != 4 or parts[0] != 'tactic' or parts[1] != node['id'] or not parts[2].isdigit():
        raise ValueError('推荐已过期，请重新生成')
    index = int(parts[2]); items = node.get('meta', {}).get('tactics_v2', [])
    if index >= len(items) or tactic_token(node, index) != token:
        raise ValueError('推荐内容已变更，请重新选择')
    return validate_proposal(items[index])


def messages(node, language='zh-CN'):
    combat = node['state']['combat']
    from .content_guard import SECRET_RULE
    locale_rule = 'Write all labels and intents in English; keep JSON keys and effect values unchanged.\n' if language == 'en-US' else ''
    return [{'role': 'system', 'content': locale_rule + '为陆凌霄的当前战斗提出2至3项不同做法。只返回JSON对象choices数组，每项含label、intent、multiplier、energy_cost、effect。multiplier必须在0.8至1.4之间，energy_cost为4至20整数，高于1.2至少消耗10；effect只能是none或weaken，weaken至少消耗8。不得创造装备、奖励、其他能力或跳过战斗。只可使用当前穿戴的装备，严禁假设地面有可使用的武器、炸药或工具；不确定时描述徒手、移动或利用确定存在的地形。' + SECRET_RULE},
            {'role': 'user', 'content': json.dumps({'正文': node['text'][-1600:], '场景': node.get('meta', {}).get('scene'),
               '敌人': combat, '攻击力': node['state']['base_attack'], '能量': node['state']['energy'],
               '当前装备实例': node['state'].get('equipment_items'), '穿戴部位': node['state'].get('equipment_slots')}, ensure_ascii=False)}]
