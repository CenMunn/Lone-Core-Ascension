"""Draft v2 encounters and atomic combat exchanges."""
from copy import deepcopy
from uuid import uuid4
from .catalog import MONSTERS, ABILITIES, EQUIPMENT, DUNGEONS
from .models_v2 import base_stats, validate_state_v2

RANKS=['F-','E','D','C','B','A','S','SS','SSS','UR','ULTRA']

def _check_operation(state,operation_id):
    validate_state_v2(state)
    if state.get('legacy_battle_requires_old_rules') and state.get('combat'):
        raise ValueError('当前节点是旧版战斗，请先在旧版完成本场后再迁移。')
    if not isinstance(operation_id,str) or not operation_id.strip():raise ValueError('操作编号无效')
    if operation_id in state.get('completed_operations',[]):raise ValueError('该操作已结算')

def _record(state,operation_id):
    state['operation_seq']+=1;state['completed_operations'].append(operation_id)

def _known_skills(state):
    by_name={x['name']:i for i,x in ABILITIES.items()}
    candidates=(x.get('catalog_id') or (x['id'] if x.get('id') in ABILITIES else by_name.get(x.get('name')))
                for x in state.get('skills',[]) if isinstance(x,dict))
    return {x for x in candidates if x in ABILITIES}

def _gear_stat(state,key):
    slots=state.get('equipment_slots');items=state.get('equipment_items') or {}
    if isinstance(slots,dict):
        equipped=[items.get(instance,{}).get('item_id') for instance in slots.values() if instance]
    else:equipped=state.get('equipment',{}).values()
    return sum(EQUIPMENT[item].get('stats',{}).get(key,0) for item in equipped if item in EQUIPMENT)

def _wears(state,item_id):
    items=state.get('equipment_items') or {}
    return any(items.get(instance,{}).get('item_id')==item_id
               for instance in (state.get('equipment_slots') or {}).values() if instance)

def _gear_effects(state):
    items=state.get('equipment_items') or {}
    return {EQUIPMENT.get(items.get(instance,{}).get('item_id'),{}).get('special_effect')
            for instance in (state.get('equipment_slots') or {}).values() if instance}

def start_encounter(state,monster_id,operation_id,*,source='story'):
    _check_operation(state,operation_id)
    if state.get('combat') or state.get('hp',0)<=0:raise ValueError('当前不能开始新战斗')
    if source not in ('story','codex') or monster_id not in MONSTERS:raise ValueError('魔物或挑战来源无效')
    if state.get('story_turn',0)>=5000:raise ValueError('剧情回合已到上限')
    monster=MONSTERS[monster_id];bestiary=state.get('bestiary') or {}
    rank=state.get('ability_rank','F-');rank='F-' if rank=='UNRANKED' else rank
    if source=='story' and not monster['boss'] and RANKS.index(monster['rank'])>RANKS.index(rank):
        raise ValueError('当前评级尚未开放该区域的魔物')
    if source=='codex' and (monster['boss'] or monster_id not in bestiary.get('seen',[])):
        raise ValueError('该魔物尚未解锁或不能重复挑战')
    if monster['boss']:
        if monster_id in bestiary.get('defeated_bosses',[]):raise ValueError('本分支已击败该首领')
        if monster_id not in state.get('flags',{}).get('unlocked_bosses',[]):raise ValueError('尚未触发该首领剧情')
        if monster.get('floor') and state.get('tower_floor')!=monster['floor']:raise ValueError('当前不在该守卫楼层')
        if monster.get('floor')==100 and (state.get('ability_rank')!='UR' or any(f not in state.get('cleared_floors',[]) for f in range(1,100))):
            raise ValueError('终战需要UR及此前塔层记录')
        if monster.get('floor')==100 and (state.get('heroine_rank')!='UR' or state['inventory'].get('clean_core',0)<3):
            raise ValueError('终战前需完成沈霁月的UR研究并准备3枚净核用于净化母核')
    result=deepcopy(state);_record(result,operation_id)
    result['story_turn']+=1;result['turn']=result['story_turn'];result['countdown']=5000-result['story_turn']
    result.setdefault('bestiary',{}).setdefault('seen',[])
    if monster_id not in result['bestiary']['seen']:result['bestiary']['seen'].append(monster_id)
    seen_abilities=result['bestiary'].setdefault('abilities_seen',[])
    for ability_id in monster['abilities']:
        if ability_id not in seen_abilities:seen_abilities.append(ability_id)
    dungeons_seen=result['bestiary'].setdefault('dungeons_seen',[])
    for dungeon_id,dungeon in DUNGEONS.items():
        if monster_id in dungeon['monster_ids'] and dungeon_id not in dungeons_seen:
            dungeons_seen.append(dungeon_id)
    encounter_id=uuid4().hex
    result['combat']={'id':encounter_id,'monster_id':monster_id,'name':monster['name'],
                      'hp':monster['hp'],'max_hp':monster['hp'],'attack':monster['attack'],
                      'exchange':0,'effects':[],'player_effects':[],'cooldowns':{},'player_shield':0,
                      'anchor_used':False,'anchor_charges':0,'source':source}
    if monster.get('floor')==100:
        result['combat']['final_phase']='suppression';result['flags']['final_phase']='battle'
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':'start_encounter',
           'monster_id':monster_id,'encounter_id':encounter_id,'story_turn':result['story_turn'],
           'summary':f"独自迎战{monster['name']}。"}
    return result,event

def _victory(state,combat):
    monster=MONSTERS[combat['monster_id']];reward_id='encounter:'+combat['id']
    if reward_id in state['claimed_rewards']:raise ValueError('本次战斗已结算')
    state['claimed_rewards'].append(reward_id);state['defeated_enemies'].append(reward_id)
    cores=3 if monster['boss'] else 2
    state['inventory']['raw_core']=state['inventory'].get('raw_core',0)+cores
    state['inventory']['material']=state['inventory'].get('material',0)+2
    grades=state.setdefault('core_grades',{});grades[monster['rank']]=grades.get(monster['rank'],0)+cores
    if monster.get('elite_material'):
        material=monster['elite_material']
        state['inventory'][material]=state['inventory'].get(material,0)+1
        recipes=state.setdefault('unlocked_recipes',[])
        for item in EQUIPMENT.values():
            if item.get('unlock_material')==material and item['id'] not in recipes:
                recipes.append(item['id'])
    level=state['realm_index']*3+state['realm_stage'];cost=60+16*level+4*(level//3)**2
    rank=state.get('ability_rank','F-');rank='F-' if rank=='UNRANKED' else rank
    diff=max(0,RANKS.index(rank)-RANKS.index(monster['rank']))
    xp=max(1,round(cost*.18*(.45**diff)))
    if 'trial_realm' in monster:xp+=cost
    state['xp']+=xp
    bestiary=state.setdefault('bestiary',{});seen=bestiary.setdefault('abilities_seen',[])
    for skill in monster['abilities']:
        if skill not in seen:seen.append(skill)
    if monster['boss']:
        bestiary.setdefault('defeated_bosses',[]).append(monster['id'])
        floor=monster.get('floor')
        if floor:
            if floor not in state['cleared_floors']:state['cleared_floors'].append(floor)
            state['cleared_floors'].sort();state['tower_floor']=min(100,floor+1)
            if floor==100:state['flags'].update(boss_defeated=True,final_phase='purification')
        if monster['id']=='wall_boss':state['flags']['wall_saved']=True
        if 'trial_realm' in monster:
            state['flags'].setdefault('trials_v2',{})[str(monster['trial_realm'])]=True
        for item in EQUIPMENT.values():
            if item.get('boss_id')==monster['id'] and item.get('unlock_material') and not item.get('unlock_after_purification'):
                material=item['unlock_material'];state['inventory'][material]=state['inventory'].get(material,0)+1
                recipes=state.setdefault('unlocked_recipes',[])
                if item['id'] not in recipes:recipes.append(item['id'])
    for ability in dict.fromkeys(monster['abilities']):
        echo_id='echo:'+combat['id']+':'+ability
        state.setdefault('echoes',[]).append({'id':echo_id,'enemy_id':reward_id,'catalog_id':ability,
            'skill_name':ABILITIES[ability]['name'],'compatible':True,'power':0})
    state['combat_wins']=state.get('combat_wins',0)+1
    if state['combat_wins']>=3 and state.get('recovery_days',0)>=1 and state.get('body_stage')=='underfed':
        state['body_stage']='recovering'
    state['combat']=None
    return xp

def combat_step(state,request,operation_id):
    _check_operation(state,operation_id)
    combat=state.get('combat')
    if not isinstance(combat,dict) or state.get('hp',0)<=0:raise ValueError('当前没有可继续的战斗')
    if not isinstance(request,dict) or request.get('action') not in ('attack','skill','guard','retreat','awaken','tactic'):
        raise ValueError('战斗行动无效')
    action=request['action'];skill_id=request.get('skill_id');skill=None
    proposal=None
    if action=='tactic':
        from .tactics_v2 import validate_proposal
        proposal=validate_proposal(request.get('proposal'))
        if state['energy']<proposal['energy_cost']:raise ValueError('核心能量不足')
    next_exchange=combat['exchange']+1
    if action=='awaken' and (combat.get('monster_id')!='tower_100' or combat.get('final_phase')!='suppression'
                             or state['ability_rank']!='UR' or combat['exchange']<2):
        raise ValueError('尚未满足终战觉醒条件')
    if action=='skill':
        if skill_id not in _known_skills(state) or skill_id not in ABILITIES:raise ValueError('尚未掌握该能力')
        skill=ABILITIES[skill_id]
        if skill['effect']=='passive':raise ValueError('该能力无需主动施放')
        if state['energy']<skill['energy_cost']:raise ValueError('核心能量不足')
        if next_exchange<combat['cooldowns'].get(skill_id,0):raise ValueError('该能力仍在冷却')
        if skill_id=='causal_anchor' and combat.get('anchor_used'):raise ValueError('该能力本场已使用')
        if skill['effect']=='energy_heal' and state['hp']<=max(1,round(state['max_hp']*.1)):
            raise ValueError('生命不足以转换能量')
        if skill['effect']=='energy_heal' and state['energy']==state['max_energy']:
            raise ValueError('能量已经全满')
    result=deepcopy(state);c=result['combat'];_record(result,operation_id);c['exchange']=next_exchange
    gear_effects=_gear_effects(result)
    event={'id':uuid4().hex,'operation_id':operation_id,'action_id':action,'skill_id':skill_id,
           'encounter_id':c['id'],'monster_id':c['monster_id'],'story_turn':result['story_turn'],'exchange':next_exchange,
           'damage_to_enemy':0,'damage_to_player':0,'outcome':'ongoing'}
    if action=='retreat':
        summary='陆凌霄撤离战斗，没有获得战利品。'
        if c.get('monster_id')=='tower_100' and c.get('final_phase')=='awakened':
            ultra=base_stats('ULTRA',result['realm_index'],result['realm_stage'])
            ur=base_stats('UR',result['realm_index'],result['realm_stage'])
            result['ability_rank']='UR';result['max_hp']-=ultra[0]-ur[0]
            result['max_energy']-=ultra[1]-ur[1];result['base_attack']-=ultra[2]-ur[2]
            result['hp']=min(result['hp'],result['max_hp']);result['energy']=min(result['energy'],result['max_energy'])
            result['flags']['final_phase']='ready'
            summary+='战中觉醒尚未稳定，当前回到UR，可重新挑战并再次觉醒。'
        result['combat']=None;event.update(outcome='retreat',summary=summary);return result,event
    remaining=[]
    for effect in c['effects']:
        if effect['type'] in ('bleed','poison','burn'):
            protected=c.get('monster_id')=='tower_100' and c.get('final_phase')!='awakened'
            damage=min(max(0,c['hp']-int(protected)),effect['damage']);c['hp']-=damage;event['damage_to_enemy']+=damage
        effect['remaining']-=1
        if effect['remaining']>0:remaining.append(effect)
    c['effects']=remaining
    if c['hp']>0:
        attack=result['base_attack']+_gear_stat(result,'attack')
        if action=='attack':damage=attack
        elif action=='tactic':
            result['energy']-=proposal['energy_cost']
            damage=round(attack*proposal['multiplier'])
            if proposal['effect']=='weaken':c['weaken']=2;c['armor_break']=2
            event['player_intent']=proposal['intent']
            event['tactic_label']=proposal['label']
        elif action=='awaken':
            old=base_stats('UR',result['realm_index'],result['realm_stage'])
            new=base_stats('ULTRA',result['realm_index'],result['realm_stage']);result['ability_rank']='ULTRA'
            result['max_hp']+=new[0]-old[0];result['max_energy']+=new[1]-old[1]
            result['base_attack']+=new[2]-old[2];result['flags']['final_phase']='awakened'
            c['final_phase']='awakened';damage=0
        elif action=='skill':
            result['energy']-=skill['energy_cost'];c['cooldowns'][skill_id]=next_exchange+skill['cooldown']+1
            level=next((max(1,min(3,x.get('level',1))) for x in result['skills'] if x.get('catalog_id',x.get('id'))==skill_id),1)
            scale=1+.1*(level-1)
            effect=skill['effect'];damage=round(attack*skill['multiplier']*scale)
            if effect in ('bleed','poison','burn'):
                dot_multiplier=1.25 if effect=='burn' and 'burn_boost' in gear_effects else 1
                c['effects'].append({'type':effect,'damage':max(1,round(attack*.12*dot_multiplier*scale)),'remaining':2})
            elif effect=='shield':c['player_shield']=2+level-1
            elif effect=='heal':result['hp']=min(result['max_hp'],result['hp']+round(result['max_hp']*(.35+.05*(level-1))))
            elif effect=='energy_heal':
                event['health_cost']=max(1,round(result['max_hp']*.1));result['hp']-=event['health_cost']
                old_energy=result['energy']
                result['energy']=min(result['max_energy'],old_energy+max(1,round(result['max_energy']*(.25+.05*(level-1)))))
                event['energy_restored']=result['energy']-old_energy
            elif effect=='control':c['control']=1
            elif effect=='weaken':c['weaken']=2+level-1;c['armor_break']=2+level-1
            elif effect=='survival':c['anchor_used']=True;c['anchor_charges']=1
        else:damage=0
        if c.get('armor_break', 0) and damage>0:
            damage=round(damage*1.1);c['armor_break']-=1
        if action=='attack' and next_exchange%3==0 and 'thunder' in gear_effects:
            damage+=round(attack*.3)
        if c.get('enemy_shield', 0):
            if 'armor_break' in gear_effects:damage=round(damage*1.2)
            damage=round(damage*.65);c['enemy_shield']-=1
        if c.get('player_slow', 0) and not _wears(result,'gravity_boots'):
            damage=round(damage*.75);c['player_slow']-=1
        elif c.get('player_slow', 0):c['player_slow']=0
        protected=c.get('monster_id')=='tower_100' and c.get('final_phase')!='awakened'
        damage=min(max(0,c['hp']-int(protected)),max(0,damage));c['hp']-=damage;event['damage_to_enemy']+=damage
    if c['hp']<=0:
        xp=_victory(result,c)
        monster=MONSTERS[c['monster_id']]
        extra='获得精英制作材料与装备配方。' if monster.get('elite_material') else ''
        names='、'.join(ABILITIES[a]['name'] for a in dict.fromkeys(monster['abilities']))
        event.update(outcome='victory',xp_gained=xp,summary=f"击败{c['name']}，获得战利品与{xp}修炼经验。{extra}可融合残响：{names}（每个敌人选择一种）。")
        return result,event
    monster=MONSTERS[c['monster_id']];incoming=max(1,c['attack']-_gear_stat(result,'defense'))
    if action=='guard':incoming=max(1,incoming//3)
    if action=='guard' and 'bone' in gear_effects:incoming=max(1,round(incoming*.8))
    if 'trial_guard' in gear_effects and result['hp'] < result['max_hp']*.35:
        incoming=max(1,round(incoming*.9))
    if c.get('player_shield',0)>0:incoming=max(1,incoming//2);c['player_shield']-=1
    if c.get('weaken',0)>0:incoming=max(1,round(incoming*.8));c['weaken']-=1
    if _wears(result,'iron_king_chest'):incoming=max(1,round(incoming*.9))
    controlled=c.pop('control',0)
    if controlled:incoming=max(1,round(incoming*.8)) if monster['boss'] else 0
    remaining_player=[];dot=0
    for status in c.get('player_effects',[]):
        dot+=round(status['damage']*.7) if status['type']=='poison' and 'poison_resist' in gear_effects else status['damage'];status['remaining']-=1
        if status['remaining']>0:remaining_player.append(status)
    c['player_effects']=remaining_player
    if next_exchange%3==0 and (not controlled or monster['boss']):
        enemy_ability=monster['abilities'][0];effect=ABILITIES[enemy_ability]['effect']
        event['enemy_ability']=enemy_ability
        if effect in ('bleed','poison','burn'):
            c['player_effects'].append({'type':effect,'damage':max(1,round(c['attack']*.15)),'remaining':2})
        elif effect=='shield':c['enemy_shield']=1
        elif effect in ('weaken','control'):c['player_slow']=1
        elif effect=='damage':incoming=round(incoming*1.2)
        elif effect=='heal':c['hp']=min(c['max_hp'],c['hp']+round(c['max_hp']*.08))
        elif effect=='energy_heal':incoming=round(incoming*1.1)
    if incoming>0 and 'void' in gear_effects and not c.get('void_boots_used'):
        incoming=max(1,round(incoming*.5));c['void_boots_used']=True
    incoming+=dot
    if action=='guard' and 'mirror' in gear_effects:c['player_shield']=max(c.get('player_shield',0),1)
    damage=min(result['hp'],incoming);result['hp']-=damage
    if result['hp']==0 and c.get('anchor_charges',0)>0:
        result['hp']=1;c['anchor_charges']-=1
    elif result['hp']==0 and _wears(result,'time_amulet') and not c.get('time_amulet_used'):
        result['hp']=1;c['time_amulet_used']=True
    event['damage_to_player']=damage
    if result['hp']==0:event['outcome']='defeat';result['combat']=None
    event['summary']=f"第{next_exchange}次交锋：对{c['name']}造成{event['damage_to_enemy']}伤害，自身承受{damage}伤害。"
    if event.get('enemy_ability'):
        event['summary']+=f"{c['name']}发动{ABILITIES[event['enemy_ability']]['name']}。"
    if event.get('health_cost'):
        event['summary']+=f"转化消耗{event['health_cost']}生命，恢复{event['energy_restored']}能量。"
    if action=='awaken':event['summary']='战中领悟，陆凌霄突破至ULTRA；'+event['summary']
    return result,event


def auto_attack(state, operation_id, *, max_steps=10):
    """Resolve bounded basic exchanges; stop before critical health or finale awakening."""
    _check_operation(state, operation_id)
    if type(max_steps) is not int or not 1 <= max_steps <= 10:
        raise ValueError('连续攻击次数无效')
    if not state.get('combat'):
        raise ValueError('当前没有可继续的战斗')
    result = deepcopy(state); events = []
    for index in range(max_steps):
        if not result.get('combat'):
            break
        current = result['combat']
        dot = sum(x.get('damage', 0) for x in current.get('player_effects', []))
        danger = max(1, round(result['max_hp']*.35), round(current['attack']*1.5)+dot)
        if result['hp'] <= danger:
            break
        if current.get('monster_id') == 'tower_100' and current.get('final_phase') == 'suppression' and current.get('exchange', 0) >= 2:
            break
        result, event = combat_step(result, {'action': 'attack'}, f'{operation_id}:step:{index}')
        events.append(event)
    if not events:
        raise ValueError('生命过低或需要手动觉醒，请选择治疗、防御或其他行动')
    result['completed_operations'].append(operation_id)
    damage = sum(x.get('damage_to_enemy', 0) for x in events)
    received = sum(x.get('damage_to_player', 0) for x in events)
    event = {'id': uuid4().hex, 'operation_id': operation_id, 'action_id': 'auto_attack',
             'monster_id': state['combat']['monster_id'], 'story_turn': result['story_turn'],
             'exchange_count': len(events), 'damage_to_enemy': damage, 'damage_to_player': received,
             'outcome': events[-1]['outcome'], 'exchanges': events,
             'summary': f'连续普通攻击{len(events)}次，造成{damage}伤害，承受{received}伤害；遇到危险或觉醒节点会停止。'}
    return validate_state_v2(result), event
