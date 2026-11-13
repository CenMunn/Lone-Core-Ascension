"""Node-bound model suggestions over legal non-combat actions."""
import hashlib
import json
from .content_guard import assert_private, normalize_text, SECRET_RULE
from .viewmodel_v2 import available_actions


def legal_requests(state):
    groups = available_actions(state); result = {}
    for group in ('story', 'ordinary', 'battle'):
        for item in groups[group]:
            if item.get('available') is False:
                continue
            if item['id'] == 'heroine_sss' and state['inventory'].get('clean_core', 0) < 5:
                continue
            if item['id'] == 'heroine_ur' and state['inventory'].get('clean_core', 0) < 8:
                continue
            if item['id'] == 'final_purify' and state['inventory'].get('clean_core', 0) < 3:
                continue
            if item['id'] == 'tower_100' and (state['ability_rank'] != 'UR' or state.get('heroine_rank') != 'UR'
                    or state['inventory'].get('clean_core', 0) < 3):
                continue
            key = group + ':' + item['id']
            if group == 'battle':
                request = ({'action': 'realm_trial'} if item['id'] == 'realm_trial'
                           else {'action': 'start_encounter', 'monster_id': item['id']})
            else:
                request = {'action': item['id']}
            result[key] = {'label': item['label'], 'request': request}
    return result


def validate(data, state):
    if state.get('combat'):
        raise ValueError('战斗中请使用战术推荐')
    legal = legal_requests(state)
    items = data.get('choices') if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError('推荐格式无效')
    result = []
    for item in items[:3]:
        if not isinstance(item, dict) or item.get('key') not in legal:
            continue
        label, intent = item.get('label'), item.get('intent')
        if not isinstance(label, str) or not isinstance(intent, str) or not label.strip() or not intent.strip():
            continue
        try:
            label = normalize_text(label)[:80]; intent = normalize_text(intent)[:300]
            assert_private(label + intent)
        except ValueError:
            continue
        if item['key'] in {x['key'] for x in result}:
            continue
        result.append({'key': item['key'], 'label': label, 'intent': intent,
                       'request': legal[item['key']]['request']})
    if not result:
        raise ValueError('没有可执行的情景推荐')
    return result


def token(node, index):
    item = node['meta']['suggestions_v2'][index]
    raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return f"suggest:{node['id']}:{index}:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def resolve(node, value):
    parts = str(value).split(':')
    if len(parts) != 4 or parts[0] != 'suggest' or parts[1] != node['id'] or not parts[2].isdigit():
        raise ValueError('情景推荐已过期')
    index = int(parts[2]); items = node.get('meta', {}).get('suggestions_v2', [])
    if index >= len(items) or token(node, index) != value:
        raise ValueError('情景推荐已更新')
    item = items[index]; legal = legal_requests(node['state'])
    if item['key'] not in legal or item['request'] != legal[item['key']]['request']:
        raise ValueError('推荐行动当前无法执行')
    assert_private(item['label'] + item['intent'])
    return dict(item['request']), item['intent']


def messages(node, language='zh-CN'):
    locale_rule = 'Write all labels and intents in English; keep the action keys unchanged.\n' if language == 'en-US' else ''
    return [{'role': 'system', 'content': locale_rule + '依据当前剧情提出2至3个不同的下一步建议。只返回JSON对象choices数组，每项包含key、label、intent；key必须从允许清单原样选择。每项只对应一个行动，不得附加规则以外的装备、奖励、治疗或剧情结果；人物不知晓主角系统。' + SECRET_RULE},
            {'role': 'user', 'content': json.dumps({'正文': node['text'][-1800:], '场景': node.get('meta', {}).get('scene'),
               '允许行动': legal_requests(node['state'])}, ensure_ascii=False)}]
