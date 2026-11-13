"""Authoritative deterministic game rules. Models only narrate the returned event."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
from .world import CHARACTERS, REALMS, ABILITY_RANKS, scene_for as _world_scene
from .progression import CONFIG as GROWTH,START as RANK_START,rank_for,info as growth_info,migrate

RULES = json.loads((Path(__file__).resolve().parents[1]/'config'/'rules.json').read_text(encoding='utf-8'))
CHECKPOINTS = ('opening','breakthrough','wall','guardian','finale')


def _stage(s): return s['realm_index']*4+s['realm_stage']
def _tactics(s):
    return RULES['approaches'].get(s['preferences'].get('approach'), {})

def _bound(s): return bool(s['flags'].get('system_bound'))
def _item(s,k): return s['inventory'].get(k,0)
def _add(s,k,n): s['inventory'][k]=_item(s,k)+n
def _spend(s,k,n):
    if _item(s,k)<n: raise ValueError(f'资源不足：{k}需要{n}')
    _add(s,k,-n)
def _power(s): return 19+_stage(s)//2+min(s['training_days'],20)//3+(8 if s['equipment'].get('armor')=='black_iron_armor' else 0)+(growth_info(s)['attack_bonus'] if s.get('growth_version') else 0)


def new_game(preferences=None, mode='normal', checkpoint='opening'):
    if mode not in ('normal','demo'): raise ValueError('未知模式')
    if checkpoint not in CHECKPOINTS: raise ValueError('未知演示检查点')
    if mode=='normal' and checkpoint!='opening': raise ValueError('正常模式不能跳级')
    s=dict(schema=1,world_version='1.0',mode=mode,chapter=1,turn=0,day=1,realm_index=0,realm_stage=0,ability_rank='UNRANKED',hunter_rank='未取得资格',hp=40,max_hp=100,energy=35,pollution=0,inventory={'food':RULES['initial_food'],'raw_core':0,'clean_core':0,'material':0},equipment={'weapon':'repair_knife','armor':'repair_jacket'},skills=[{'id':'residual_sense','name':'微弱能量辨识','source':'innate','power':0,'cost':0}],flags={},tower_floor=0,cleared_floors=[],claimed_rewards=[],training_days=0,body_stage='underfed',wounds=['旧伤与饥饿'],relationships={k:{'trust':0,'events':[]} for k in ('heroine','friend','mentor','commander','rival')},known_facts=['灾变已七年','核心污染威胁要塞'],countdown=RULES['countdown'],preferences=deepcopy(preferences or {}),xp=0,abilities=[],heroine_rank='SS',combat=None,echoes=[],consumed_echoes=[],defeated_enemies=[],completed_operations=[],recovery_days=0,encounter_serial=0,last_action='opening',last_event='瘦弱的陆凌霄被低阶魔兽追杀，SS级沈霁月即将赶到。',romance_event=False,skill_slots=RULES['skill_slots'],demo_checkpoint=checkpoint if mode=='demo' else None)
    s['preferences'].setdefault('perspective','first')
    s.update(growth_version=1,ability_xp=0,cores_absorbed=0)
    if mode=='demo' and checkpoint!='opening':
        n={'breakthrough':3,'wall':19,'guardian':39,'finale':39}[checkpoint]
        s.update(realm_index=n//4,realm_stage=n%4,ability_rank=RULES['stages'][n]['rank'],xp=500,training_days=30,day=50,recovery_days=20,body_stage='hardened' if n>20 else 'trained',hp=RULES['stages'][n]['max_hp'],max_hp=RULES['stages'][n]['max_hp'],energy=100,wounds=[],inventory={'food':100,'raw_core':100,'clean_core':100,'material':100})
        s['flags'].update(system_bound=True,**{f'trial_{i}':True for i in range(n+1)})
        s['abilities']=[deepcopy(c['unlock']) for c in RULES['stages'][:n+1] if c.get('unlock')]
        s['equipment']['armor']='black_iron_armor'
        s['skills'].append({'id':'core_pulse','name':'独行核脉冲','source':'system_binding','power':14,'cost':12})
        s['heroine_rank']='UR' if n>=36 else ('SSS' if n>=20 else 'SS')
        s['known_facts']+=['独行系统仅辅助本人','污染可逆向净化']
        s['relationships']['heroine']={'trust':3,'events':['示范存档：共同研究记录']}
        s['chapter']=2 if checkpoint=='breakthrough' else 3 if checkpoint=='wall' else 6 if checkpoint=='guardian' else 7
        if checkpoint in ('guardian','finale'):
            cleared=9 if checkpoint=='guardian' else 99
            s['cleared_floors']=list(range(1,cleared+1)); s['tower_floor']=cleared+1
            s['claimed_rewards']=[f'tower:{i}' for i in range(1,cleared+1)]
            s['flags'].update(wall_saved=True,tower_unlocked=True,heroine_sss=True,heroine_ur=True)
        s['last_event']=f'演示检查点：{checkpoint}。既有资源与经历仅来自标注的演示快照。'
    if s['ability_rank'] in RANK_START:s['ability_xp']=RANK_START[s['ability_rank']]
    bonus=growth_info(s)['hp_bonus'];s['max_hp']+=bonus
    if mode=='demo' and checkpoint!='opening':s['hp']+=bonus
    validate_state(s)
    return s


def actions_for(s):
    if s.get('flags',{}).get('victory') or s['hp']<=0 or s['countdown']<=0: return []
    def a(i,label,hint,kind='action'): return dict(id=i,label=label,hint=hint,kind=kind)
    if not _bound(s): return [a('opening','接受救援 · 绑定系统','SS级沈霁月救下被魔兽追杀的你；救援不算你的击杀。','story')]
    if s.get('combat'):
        c=s['combat']; tactic=_tactics(s); tactical_hint=tactic.get('hint',''); recovery=10+tactic.get('guard_energy_bonus',0); result=[a('attack','普通攻击',f"对{c['name']}造成约{_power(s)}伤害；敌方意图：{c['intent']}。{tactical_hint}",'combat'),a('guard','防御观察',f'减轻本回合伤害、恢复{recovery}能量，破除守卫的蓄力与护壳。{tactical_hint}','combat'),a('retreat','撤离战斗','放弃本次战果与奖励，保留伤势和时间成本。','combat')]
        if s['energy']>=12 and s['pollution']<85 and len(s['skills'])>1 and not c.get('silenced'):
            result.insert(1,a('skill','施展核心技能','消耗12能量，提升污染，造成更大伤害；不能复制敌人全部规则。'+tactical_hint,'combat'))
        if s['pollution']>=20 and _item(s,'clean_core')>0: result.append(a('purify','战中净化','消耗1净核，降低20污染；本回合承受减半攻击。','combat'))
        return result
    result=[]
    if s['energy']>=RULES['train_energy'] and _item(s,'food')>=1:
        result.append(a('train','训练与复盘','消耗20能量和1食物，获得18修炼经验；成长需要训练天数与恢复。'))
    if _item(s,'food')>=1 and (s['energy']<100 or s['hp']<s['max_hp'] or s['wounds']):
        result.append(a('rest','进食休整','消耗1食物和时间，恢复70能量、80生命；不增加修为或材料。'))
    result.append(a('forage','拾荒换取口粮','付出4生命与1回合，获得3食物；不会获得修为、净核或残响。'))
    if s['energy']>=RULES['explore_energy'] and s['pollution']<90:
        result.append(a('explore','探索当前区域','消耗8能量进入遭遇；胜利后获得食物、材料、原核和唯一残响。'))
        if not s['flags'].get(f'trial_{_stage(s)}'):
            result.append(a('trial','独行阶段试炼','亲自击败本阶段试炼敌人，才可突破下一阶段。'))
    if _item(s,'raw_core') and s['energy']>=8 and s['pollution']<95:
        increase=2 if any(x['id']=='furnace_control' for x in s.get('abilities',[])) else 3
        result.append(a('refine','熔炉净化原核',f'消耗1原核、8能量，将其转成1净核；增加{increase}污染。净化不等于吸收。'))
    if _item(s,'clean_core') and s['energy']>=GROWTH['absorb_energy'] and s['pollution']<65:
        gains=growth_info(s)
        result.append(a('absorb_core',f"吸收净核 · 异能EXP +{gains['core_xp']} / 修炼EXP +{gains['cultivation_xp']}",f"消耗1净核、8能量，污染+2；异能经验达到阈值自动升级，境界突破仍需独行试炼。",'growth'))
    if s['pollution']>0 and _item(s,'food')>=RULES['detox_food'] and s['energy']>=RULES['detox_energy']:
        result.append(a('detox','隔离排毒与呼吸恢复','消耗2食物、20能量和1回合，降低15污染；无净核时也可逐步恢复。'))
    if s['pollution']>0 and _item(s,'clean_core'):
        result.append(a('purify','净化自身污染','消耗1净核降低20污染；不生成额外资源。'))
    if s['equipment'].get('armor')!='black_iron_armor' and _item(s,'material')>=6 and _item(s,'clean_core')>=2:
        result.append(a('craft','打造黑铁核心护甲','消耗6材料、2净核；顾砺山指导打造，增加战斗防护。'))
    n=_stage(s); cfg=RULES['stages'][n]
    if n<39 and s['xp']>=cfg['xp'] and _item(s,'clean_core')>=cfg['clean_core'] and s['flags'].get(f'trial_{n}') and s['pollution']<65:
        result.append(a('breakthrough','突破下一阶段',f"消耗{cfg['xp']}经验与{cfg['clean_core']}净核，已完成独行试炼；十境共40阶段。",'growth'))
    if not s['tower_floor']:
        rival=RULES['story_nodes']['rival']; harvest=RULES['story_nodes']['harvest']
        if n>=rival['min_stage'] and not s['flags'].get('rival_resolved'):
            if s['energy']>=rival['refuse_energy']:
                result.append(a('rival_refuse','裴景珩交涉 · 拒绝苛刻契约',f"返回物资站交涉，消耗{rival['refuse_energy']}能量与1回合，坚持独立；与有限交易互斥。",'story'))
            if _item(s,'material')>=rival['trade_material']:
                result.append(a('rival_trade','裴景珩交涉 · 有限交易',f"以{rival['trade_material']}材料换{rival['trade_food']}食物，消耗1回合；不签独家契约，与拒绝分支互斥。",'story'))
        if n>=harvest['min_stage'] and not s['flags'].get('harvest_rejected') and s['energy']>=harvest['energy'] and _item(s,'clean_core')>=harvest['clean_core']:
            result.append(a('reject_harvest','谢玄策提案 · 拒绝牺牲平民',f"返回议事厅，投入{harvest['clean_core']}净核、{harvest['energy']}能量和1回合保存证据，选择不牺牲平民的研究路线。",'story'))
    for echo in s['echoes']:
        if echo['id'] not in s['consumed_echoes'] and len(s['skills'])<s['skill_slots']+1 and s['energy']>=15 and s['pollution']<65 and echo['compatible']:
            result.append(a('absorb:'+echo['id'],'提取残响 · '+echo['skill_name'],'只融合亲自击败敌人的部分能力；消耗15能量、增加8污染，残响仅能使用一次。','growth'))
    if n>=12 and s['heroine_rank']=='SS' and _item(s,'clean_core')>=5:
        result.append(a('heroine_sss','协助沈霁月突破SSS','交付5净核用于她独立研究，男主护住实验阵地；记录共同选择事件。','story'))
    if n>=32 and s['heroine_rank']=='SSS' and _item(s,'clean_core')>=8 and s['flags'].get('wall_saved'):
        result.append(a('heroine_ur','协助沈霁月突破UR','交付8净核与北墙验证成果，帮助她承担研究代价；不替代她的研究。','story'))
    if n>=19 and not s['flags'].get('wall_saved') and s['energy']>=8:
        result.append(a('wall_defend','独守北墙关键战线','闻峥组织撤离、周野运补、沈霁月稳封印，你独自迎战破城兽。','story'))
    if n==39 and s['flags'].get('wall_saved') and not s['flags'].get('boss_defeated') and s['energy']>=8:
        result.append(a('enter_floor',f"挑战通天塔第{s['tower_floor'] or 1}层",'逐层独行；每十层专属守卫，失败可撤退重试，奖励仅结算一次。','tower'))
    if s['flags'].get('boss_defeated') and s['heroine_rank']=='UR' and s['ability_rank']=='UR' and _item(s,'clean_core')>=3:
        result.append(a('final_purify','反向净化终焉母核','消耗3净核，凭完整塔层战果与研究成果阻止文明收割，觉醒ULTRA。','finale'))
    result.append(a('scan','扫描与任务复盘','消耗1回合获取当前敌我与突破条件；不赠送经验或材料。'))
    return result


def _start_combat(s,kind):
    s['encounter_serial']+=1; n=_stage(s)
    if kind=='tower':
        floor=s['tower_floor'] or 1
        cfg=RULES['floors'][floor-1]
        c=dict(cfg,id=f'tower:{floor}',kind=kind,max_hp=cfg['hp'],intent=cfg['mechanic'])
    else:
        name='阶段试炼守卫' if kind=='trial' else '破城重甲兽' if kind=='wall' else ['裂爪兽','污染甲虫','噬能游猎者'][s['encounter_serial']%3]
        c=dict(id=f"{kind}:{n}:{s['encounter_serial']}",name=name,kind=kind,hp=48+n,max_hp=48+n,damage=10+n//5,pollution=3,guardian=kind=='wall',intent='蓄力扑击，防御可减少伤害。')
    c.update(round=0,broken=False,silenced=False)
    s['combat']=c
    return f"独自迎战{c['name']}。{c['intent']}"


def _hit(s,guard=False):
    c=s['combat']; damage=c['damage']+_tactics(s).get('incoming_bonus',0)
    if s['equipment'].get('armor')=='black_iron_armor': damage=max(2,damage-5)
    if c['guardian'] and c['round']%3==1 and not c['broken']: damage*=2
    floor=c.get('floor',0)
    if floor==30 and not guard: s['pollution']=min(100,s['pollution']+4)
    if floor==70 and not guard: damage+=4
    if floor==80 and not guard: s['energy']=max(0,s['energy']-5)
    if floor==100 and not c['broken'] and not guard: damage+=8
    if any(a['id']=='energy_barrier' for a in s.get('abilities',[])): damage=max(1,damage-2)
    if guard: damage=max(1,damage//4); c['broken']=True
    s['hp']=max(0,s['hp']-damage)
    s['pollution']=min(100,s['pollution']+(1 if guard else c['pollution']))
    if s['pollution']>=90: s['hp']=max(0,s['hp']-8)
    if damage>=12 and '战斗伤' not in s['wounds']: s['wounds'].append('战斗伤')
    return damage


def _reward(s,c):
    rid=c['id']
    if rid in s['claimed_rewards']: raise ValueError('本战果已结算')
    s['claimed_rewards'].append(rid); s['defeated_enemies'].append(rid)
    _add(s,'food',4); _add(s,'raw_core',4); _add(s,'material',3)
    s['xp']+=20+_stage(s)
    echo_id='echo:'+rid
    s['echoes'].append(dict(id=echo_id,enemy_id=rid,skill_name='甲壳护势' if c['guardian'] else '裂爪突进',compatible=(c['kind']!='tower' or c['floor']%10!=0 or c['floor']<=70),power=10 if c['guardian'] else 7))
    if c['kind']=='trial':
        s['flags'][f'trial_{_stage(s)}']=True
        s['hunter_rank']='F级合格猎人' if _stage(s)<12 else '高阶独行猎人'
    if c['kind']=='wall': s['flags']['wall_saved']=True; s['chapter']=5; s['known_facts'].append('北墙撤离线已守住')
    if c['kind']=='tower':
        f=c['floor']; s['cleared_floors'].append(f); _add(s,'clean_core',c['reward_clean_core'])
        s['tower_floor']=min(100,f+1); s['chapter']=7 if f>=90 else 6
        if f==100: s['flags']['boss_defeated']=True
    s['combat']=None
    return f"亲自击败{c['name']}，获得4食物、4原核、3材料和唯一残响；本次战果已锁定，不能重复领奖。"


def _sync(s):
    n=_stage(s)
    if _bound(s) and not s['flags'].get('victory'): s['ability_rank']=rank_for(s['ability_xp'])
    s['max_hp']=RULES['stages'][n]['max_hp']+growth_info(s)['hp_bonus']
    if s['tower_floor']==0:
        s['chapter']=1 if n<4 else 2 if n<12 else 3 if n<20 else 4 if n<28 else 5
    if s['training_days']>=20 and s['recovery_days']>=8 and n>=20: s['body_stage']='hardened'
    elif s['training_days']>=8 and s['recovery_days']>=4: s['body_stage']='trained'
    elif s['training_days']>=3 and s['recovery_days']>=1: s['body_stage']='recovering'
    s['hp']=min(s['hp'],s['max_hp'])


def apply_action(state, action_id, operation_id=''):
    validate_state(state)
    if operation_id and operation_id in state['completed_operations']: raise ValueError('该操作已结算')
    legal={a['id']:a for a in actions_for(state)}
    if action_id not in legal: raise ValueError('当前状态不允许此行动，请选择合法选项')
    s=migrate(deepcopy(state)); s['turn']+=1; s['countdown']-=1; s['romance_event']=False
    s['last_action']=action_id.split(':')[0]
    if operation_id: s['completed_operations'].append(operation_id)
    text=''; kind=legal[action_id]['kind']; n=_stage(s)
    if action_id=='opening':
        s['flags']['system_bound']=True; s['ability_rank']='F-'; s['hp']=80; s['energy']=85
        s['skills'].append(dict(id='core_pulse',name='独行核脉冲',source='system_binding',power=14,cost=12))
        s['relationships']['heroine']['events'].append('SS级沈霁月救援'); s['relationships']['heroine']['trust']=1
        s['known_facts']+=['沈霁月是SS级研究员','系统绑定只辅助自身训练与净化']
        text='SS级沈霁月以封印挡住追杀你的魔兽，把瘦弱受伤的你带到掩体。你没有取得击杀战果。独行进化系统绑定；能量辨识仍微弱，变强需要训练与实战。'
    elif action_id in ('explore','trial','wall_defend','enter_floor'):
        s['energy']-=8
        if action_id=='enter_floor':
            if not s['tower_floor']: s['tower_floor']=1
            s['chapter']=7 if s['tower_floor']>=90 else 6
        text=_start_combat(s,{'explore':'explore','trial':'trial','wall_defend':'wall','enter_floor':'tower'}[action_id])
    elif action_id in ('attack','skill','guard'):
        c=s['combat']; c['round']+=1
        if action_id=='guard':
            recovery=10+_tactics(s).get('guard_energy_bonus',0)
            s['energy']=min(100,s['energy']+recovery); dmg=_hit(s,True); text=f'防御观察，承受{dmg}伤害，打断护壳与蓄力并恢复{recovery}能量。'
        else:
            damage=_power(s)
            if action_id=='attack': damage+=_tactics(s).get('attack_bonus',0)
            if not c.get('last_attack'): damage+=_tactics(s).get('first_hit_bonus',0)
            if action_id=='skill': s['energy']-=12; s['pollution']=min(100,s['pollution']+3); damage+=max(skill.get('power',0) for skill in s['skills'])
            if c['guardian'] and not c['broken'] and c['round']<=2: damage=max(1,damage//2)
            if c.get('floor')==20 and action_id=='skill' and not c['broken']: s['hp']=max(0,s['hp']-4)
            if c.get('floor')==90 and action_id=='skill' and c.get('last_attack')=='skill': damage=max(1,damage//2)
            c['last_attack']=action_id
            c['hp']=max(0,c['hp']-damage)
            text=f'攻击造成{damage}伤害。'
            if c['hp']==0: text+=_reward(s,c)
            else: text+=f"承受反击{_hit(s)}伤害，敌人剩余{c['hp']}生命。"
        if s.get('combat'):
            s['combat']['silenced']=bool(s['combat'].get('floor')==60 and s['combat']['round']%3==1)
    elif action_id=='retreat': s['combat']=None; text='沿预留退路撤离，没有获得战果或残响，伤势与时间代价保留。'
    elif action_id=='train':
        _spend(s,'food',RULES['train_food']); s['energy']-=RULES['train_energy']; s['training_days']+=1; s['day']+=1; s['xp']+=RULES['train_xp']
        text='完成呼吸、负重与动作复盘，消耗食物和能量获得18经验。训练成果仍需要进食休息巩固。'
    elif action_id=='rest':
        _spend(s,'food',1); s['energy']=min(100,s['energy']+RULES['rest_energy']); s['hp']=min(s['max_hp'],s['hp']+RULES['rest_hp']); s['recovery_days']+=1; s['day']+=1; s['wounds']=[]
        text='进食并休整，恢复生命与能量，清理伤口。时间继续流逝，没有获得修为或免费材料。'
    elif action_id=='forage':
        s['hp']=max(1,s['hp']-4); _add(s,'food',3); text='用维修手艺换取3份口粮，来回拾荒损耗4生命与时间。'
    elif action_id=='refine':
        increase=2 if any(a['id']=='furnace_control' for a in s.get('abilities',[])) else 3
        _spend(s,'raw_core',1); _add(s,'clean_core',1); s['energy']-=8; s['pollution']=min(100,s['pollution']+increase); text=f'熔炉把1原核炼成1净核，消耗8能量并积累{increase}污染。这是制备材料，还未吸收；可随后选择吸收净核获得异能和修炼经验。'
    elif action_id=='absorb_core':
        gains=growth_info(s);_spend(s,'clean_core',1);s['energy']-=GROWTH['absorb_energy'];s['pollution']=min(100,s['pollution']+GROWTH['absorb_pollution'])
        s['ability_xp']+=gains['core_xp'];s['xp']+=gains['cultivation_xp'];s['cores_absorbed']+=1
        text=f"独自在安全处吸收1枚净核，异能EXP +{gains['core_xp']}，修炼EXP +{gains['cultivation_xp']}；能量-8、污染+2。系统熔炉与面板只在陆凌霄意识中运行，没有向他人透露。"
    elif action_id=='purify':
        _spend(s,'clean_core',1); amount=25 if any(a['id']=='core_scan' for a in s.get('abilities',[])) else 20
        s['pollution']=max(0,s['pollution']-amount); text=f'消耗1净核，降低{amount}污染。'
        if s.get('combat'): text+=f'净化期间承受{_hit(s,True)}伤害。'
    elif action_id=='detox':
        _spend(s,'food',RULES['detox_food']); s['energy']-=RULES['detox_energy']; s['pollution']=max(0,s['pollution']-RULES['detox_amount']); text='隔离排毒并进行呼吸恢复，消耗2份食物与20能量，降低15污染，没有生成净核。'
    elif action_id=='craft':
        _spend(s,'material',6); _spend(s,'clean_core',2); s['equipment']['armor']='black_iron_armor'; s['flags']['armor_crafted']=True; text='在顾砺山指导下，以实有材料打造黑铁核心护甲。'
    elif action_id=='breakthrough':
        cfg=RULES['stages'][n]; s['xp']-=cfg['xp']; _spend(s,'clean_core',cfg['clean_core']); n+=1; s['realm_index']=n//4; s['realm_stage']=n%4; s['hp']+=8
        if RULES['stages'][n].get('unlock'): s['abilities'].append(deepcopy(RULES['stages'][n]['unlock']))
        text=f"独行试炼与材料条件齐备，突破至{REALMS[n//4]}{RULES['stages'][n]['phase']}；修炼与异能评级分别记录。"
    elif action_id.startswith('absorb:'):
        eid=action_id[len('absorb:'):]; echo=next(e for e in s['echoes'] if e['id']==eid)
        if echo['enemy_id'] not in s['defeated_enemies']: raise ValueError('残响来源未亲自击败')
        s['energy']-=15; s['pollution']+=8; s['consumed_echoes'].append(eid); s['skills'].append(dict(id='extracted:'+eid,name=echo['skill_name'],source=eid,power=echo['power'],cost=12)); text=f"残响已消耗，仅融合部分能力「{echo['skill_name']}」，不复制敌人完整规则。"
    elif action_id in ('rival_refuse','rival_trade'):
        cfg=RULES['story_nodes']['rival']; s['flags']['rival_resolved']=True
        rel=s['relationships']['rival']
        if action_id=='rival_refuse':
            s['energy']-=cfg['refuse_energy']; s['flags']['rival_refused']=True
            rel['events'].append('拒绝苛刻的独家核心契约，承担独立交涉成本')
            s['known_facts'].append('裴景珩试图用独家契约控制独行猎人的核心配额；陆凌霄已拒绝')
            text=f"陆凌霄返回物资站。象牙白黑金战斗长衣的裴景珩转动纹章戒，礼貌地把核心配额与独家服从绑定。陆凌霄核对条款后拒绝，花费{cfg['refuse_energy']}能量处理交涉，未获得赠品或修为。裴景珩改为按公开交易规则审视他，仍非朋友，也不知道独行系统。"
        else:
            _spend(s,'material',cfg['trade_material']); _add(s,'food',cfg['trade_food']); s['flags']['rival_traded']=True
            rel['trust']+=1; rel['events'].append('拒绝独家依附，只按明价完成一次材料换口粮')
            s['known_facts'].append('裴景珩接受一次明码材料交易，双方没有建立独家依附或盟友关系')
            text=f"陆凌霄返回物资站，逐项核对裴景珩递来的账单。对方衣装整洁、措辞彬彬有礼，却仍用等级衡量配额。你不接受独家依附，只以实有的{cfg['trade_material']}材料换取{cfg['trade_food']}份库存食物。双方留下有限履约记录，没有跳级、赠送神器或泄露独行系统。"
    elif action_id=='reject_harvest':
        cfg=RULES['story_nodes']['harvest']; s['energy']-=cfg['energy']; _spend(s,'clean_core',cfg['clean_core'])
        s['flags'].update(harvest_rejected=True,civilian_research_route=True)
        rel=s['relationships'].setdefault('antagonist',{'trust':0,'events':[]})
        rel['events'].append('拒绝牺牲平民的收割提案，投入自身净核保存证据')
        s['known_facts'].extend(['谢玄策提出以外围平民生命交换可控生存区，陆凌霄已拒绝','已保存收割提案证据并建立不牺牲平民的研究路线；收割机制仍不完整'])
        text=f"返回临时议事厅，陆凌霄面对深石墨长外套、右颈带暗金接口纹的谢玄策。对方耐心说明以外围平民换取生存区的提案，把人写成可交换的数字。陆凌霄拒绝授权，投入自己的{cfg['clean_core']}净核和{cfg['energy']}能量封存证据，选择独立验证不牺牲平民的研究路线。谢玄策只掌握部分收割线索，并不知道独行系统。此举没有击败或替代百层母皇，最终试炼仍须本人完成。"
    elif action_id in ('heroine_sss','heroine_ur'):
        higher=action_id=='heroine_ur'; _spend(s,'clean_core',8 if higher else 5); s['heroine_rank']='UR' if higher else 'SSS'; s['flags'][action_id]=True
        rel=s['relationships']['heroine']; rel['trust']+=1; rel['events'].append('共同守护逆向净化实验' if higher else '为她守住研究阵地')
        s['romance_event']=not s['flags'].get('romance_chapter_'+str(s['chapter']),False)
        s['flags']['romance_chapter_'+str(s['chapter'])]=True
        text=f"陆凌霄用亲自取得的净核支撑研究，并为沈霁月挡住外部危险。她在自己的封印与研究成果上突破至{s['heroine_rank']}，向可信任的同伴坦言一次实验失败的恐惧。"
    elif action_id=='final_purify':
        _spend(s,'clean_core',3); s['flags']['victory']=True; s['ability_rank']='ULTRA'; s['pollution']=0; s['chapter']=7
        text='陆凌霄亲自击败百层终焉之核，结合沈霁月在塔外验证的逆向净化协议反转母核。男主觉醒ULTRA，污染网络解除，文明火种得以延续。'
    elif action_id=='scan':
        cfg=RULES['stages'][n]; text=f"当前{REALMS[n//4]}{cfg['phase']}，异能{s['ability_rank']}，沈霁月{s['heroine_rank']}。下一阶段需要经验{cfg['xp']}、净核{cfg['clean_core']}及本阶段独行试炼；已完成{len(s['cleared_floors'])}/100层。"
    _sync(s)
    if s['ability_rank']!=state['ability_rank'] and action_id not in ('opening','final_purify'):
        text+=f"异能评级{state['ability_rank']}→{s['ability_rank']}，最大生命提升至{s['max_hp']}，体能与力量得到强化；外在肌肉仍按训练和恢复阶段渐进呈现。"
    if s['hp']==0: text+='生命耗尽，本分支失败；可返回已保存的分支重试。'
    if s['countdown']==0: text+='终焉倒计时归零，本分支结束。'
    s['last_event']=text
    event=dict(id=f"turn:{s['turn']}",action_id=action_id,kind=kind,summary=text,description=text,turn=s['turn'],operation_id=operation_id,rewards_locked=True)
    baseline=dict(state);baseline.setdefault('ability_xp',RANK_START.get(state['ability_rank'],RANK_START['UR'] if state['ability_rank']=='ULTRA' else 0))
    event['changes']={k:s[k]-baseline.get(k,0) for k in ('hp','max_hp','energy','pollution','xp','ability_xp') if s[k]!=baseline.get(k,0)}
    if s['ability_rank']!=state['ability_rank']:event['ability_rank_change']={'from':state['ability_rank'],'to':s['ability_rank']}
    validate_state(s)
    return s,event


def scene_for(state,event=None):
    scene=_world_scene(state,event)
    if event: scene['main_action']=event.get('summary',scene['main_action'])
    return scene


def validate_state(s):
    """Reject malformed snapshots before any rule reads or mutates nested values.

    Schema 1 requires the complete runtime snapshot; incomplete old saves are
    rejected explicitly rather than silently supplying progression/reward data.
    """
    def fail(field): raise ValueError('非法或缺失状态字段：'+field)
    def integer(value, field, low=0, high=1000000):
        if type(value) is not int or not low<=value<=high: fail(field)
    def strings(value, field, unique=False):
        if not isinstance(value,list) or any(not isinstance(v,str) for v in value): fail(field)
        if unique and len(value)!=len(set(value)): fail(field)
    def record(value, field, fields):
        if not isinstance(value,dict) or any(k not in value for k in fields): fail(field)
    if not isinstance(s,dict) or type(s.get('schema')) is not int or s['schema']!=1:
        fail('schema')
    required='world_version mode chapter turn day realm_index realm_stage ability_rank hunter_rank hp max_hp energy pollution inventory equipment skills flags tower_floor cleared_floors claimed_rewards training_days body_stage wounds relationships known_facts countdown preferences xp heroine_rank combat echoes consumed_echoes defeated_enemies completed_operations recovery_days encounter_serial last_action last_event romance_event skill_slots demo_checkpoint abilities'.split()
    if any(k not in s for k in required): fail(' / '.join(k for k in required if k not in s))
    for key in ('world_version','mode','ability_rank','hunter_rank','body_stage','heroine_rank','last_action','last_event'):
        if not isinstance(s[key],str): fail(key)
    if s['world_version']!='1.0': fail('world_version')
    if s['mode'] not in ('normal','demo'): fail('mode')
    if s['ability_rank'] not in ['UNRANKED']+ABILITY_RANKS: fail('ability_rank')
    if s['heroine_rank'] not in ('SS','SSS','UR'): fail('heroine_rank')
    if s['hunter_rank'] not in ('未取得资格','F级合格猎人','高阶独行猎人'): fail('hunter_rank')
    if s['body_stage'] not in ('underfed','recovering','trained','hardened'): fail('body_stage')
    if s['demo_checkpoint'] is not None and (not isinstance(s['demo_checkpoint'],str) or s['demo_checkpoint'] not in CHECKPOINTS): fail('demo_checkpoint')
    if s['mode']=='normal' and s['demo_checkpoint'] is not None: fail('demo_checkpoint')
    if type(s['romance_event']) is not bool: fail('romance_event')
    for key,low,high in [('chapter',1,7),('realm_index',0,9),('realm_stage',0,3),('energy',0,100),('pollution',0,100),('tower_floor',0,100),('max_hp',1,1000000),('turn',0,1000000),('day',1,1000000),('countdown',0,RULES['countdown']),('xp',0,1000000),('training_days',0,1000000),('recovery_days',0,1000000),('encounter_serial',0,1000000),('skill_slots',1,20)]:
        integer(s[key],key,low,high)
    integer(s['hp'],'hp',0,s['max_hp'])
    for key in ('inventory','equipment','flags','relationships','preferences'):
        if not isinstance(s[key],dict) or any(not isinstance(k,str) for k in s[key]): fail(key)
    if 'approach' in s['preferences'] and not isinstance(s['preferences']['approach'],str): fail('preferences.approach')
    for key in ('food','raw_core','clean_core','material'):
        if key not in s['inventory']: fail('inventory.'+key)
    for key,value in s['inventory'].items(): integer(value,'inventory.'+key)
    for key in ('weapon','armor'):
        if not isinstance(s['equipment'].get(key),str): fail('equipment.'+key)
    if any(not isinstance(v,str) for v in s['equipment'].values()): fail('equipment')
    if any(type(v) is not bool for v in s['flags'].values()): fail('flags')
    for key in ('wounds','known_facts','claimed_rewards','consumed_echoes','defeated_enemies','completed_operations'):
        strings(s[key],key,unique=key not in ('wounds','known_facts'))
    if not isinstance(s['cleared_floors'],list): fail('cleared_floors')
    for floor in s['cleared_floors']: integer(floor,'cleared_floors',1,100)
    if s['cleared_floors']!=list(range(1,len(s['cleared_floors'])+1)): fail('cleared_floors')
    if s['tower_floor'] and s['tower_floor']!=min(100,len(s['cleared_floors'])+1): fail('tower_floor')
    if s['cleared_floors'] and not s['tower_floor']: fail('tower_floor')
    for cid in ('heroine','friend','mentor','commander','rival'):
        if cid not in s['relationships']: fail('relationships.'+cid)
    for cid,rel in s['relationships'].items():
        record(rel,'relationships.'+cid,('trust','events'))
        integer(rel['trust'],'relationships.'+cid+'.trust')
        strings(rel['events'],'relationships.'+cid+'.events')
    for key in ('skills','abilities','echoes'):
        if not isinstance(s[key],list): fail(key)
    if not s['skills'] or len(s['skills'])>s['skill_slots']+1: fail('skills')
    skill_ids=[]
    for skill in s['skills']:
        record(skill,'skills',('id','name','source','power','cost'))
        for key in ('id','name','source'):
            if not isinstance(skill[key],str) or not skill[key]: fail('skills.'+key)
        integer(skill['power'],'skills.power'); integer(skill['cost'],'skills.cost',0,100)
        skill_ids.append(skill['id'])
    if len(skill_ids)!=len(set(skill_ids)): fail('skills.id')
    for ability in s['abilities']:
        record(ability,'abilities',('id','name','effect'))
        if any(not isinstance(ability[k],str) for k in ('id','name','effect')): fail('abilities')
    echo_ids=[]
    for echo in s['echoes']:
        record(echo,'echoes',('id','enemy_id','skill_name','compatible','power'))
        if any(not isinstance(echo[k],str) or not echo[k] for k in ('id','enemy_id','skill_name')): fail('echoes')
        if type(echo['compatible']) is not bool: fail('echoes.compatible')
        integer(echo['power'],'echoes.power')
        if echo['enemy_id'] not in s['defeated_enemies']: fail('echoes.enemy_id')
        echo_ids.append(echo['id'])
    if len(echo_ids)!=len(set(echo_ids)) or any(e not in echo_ids for e in s['consumed_echoes']): fail('echoes.id')
    c=s['combat']
    if c is not None:
        record(c,'combat',('id','name','kind','hp','max_hp','damage','pollution','guardian','intent','round','broken','silenced'))
        if any(not isinstance(c[k],str) for k in ('id','name','kind','intent')): fail('combat')
        if c['kind'] not in ('tower','trial','wall','explore'): fail('combat.kind')
        for key in ('guardian','broken','silenced'):
            if type(c[key]) is not bool: fail('combat.'+key)
        integer(c['max_hp'],'combat.max_hp',1); integer(c['hp'],'combat.hp',1,c['max_hp'])
        for key in ('damage','pollution','round'): integer(c[key],'combat.'+key)
        if c['kind']=='tower':
            for key in ('floor','reward_clean_core'):
                if key not in c: fail('combat.'+key)
            integer(c['floor'],'combat.floor',1,100); integer(c['reward_clean_core'],'combat.reward_clean_core')
            if c['floor']!=s['tower_floor']: fail('combat.floor')
    minimum={'underfed':(0,0),'recovering':(3,1),'trained':(8,4),'hardened':(20,8)}[s['body_stage']]
    if s['training_days']<minimum[0] or s['recovery_days']<minimum[1]: fail('body_stage')
    expected=RULES['stages'][_stage(s)]['rank'] if _bound(s) else 'UNRANKED'
    if 'growth_version' in s:
        if type(s['growth_version']) is not int or s['growth_version']!=1:fail('growth_version')
        for key in ('ability_xp','cores_absorbed'):
            if key not in s:fail(key)
            integer(s[key],key)
        expected=rank_for(s['ability_xp']) if _bound(s) else 'UNRANKED'
    if not s['flags'].get('victory') and s['ability_rank']!=expected: fail('ability_rank')
    if s['equipment'].get('armor')=='black_iron_armor' and s['mode']=='normal' and not s['flags'].get('armor_crafted'): fail('equipment.armor')
    if s['flags'].get('victory') and (len(s['cleared_floors'])!=100 or not s['flags'].get('boss_defeated') or s['ability_rank']!='ULTRA'): fail('flags.victory')
    if s['ability_rank']=='ULTRA' and not s['flags'].get('victory'): fail('ability_rank')
    try: json.dumps(s,ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError,RecursionError) as exc: raise ValueError('状态必须为有限JSON数据') from exc
