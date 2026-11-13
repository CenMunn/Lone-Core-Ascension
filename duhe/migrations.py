"""Pure full-tree conversion; persistent import is intentionally separate."""
from copy import deepcopy
from uuid import uuid4
from .models_v2 import derive_story_turn, migrate_state

def migrate_campaign(bundle):
    if not isinstance(bundle,dict) or not isinstance(bundle.get('nodes'),list):
        raise ValueError('存档节点无效')
    source=bundle['nodes'];graph={}
    for node in source:
        nid=node.get('id')
        if not isinstance(nid,str) or nid in graph:raise ValueError('节点编号无效或重复')
        graph[nid]=node
    roots=[n for n in source if n.get('parent_id') is None]
    if len(roots)!=1 or bundle.get('campaign',{}).get('current_node') not in graph:
        raise ValueError('存档根节点或当前节点无效')
    clocks={roots[0]['id']:(0,0)}
    for start in graph:
        pending=[];seen=set();nid=start
        while nid not in clocks:
            if nid in seen or nid not in graph:raise ValueError('存档分支存在循环或缺失父节点')
            seen.add(nid);pending.append(nid);nid=graph[nid].get('parent_id')
        for child_id in reversed(pending):
            child=graph[child_id];parent=graph[child['parent_id']]
            turn,seq=clocks[parent['id']]
            clocks[child_id]=(derive_story_turn(turn,parent['state'],child.get('event',{})),seq+1)
    mapping={nid:uuid4().hex for nid in graph};result=deepcopy(bundle)
    result['campaign']['id']=uuid4().hex
    result['campaign']['current_node']=mapping[bundle['campaign']['current_node']]
    result['campaign']['revision']=0
    for node in result['nodes']:
        old_id=node['id'];turn,seq=clocks[old_id]
        node['state']=migrate_state(node['state'],story_turn=turn,operation_seq=seq)
        node['id']=mapping[old_id];node['parent_id']=mapping.get(node.get('parent_id'))
    for feedback in result.get('feedback',[]):
        if feedback.get('node_id') not in mapping:raise ValueError('反馈关联节点不存在')
        feedback['node_id']=mapping[feedback['node_id']]
        feedback['campaign_id']=result['campaign']['id'];feedback['id']=uuid4().hex
    return result,mapping
