"""Continuous narrative between state-gated campaign milestones."""
from copy import deepcopy
from uuid import uuid4
from .models_v2 import validate_state_v2

CONTINUATIONS={
    'continue_story':('继续当前故事','承接上一段最后的动作和未解决的问题，推进一件局部事件，留下下一步线索。'),
    'story_investigate':('调查当前场景的线索','承接当前场景进行调查，获得有来由的观察与线索；不凭空结算物资、战果或关键主线。'),
    'story_converse':('与在场人物交流／整理思绪','与当前在场人物展开有意义的对话；独处时通过行动与思考整理已有线索，不凭空召来角色。'),
}

def continuation_actions(state):
    if not state.get('flags',{}).get('system_bound') or state.get('flags',{}).get('victory') or state['story_turn']>=5000:
        return []
    return [{'id':key,'label':value[0]} for key,value in CONTINUATIONS.items()]

def continue_narrative(state,action,operation_id):
    validate_state_v2(state)
    if not isinstance(operation_id,str) or not operation_id.strip() or operation_id in state['completed_operations']:
        raise ValueError('操作编号无效或已结算')
    if action not in {x['id'] for x in continuation_actions(state)}:
        raise ValueError('当前不能继续故事，请先完成初遇或检查是否已经结局。')
    result=deepcopy(state)
    result['story_turn']+=1;result['turn']=result['story_turn'];result['countdown']=5000-result['story_turn']
    result['operation_seq']+=1;result['completed_operations'].append(operation_id)
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':action,'story_turn':result['story_turn'],
           'summary':CONTINUATIONS[action][1], 'continuation':True,
           'constraints':'本次只有叙事推进；所有经验、等级、核心、伤势、战果与关键节点仍以当前状态为准。'}
    return validate_state_v2(result),event

def is_story_node(node):
    event=node.get('event') or {}
    return (event.get('continuation') or event.get('action_id') in {
        'opening','first_hunt_report','rival_refuse','rival_trade','help_couriers','secure_samples','reject_harvest',
        'heroine_sss','heroine_ur','wall_prepare','start_encounter','realm_trial','tower_segment','final_purify','epilogue'}
        or event.get('outcome') in ('victory','defeat'))

def reading_node(store,owner,cid):
    history=store.history(owner,cid)
    return next((n for n in reversed(history) if is_story_node(n)),history[-1])

def route_hint(state):
    from .combat import RANKS
    flags=state.get('flags',{});inv=state['inventory'];rank=state['ability_rank']
    if not flags.get('system_bound'):return '下一步：选择初遇，接受沈霁月救援。'
    if flags.get('victory'):return '故事已结束；可以回到旧节点探索另一条分支。'
    suffix='普通续写始终可用，不必先净化、打造或升级。'
    if state.get('combat'):
        return '关键节点等待当前战斗结算。可在“战斗交锋”出招；普通续写可观察战局，不会自动扣血或替你击败敌人。'
    if not state.get('combat_wins',0):goal='首次独行：在“准备战斗”中亲自击败一只魔物，解锁战果登记。'
    elif not flags.get('first_hunt_report'):goal='已完成首次击杀，可选择“回到要塞记录战果”。'
    elif not flags.get('rival_resolved'):goal=f'要塞交涉：需要异能D级，当前为{rank}。'
    elif not flags.get('courier_decision'):goal=f'运输线分支：需要异能B级，当前为{rank}。'
    elif not flags.get('heroine_sss'):goal=f'沈霁月研究：需要异能A级与5颗净化核心；当前{rank}级、净化核心{inv.get("clean_core",0)}颗。'
    elif not flags.get('harvest_rejected'):goal=f'议事厅抉择：需要异能S级，当前为{rank}。'
    elif not flags.get('wall_saved'):
        goal='北墙：选择“准备迎战”解锁首领，再到“准备战斗”挑战破城重甲兽。'
    elif flags.get('final_phase')=='purification':goal='终战已胜利，可选择“反向净化终焉母核”；需3颗净化核心。'
    elif flags.get('final_phase')=='epilogue_ready':goal='文明已经获救，可选择结局。'
    elif state.get('heroine_rank')!='UR' and rank in ('UR','ULTRA'):
        goal=f'终战研究：需要8颗净化核心，当前{inv.get("clean_core",0)}颗，选择支持沈霁月的UR研究。'
    elif state.get('tower_floor',0)%10==0 and state.get('tower_floor',0)>0:
        goal=f'通天塔第{state["tower_floor"]}层：到“准备战斗”挑战守卫；终战需UR、沈霁月UR及3颗净化核心。'
    else:goal='通天塔：可集中攻略普通楼层，再挑战每十层守卫；终战仍需完成相应成长与研究。'
    return f'**关键主线指引：** {goal}\n\n{suffix}'
