"""Draft v2 story milestones and compressed ordinary tower floors."""
from copy import deepcopy
from uuid import uuid4
from .combat import RANKS
from .models_v2 import validate_state_v2
from .equipment import _consume


def available_milestones(state):
    """Expose only story beats whose actual prerequisites have been met."""
    validate_state_v2(state)
    if state.get('combat') or not state.get('flags', {}).get('system_bound'):
        return []
    flags = state['flags']
    rank = state['ability_rank'] if state['ability_rank'] != 'UNRANKED' else 'F-'
    level = RANKS.index(rank)
    beats = []
    if state.get('combat_wins', 0) and not flags.get('first_hunt_report'):
        beats.append({'id': 'first_hunt_report', 'label': '首次独行：回到要塞记录战果'})
    if level >= RANKS.index('D') and not flags.get('rival_resolved'):
        beats.append({'id': 'rival_refuse', 'label': '要塞交涉：拒绝苛刻契约'})
        if state['inventory'].get('material', 0) >= 4:
            beats.append({'id': 'rival_trade', 'label': '要塞交涉：有限交易（4材料换6食物）'})
    if flags.get('rival_resolved') and level >= RANKS.index('B') and not flags.get('courier_decision'):
        beats.extend([{'id': 'help_couriers', 'label': '支援周野的运输线'},
                      {'id': 'secure_samples', 'label': '优先保全污染样本'}])
    if flags.get('rival_resolved') and level >= RANKS.index('S') and not flags.get('harvest_rejected'):
        beats.append({'id': 'reject_harvest', 'label': '议事厅：拒绝牺牲平民的方案'})
    if (flags.get('rival_resolved') and level >= RANKS.index('A')
            and state['heroine_rank'] == 'SS'):
        beats.append({'id': 'heroine_sss', 'label': '协助沈霁月的核心研究（5净核）'})
    if (flags.get('heroine_sss') and level >= RANKS.index('S')
            and not flags.get('wall_saved') and 'wall_boss' not in flags.get('unlocked_bosses', [])):
        beats.append({'id': 'wall_prepare', 'label': '北墙危机：准备迎战母巢'})
    if (flags.get('wall_saved') and state['heroine_rank'] == 'SSS'
            and level >= RANKS.index('UR')):
        beats.append({'id': 'heroine_ur', 'label': '支持沈霁月完成UR研究（8净核）'})
    return beats


def perform_milestone(state, milestone, operation_id):
    validate_state_v2(state)
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise ValueError('操作编号无效')
    if operation_id in state['completed_operations']:
        raise ValueError('该操作已结算')
    if state['story_turn'] >= 5000 or state['hp'] <= 0:
        raise ValueError('当前无法推进剧情')
    if milestone not in {x['id'] for x in available_milestones(state)}:
        raise ValueError('当前尚未满足剧情条件')
    result = deepcopy(state)
    flags = result['flags']
    if milestone == 'first_hunt_report':
        flags['first_hunt_report'] = True
        result['chapter'] = max(result['chapter'], 2)
        summary = '完成首次独行后，我将实际战果登记在猎人公会，隐去系统的存在。'
        cast = ['protagonist']
    elif milestone in ('rival_refuse', 'rival_trade'):
        flags['rival_resolved'] = True
        flags['rival_decision'] = milestone
        result['chapter'] = max(result['chapter'], 3)
        if milestone == 'rival_trade':
            _consume(result, 'material', 4)
            result['inventory']['food'] = result['inventory'].get('food', 0) + 6
            summary = '我与裴景珩进行一次有限交易，没有签署独家契约。'
        else:
            summary = '裴景珩提出独家契约，我拒绝交出自己的行动自由。'
        cast = ['protagonist', 'rival']
    elif milestone in ('help_couriers', 'secure_samples'):
        flags['courier_decision'] = milestone
        if milestone == 'help_couriers':
            result['relationships']['friend']['trust'] += 1
            result['relationships']['friend']['events'].append('运输线支援')
            summary = '我与周野约定撤离路线，独自引开堵路的魔兽，保住运输队。'
        else:
            result['relationships']['friend']['events'].append('样本优先，运输线绕行')
            summary = '我优先保全污染样本，周野独自调整运输路线；两人记下分歧与代价。'
        cast = ['protagonist', 'friend']
    elif milestone == 'reject_harvest':
        flags['harvest_rejected'] = True
        summary = '谢玄策提出牺牲平民以加速研究，我拒绝该方案，留下公开证据。'
        cast = ['protagonist', 'antagonist']
    elif milestone == 'heroine_sss':
        _consume(result, 'clean_core', 5)
        result['heroine_rank'] = 'SSS'
        flags['heroine_sss'] = True
        result['relationships']['heroine']['events'].append('共同保护核心研究')
        summary = '沈霁月独立完成核心研究，突破SSS；我负责守住实验阵地。'
        cast = ['protagonist', 'heroine']
    elif milestone == 'wall_prepare':
        flags.setdefault('unlocked_bosses', []).append('wall_boss')
        result['chapter'] = max(result['chapter'], 5)
        summary = '尸潮逼近北墙；闻峥组织撤离，周野运送物资，我准备独自迎战母巢。'
        cast = ['protagonist', 'friend', 'commander']
    else:
        _consume(result, 'clean_core', 8)
        result['heroine_rank'] = 'UR'
        flags['heroine_ur'] = True
        result['relationships']['heroine']['events'].append('完成终焉协议研究')
        summary = '沈霁月以北墙验证成果完成研究，晋升UR；我们确认了反向净化的可能。'
        cast = ['protagonist', 'heroine']
    result['story_turn'] += 1
    result['turn'] = result['story_turn']
    result['countdown'] = 5000 - result['story_turn']
    result['operation_seq'] += 1
    result['completed_operations'].append(operation_id)
    result['known_facts'].append(summary)
    event = {'id': uuid4().hex, 'operation_id': operation_id, 'action_id': milestone,
             'story_turn': result['story_turn'], 'summary': summary, 'present_character_ids': cast}
    return validate_state_v2(result), event

def next_story_beats(state):
    validate_state_v2(state);flags=state.get('flags',{});beats=[]
    rank=state['ability_rank'];rank='F-' if rank=='UNRANKED' else rank
    if RANKS.index(rank)>=RANKS.index('UR') and not flags.get('victory'):
        beats.append({'id':'final_route','label':'终焉主线','description':'终战路线已显现；继续完成必要的北墙、研究与塔守卫衔接。'})
    if flags.get('wall_saved') and not flags.get('boss_defeated'):
        beats.append({'id':'tower','label':'通天塔','description':'普通楼层可集中攻略，每十层必须面对守卫。'})
    if flags.get('final_phase')=='purification':
        beats.append({'id':'final_purify','label':'反向净化终焉母核','description':'汇合研究成果，关闭终焉协议。'})
    return beats

def advance_tower_segment(state,operation_id):
    validate_state_v2(state)
    if not isinstance(operation_id,str) or not operation_id.strip():raise ValueError('操作编号无效')
    if operation_id in state['completed_operations']:raise ValueError('该操作已结算')
    if state.get('combat') or state['hp']<=0:raise ValueError('当前不能攻略塔层')
    if not state.get('flags',{}).get('wall_saved'):raise ValueError('须先完成北墙主线')
    if state['story_turn']>=5000:raise ValueError('剧情回合已到上限')
    cleared=set(state.get('cleared_floors',[]));start=state.get('tower_floor',0) or 1
    if not isinstance(start,int) or not 1<=start<=100:raise ValueError('塔层无效')
    if any(f not in cleared for f in range(10,start,10)):raise ValueError('前方守卫尚未击败，不能跳过')
    while start in cleared and start<100:start+=1
    if start%10==0:raise ValueError('请先挑战本层守卫')
    end=((start//10)+1)*10-1;guard=end+1
    result=deepcopy(state);result['story_turn']+=1;result['turn']=result['story_turn']
    result['countdown']=5000-result['story_turn'];result['operation_seq']+=1
    result['completed_operations'].append(operation_id)
    result['cleared_floors']=sorted(cleared|set(range(start,end+1)))
    result['tower_floor']=guard;result['chapter']=6
    unlocks=result.setdefault('flags',{}).setdefault('unlocked_bosses',[])
    guard_id=f'tower_{guard}'
    if guard_id not in unlocks:unlocks.append(guard_id)
    result.setdefault('bestiary',{}).setdefault('seen',[])
    if guard_id not in result['bestiary']['seen']:result['bestiary']['seen'].append(guard_id)
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':'tower_segment',
           'floors':[start,end],'guardian_floor':guard,'story_turn':result['story_turn'],
           'summary':f'独自通过通天塔第{start}至{end}层，抵达第{guard}层守卫。'}
    return result,event

def _final_check(state,operation_id,phase):
    validate_state_v2(state)
    if not isinstance(operation_id,str) or not operation_id.strip():raise ValueError('操作编号无效')
    if operation_id in state['completed_operations']:raise ValueError('该操作已结算')
    if state.get('combat') or state['hp']<=0 or state.get('flags',{}).get('final_phase')!=phase:
        raise ValueError('尚未满足当前结局阶段')

def purify_final_core(state,operation_id):
    _final_check(state,operation_id,'purification')
    if not state['flags'].get('boss_defeated') or state['ability_rank']!='ULTRA' or state.get('heroine_rank')!='UR':
        raise ValueError('尚未完成终战或沈霁月的研究突破')
    result=deepcopy(state);_consume(result,'clean_core',3)
    if result['story_turn']<5000:result['story_turn']+=1
    result['turn']=result['story_turn'];result['countdown']=5000-result['story_turn']
    result['operation_seq']+=1;result['completed_operations'].append(operation_id)
    result['flags'].update(civilization_saved=True,final_phase='epilogue_ready');result['chapter']=7
    result['inventory']['purified_final_fragment']=result['inventory'].get('purified_final_fragment',0)+1
    recipes=result.setdefault('unlocked_recipes',[])
    if 'purified_final_seal' not in recipes:recipes.append('purified_final_seal')
    result['known_facts'].append('终焉母核已反向净化，深渊之环关闭')
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':'final_purify',
           'story_turn':result['story_turn'],'clean_core_cost':3,
           'summary':'陆凌霄反向净化母核，关闭深渊之环，文明的火种得以存续。'}
    return result,event

def finish_epilogue(state,operation_id):
    _final_check(state,operation_id,'epilogue_ready')
    if not state['flags'].get('civilization_saved') or state.get('heroine_rank')!='UR':
        raise ValueError('尚未满足结局条件')
    result=deepcopy(state);result['operation_seq']+=1;result['completed_operations'].append(operation_id)
    result['flags'].update(victory=True,final_phase='finished')
    events=result['relationships']['heroine'].setdefault('events',[])
    if 'wedding' not in events:events.append('wedding')
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':'epilogue',
           'story_turn':result['story_turn'],'present_character_ids':['protagonist','heroine','friend','mentor','commander'],
           'summary':'文明重建后，陆凌霄与沈霁月结婚，伙伴们前来庆祝。独行试炼完成。人类文明存续判定：通过。'}
    return result,event
