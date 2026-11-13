"""A modest, branch-local preference for meaningful contact with the main cast."""
import hashlib

THREADS={
    'heroine':'沈霁月的污染研究、样本线索、撤离安排与克制的相互关心；她有自己的研究进度。',
    'friend':'周野的运输路线、补给委托与废墟见闻；他讲义气，也有自己的任务和难处。',
    'mentor':'顾砺山的维修委托、锻造经验和对独行训练的提醒，不凭空赠送装备或奖励。',
    'commander':'闻峥的要塞防线、平民撤离与可靠情报，不替主角完成独行战斗。',
    'rival':'裴景珩的资源竞争、财阀压力与表面礼貌，不提前完成尚未触发的契约抉择。',
    'antagonist':'已揭露的谢玄策研究方案、证据争议与文明存续的代价，不提前完成终焉关键节点。',
}

def choose_focus(state,event,history,scene):
    if event.get('action_id') not in ('continue_story','story_investigate','story_converse') or state.get('combat'):
        return None
    chapter=state.get('chapter',1)
    weights={'heroine':4,'friend':3}
    if chapter>=2:weights['mentor']=2
    if chapter>=3:weights.update(commander=2,rival=1)
    if chapter>=5:weights['commander']=3
    if state.get('flags',{}).get('harvest_rejected'):weights['antagonist']=1
    recent=[n.get('meta',{}).get('scene',{}).get('present_character_ids',[]) for n in history[-3:]]
    for cid in weights:
        if len(recent)>=3 and all(cid in cast for cast in recent):weights[cid]*=.2
    raw=hashlib.sha256(str(event.get('id','')).encode()).digest()
    roll=int.from_bytes(raw[:4],'big')/2**32
    # Two scenes alone make a meaningful contact more likely, rather than enforcing a fixed rotation.
    alone=len(recent)>=2 and all(not(set(cast)&set(THREADS)) for cast in recent[-2:])
    if roll >= (.75 if alone else .5):return None
    pick=int.from_bytes(raw[4:8],'big')/2**32*sum(weights.values())
    chosen=next(iter(weights))
    for cid,weight in weights.items():
        pick-=weight
        if pick<0:chosen=cid;break
    remote=chapter in (4,6) or '地下城' in scene.get('location','') or '通天塔' in scene.get('location','')
    return {'character_id':chosen,'thread':THREADS[chosen],
            'contact':'通信、留言或与其有关的线索；保持主角独行' if remote else '优先与已在场人物有实质交流；若不在场，可有来由地相遇、通信或追踪其线索',
            'guidance':'让人物带动当前矛盾或线索，承接上段动作并交代联系的缘由；不要突然插入寒暄、重复救援或强行转场。每段聚焦一至两位重要配角，感情只作暗线。人物可以拒绝、忙于自己的任务；不赠送未结算资源，不跳过关键节点，也不让伙伴替主角刷怪。'}
