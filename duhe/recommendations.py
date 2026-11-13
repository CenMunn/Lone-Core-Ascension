"""Model-written tactics are bound to a specific node and legal settlement."""
import json
import hashlib
import re
from .rules import actions_for,scene_for
from .content_guard import SECRET_RULE,assert_private,leaks_secret,normalize_text


def messages(node,locale):
    result=[{'role':'system','content':'''为互动小说生成2至3个适合此刻场景的具体行动建议，只输出JSON：{"choices":[{"action_id":"rest","label":"回到维修棚，处理裂开的肋伤","intent":"先包扎再休息"}]}。每项绑定一个允许行动ID，不能发明ID。结合正文中的地点、威胁、角色、伤势，建议不同目标或策略，不能只重复菜单标题。不得承诺额外奖励、越级、瞬杀、改变固定设定；不能替主角进入尚未解锁场所。意图只细化一个回合，不能串联多个结算。'''},
            {'role':'user','content':json.dumps({'locale':locale,'story':node['text'][-2200:],'scene':node.get('meta',{}).get('scene') or scene_for(node['state'],node['event']),'current_facts':{k:node['state'].get(k) for k in ('hp','max_hp','energy','pollution','inventory','equipment','wounds')},'constraint':'建议不得使用库存中不存在的道具或承诺额外交易、治疗与奖励；必须保持对应合法行动的代价和结果。','allowed':actions_for(node['state'])},ensure_ascii=False)}]
    result[0]['content']+='\n'+SECRET_RULE
    if locale=='en-US':
        result[0]['content']='OUTPUT LANGUAGE: ENGLISH. Every label and intent MUST be natural English, even if reference facts are Chinese. Use Lu Lingxiao, Shen Jiyue, Zhou Ye. Return only JSON.\n'+result[0]['content'].replace('回到维修棚，处理裂开的肋伤','Return to shelter to tend the wound').replace('先包扎再休息','Dress the wound and rest')
        result[-1]['content']+='\nFINAL INSTRUCTION: English labels and intents only. Keep exact allowed action_id values.'
    else:result[0]['content']+=' 使用中文label和intent。'
    return result


def validate(data,state,locale='zh-CN'):
    allowed={a['id'] for a in actions_for(state)};result=[];seen=set()
    items=data.get('choices',[]) if isinstance(data,dict) else []
    if not isinstance(items,list):raise ValueError('推荐选项格式错误')
    for item in items[:3]:
        if not isinstance(item,dict):continue
        action=item.get('action_id');label=item.get('label');intent=item.get('intent')
        if action not in allowed or action in seen or not isinstance(label,str) or not isinstance(intent,str):continue
        if not label.strip() or not intent.strip():continue
        if leaks_secret(label+' '+intent):continue
        try:label=normalize_text(label);intent=normalize_text(intent)
        except ValueError:continue
        if locale=='en-US' and (re.search(r'[\u4e00-\u9fff]',label+intent) or len(re.findall(r'[A-Za-z]+',label+' '+intent))<3):continue
        result.append({'action_id':action,'label':label[:100],'intent':intent[:400]});seen.add(action)
    if len(result)<min(2,len(allowed)):raise ValueError('模型没有返回足够的合法推荐，基础行动仍可使用。')
    return result


def choice_token(node,index):
    item=node.get('meta',{}).get('recommendations',[])[index]
    digest=hashlib.sha256(json.dumps(item,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:12]
    return f"ai:{node['id']}:{index}:{digest}"


def resolve(node,token):
    parts=token.split(':')
    if len(parts) not in (3,4) or parts[0]!='ai' or parts[1]!=node['id'] or not parts[2].isdigit():raise ValueError('推荐已过期，请刷新当前场景。')
    items=node['meta'].get('recommendations',[]);index=int(parts[2])
    if index>=len(items):raise ValueError('推荐不存在')
    if len(parts)==4 and choice_token(node,index)!=token:raise ValueError('推荐内容已更新，请刷新后重新选择或投票。')
    item=items[index]
    assert_private(item.get('label','')+' '+item.get('intent',''))
    normalize_text(item.get('label','')+' '+item.get('intent',''))
    if item['action_id'] not in {a['id'] for a in actions_for(node['state'])}:raise ValueError('推荐行动当前不可用')
    return item['action_id'],item['intent']
