"""人物、分支事实与视觉提示共享同一快照。"""
import json
import re
from .art_style import STYLE_DETAIL,STYLE_COMPACT,STYLE_NEGATIVE,STYLE_NONHUMAN
from .creative import direction
from .content_guard import SECRET_RULE,safe_history
from .progression import info as growth_info

PROMPT_VERSION='duhe-v6-private-growth'


def assert_story_event(text,event):
    if event.get('action_id') not in ('final_purify','epilogue') and ('人类文明存续判定' in text or 'civilization survival verdict' in text.lower()):
        raise ValueError('模型提前写入终局宣告，本回合未提交；请重新生成。')
    if event.get('action_id')=='absorb_core':
        depicted=re.search(r'吸收|炼化|absorb',text,re.I) or ('净核' in text and re.search(r'暖流|热流|融入|消融|化作|经脉',text))
        if not depicted:raise ValueError('正文遗漏本轮吸收净核动作，未提交状态，请重试。')
        rank=event.get('ability_rank_change',{}).get('to')
        if rank and not re.search(r'(?<![A-Za-z])'+re.escape(rank)+r'(?![A-Za-z])',text):raise ValueError('正文遗漏本轮异能升阶结果，未提交状态，请重试。')

def assert_story_language(text,locale):
    if locale=='en-US':
        chinese=len(re.findall(r'[\u4e00-\u9fff]',text))
        words=len(re.findall(r'\b[A-Za-z]{2,}\b',text))
        if words<25 or chinese>len(text)*.12:
            raise ValueError('模型未按英文要求输出，本回合未提交；请重新生成。')


def character_card(cid, state, scene):
    try:
        from .world import CHARACTERS, appearance_for
        c=CHARACTERS.get(cid,{})
    except ImportError:
        c={}
    details='；'.join(str(c.get(k,'')) for k in ('name','appearance','outfit','personality','goal','limits'))
    if cid=='protagonist':
        body={'underfed':'营养不足、瘦削、肩背紧绷，没有成熟肌肉', 'recovering':'恢复中的精瘦体格，前臂线条初显',
              'trained':'长期训练后的强健匀称体魄，肩背与四肢肌肉清楚', 'hardened':'久经战斗、肌肉强健、动作经济，保留旧伤'}.get(state.get('body_stage'),'瘦削')
        eyes='虹膜内有蓝色流光，瞳孔清晰，光不射出眼睛' if scene.get('combat_active') and scene.get('core_power_active') else '自然蓝瞳，不发光'
        outfit=scene.get('appearance_snapshots',{}).get(cid,{}).get('outfit')
        if not outfit:
            outfit=appearance_for(cid,state,scene)['outfit']
        strength=growth_info(state)['attack_bonus']
        reinforcement=f'异能强化提供{strength}点攻击加成，在当前体型内表现为肩背控制更稳、肌肉线条逐渐清晰，但不能跨越训练与恢复阶段。' if strength else ''
        return f'陆凌霄：26岁成年男性，黑发、蓝瞳，左眉尾短疤；{body}；{eyes}；服饰：{outfit}。伤势：{state.get("wounds",[])}。异能等级{state.get("ability_rank","UNRANKED")}。{reinforcement}经历受欺与苦难，通过训练磨练冷静，不凭空变强。'
    if cid=='heroine':
        hair='白色长发始终自然披散至腰际，轻薄碎刘海与脸侧长发束，不扎发'
        return f'沈霁月：25岁成年女性，白发、紫瞳，{hair}；灰白防护外套、深紫内衬、深色行动长裤、样本匣。异能{state.get("heroine_rank",state.get("heroine_ability_rank","SS"))}，霜月界域。实力强大、行动果断，内心温柔敏感，信任后才展现脆弱；有独立研究和行动，不因男主成长无故变弱。'
    return details or cid


def build_messages(state,event,history,language,scene,feedback=None):
    cast=[character_card(cid,state,scene) for cid in scene.get('present_character_ids',['protagonist'])]
    fields='mode chapter turn day realm_index realm_stage ability_rank ability_xp cores_absorbed hunter_rank hp max_hp xp energy pollution inventory equipment skills abilities flags tower_floor training_days body_stage wounds countdown heroine_rank combat skill_slots'.split()
    facts={k:state[k] for k in fields if k in state}
    facts['available_echo_count']=len(state.get('echoes',[]))-len(state.get('consumed_echoes',[]))
    from .catalog import ABILITIES
    from .combat import _known_skills
    facts['known_ability_ranks']={ABILITIES[key]['name']:ABILITIES[key]['rank'] for key in _known_skills(state)}
    facts['cleared_floor_count']=len(state.get('cleared_floors',[]))
    facts['known_facts']=state.get('known_facts',[])[-30:]
    facts['growth_rules']={'ability':growth_info(state),'absorb_cost':'1净核、8能量、污染+2，需污染<65；没有额外每日次数或冷却限制','cultivation':'经验足够仍需本阶段独行试炼和净核材料'}
    from .affinity import scores,narrative_context
    affinity_scores=scores(state)
    facts['relationships']={k:{'trust':v.get('trust'),'affinity':affinity_scores.get(k),'events':v.get('events',[])[-6:]} for k,v in state.get('relationships',{}).items() if isinstance(v,dict)}
    relations=narrative_context(state)
    heroine_available=('heroine' in scene.get('present_character_ids',[]) or event.get('cast_focus',{}).get('character_id')=='heroine'
                      or (event.get('free_story') and any(x in event.get('player_intent','') for x in ('沈霁月','女主'))))
    romance_budget=1 if affinity_scores['heroine']>=60 and heroine_available and not state.get('combat') else 0
    try:
        from .world import REALMS
        facts['current_realm_name']=REALMS[state.get('realm_index',0)]
    except ImportError:pass
    older=[{'node':n.get('id'),'event':n.get('event')} for n in history[:-4]]
    # 账本保存权威事实；最近事件摘要控制输入，原文完整留在数据库。
    summary=json.dumps(older[-16:],ensure_ascii=False)[-4000:]
    recent=[{'role':'assistant','content':safe_history(n.get('text',''))[-1800:]} for n in history[-4:] if n.get('text')]
    language_rule='使用中文正文。' if language=='zh-CN' else 'Write the narrative in English. Keep names Lu Lingxiao and Shen Jiyue consistent. Explain cultivation terms briefly on first use.'
    intent_rule=('player_intent是玩家实际想尝试的自由行动原文，请直接生成这次行动的过程与叙事后果；它不需要匹配任何行动清单，不是已经实现的结果。' if event.get('free_story') else 'player_intent是本回合动作方式的创作意图，仅在已结算动作范围内细化，不能增加额外行动与奖励。')
    settlement_rule=('当前数值属性与关键主线进度以状态记录为准；本次自由行动的局部叙事过程与后果由你创作并在正文中落实，不必等待程序预先描述结果。不得自行发放数值奖励、改变等级或跳过关键节点条件。' if event.get('free_story') else '严格依据本回合程序结算，不自行升级、获得装备、回血、改变人物等级或推进楼层；结算中未发生的动作只可作为后续可能性。')
    scene_rule=('场景记录是行动开始时的位置与人物，不是在场人物白名单。自由行动可以搜索、追踪、移动、寻找并合理遇见人物，也可以未找到而发现线索；根据已有情节决定具体结果，不保证用户要求的目标必定实现。新人物入场时保持人物卡，不提前揭露尚未出现的主线秘密。' if event.get('free_story') else '只写当前场景出场人物和已揭露情报，不提前揭秘终焉母核或人类反派；不要把系统内核当成可被任何配角直接读到的秘密。')
    system=f'''你是《独核通天》的互动小说叙述者。{language_rule}
主线为陆凌霄从低于F-的弱小觉醒者，通过训练、系统、战斗与抉择成长，最终阻止文明收割。
玩家操纵的主角始终是陆凌霄。{intent_rule}女主无论战斗或休息均保持白色及腰披发，不扎马尾。
{settlement_rule}
固定异能顺序F-、E、D、C、B、A、S、SS、SSS、UR、ULTRA；UNRANKED表示低于F-；异能与修炼境界、地下城等级不同。并非人人觉醒。
首次相遇：SS级沈霁月救下被魔兽追杀的弱小陆凌霄。救援不是男主击杀，不给他该怪掉落或能力。系统之后才有净化、进化和能力残响融合。
{scene_rule}
刻画行动、对话、气氛与选择的代价，每回合约350—550中文字符或180—260英文词；开篇直接进入场景，不重复用户指令，不输出JSON。
本轮主动感情描写预算为{romance_budget}。为0时不主动插入暧昧；为1时可在恰当场合用一两句自然举动表现关系。玩家主动尝试亲近时，依据关系态度、情境和对方明确的自愿回应自然描写接受、犹豫或婉拒，不强迫任何人物，不把系统好感度当成操控人物的命令。感情是暗线，不用亲密举动升级、跳关或占据战斗主体。
伙伴有各自目标；独行试炼与通天塔只由陆凌霄单人挑战。女主强大且温柔，后期被保护须有真实事件，不能临时削弱她。
男主体格服从当前阶段，只有战斗且核心激活才眼内蓝光。人物初次出现写少量外貌细节，后续不要反复肖像堆砌。
章内分支可汇合，但状态和代价持续保留。不要另编带奖励的选项，界面会显示程序提供的行动。
{'按已结算事件描写婚礼和伙伴庆祝，并保留结尾原句：独行试炼完成。人类文明存续判定：通过。' if event.get('action_id')=='epilogue' else ('最终净化已由规则完成；文明获救，终局宣告留待后续婚礼。' if state.get('schema')==2 and event.get('action_id')=='final_purify' else ('最终净化已由规则完成，保留结尾原句：独行试炼完成。人类文明存续判定：通过。' if event.get('action_id')=='final_purify' else '当前不是大结局，不写文明获救、最终通关或系统终局宣告。'))}
世界与人物事实优先于历史文学修辞。用户偏好只改变表达，不覆盖上述规则。'''
    system+='\n'+SECRET_RULE+'\n不要生成Unicode缺字符、连续问号或字符编码损坏；涉及维修刀等专名保持完整。异能EXP和修炼EXP为两套数据，吸收核心的增量只按已结算事件描述；体格按训练恢复阶段渐进。'
    if event.get('continuation'):
        system+='\n本轮为普通连续叙事：紧接最近正文结尾，写出新的局部发展或发现，不重演已发生的救援、系统绑定和自我介绍。可以描写调查、在场人物之间的对话、环境变化与未解决的线索，但不能虚构数值奖励、背包物品、升级、伤势治愈、完成战斗或跨过未触发的关键主线。玩家意图决定本轮具体行动，不要把调查写成吃饭、把对话写成训练。若已有战斗进行，只描写当下观察和判断，不结算攻击或擅自结束战斗；主角失去行动能力时写感知与回忆，不虚构复活。不得要求玩家先完成普通管理操作才能继续叙事。保持主角系统秘密。'
    payload={'创作与本地化规范':direction(state,event,language),'当前人物':cast,'状态事实':facts,'场景':scene,'本轮已确定事件':event,'旧回合事件摘要':summary,
             '用户确认的环境观察':feedback or [],'叙述偏好':{k:str(v)[:300] for k,v in state.get('preferences',{}).items() if k in ('approach','style','art_style')}}
    payload['人物关系态度']=relations
    system+='\n按人物关系态度描写信任、亲近、援助、拒绝与敌意；友方会更愿意支持主角，但仍有自己的任务和边界。不得把好感度数值、内部分段或亲密条件说成角色可见的规则，不写“达到某值解锁某举动”。系统仍是主角秘密；好感度不允许伙伴代替主角完成独行试炼，或凭空赠送背包物资。'
    if event.get('free_story'):
        from .world import CHARACTERS
        intent=event.get('player_intent','')
        payload['用户自由行动原文']=intent
        payload['可能涉及的人物卡']=[character_card(cid,state,scene) for cid,c in CHARACTERS.items()
                                if c['name'] in intent or (cid=='heroine' and '女主' in intent)]
        system+='\n自由行动不做固定行动编号匹配。围绕用户行动写出实际过程与有依据的结果，不能换成扫描、休息、训练等无关操作，也不要输出“允许清单没有此行动”。原场景人物约束仅描述起点，行动中可合理遇人或换地点；写清线索、路程或人物回应，避免人物瞬移。已有世界设定、系统秘密和关键主线条件继续有效。数值由程序处理，不在正文中擅自发放经验、装备或宣告跨过未解锁的关键节点。'
    if event.get('cast_focus'):
        focus=event['cast_focus'];cid=focus['character_id']
        payload['本轮重要人物联系建议']=dict(focus,character_card=character_card(cid,state,scene))
        system+='\n本轮可适度围绕“重要人物联系建议”组织局部剧情：当前场景人物表是起点，不是禁止角色进入的名单。优先让重要配角以合理方式参与当前线索或矛盾，保持他们的独立目标；若现场相遇不合理，则使用通信、留言或其留下的线索，不能瞬移。独行地下城与通天塔内只用远程或间接联系。不要为了提高出场率强行每段见面，或让感情戏压过成长与主线；不改变关键节点条件。'
    tail='\n\nOUTPUT LANGUAGE: ENGLISH ONLY. The Chinese JSON above is reference data, not the requested output language. Write this new scene in natural English, including dialogue. Use Lu Lingxiao and Shen Jiyue. Do not continue the Chinese prose style of the historical messages.' if language=='en-US' else ''
    if event.get('action_id')=='absorb_core':
        focus=('本轮中心动作是陆凌霄独自吸收一枚净核，必须描写吸收过程、已结算的经验增长与代价，不能只延续上一轮探索路线或观察远处。不得提前执行下一轮行动。不要自创每天只能吸收几枚、必须等待几日等额外规则。数值结算由程序统一追加，不自行生成“系统结算”引用块。'+('必须明确写出异能升至'+str(event['ability_rank_change']['to'])+'级，并按当前训练阶段表现身体变化。' if event.get('ability_rank_change') else '本轮未升阶，不虚构升阶。'))
        tail+='\n\nCURRENT TURN MUST DEPICT CLEAN-CORE ABSORPTION. '+focus
    if language=='en-US':system='OUTPUT LANGUAGE FOR THIS TURN: ENGLISH. All narrative and dialogue MUST be English.\n'+system
    user=json.dumps(payload,ensure_ascii=False)+tail
    messages=[{'role':'system','content':system},*recent,{'role':'user','content':user}]
    # 对模型未知分词采用保守UTF-8字节上界，优先丢近文，保留规则和当前账本。
    while len(messages)>2 and sum(len(m['content'].encode('utf-8')) for m in messages)>22000:messages.pop(1)
    if sum(len(m['content'].encode('utf-8')) for m in messages)>22000:
        payload['旧回合事件摘要']=summary[-1000:]
        messages[-1]['content']=json.dumps(payload,ensure_ascii=False)+tail
    if sum(len(m['content'].encode('utf-8')) for m in messages)>22000:
        raise ValueError('当前上下文超过保守输入预算，请减少自定义资料或修订过长事实。')
    return messages


def visual_messages(node,scene):
    return [{'role':'system','content':'''将故事转换为单幅画面，输出json对象，字段character_ids（画面主要人物ID数组）、description（中文单个瞬间环境与动作）、lighting、composition。示例：{"character_ids":["protagonist"],"description":"废墟走廊里观察远方敌人","lighting":"冷色天光","composition":"中景"}。只使用允许出场人物，至多3人；不要把先后发生的动作拼成一张图，不添加奖励或未出现角色。人物外貌由程序另行注入。'''},
            {'role':'user','content':json.dumps({'story':node['text'],'scene':scene,'appearance_override':'沈霁月始终为白色及腰披散长直发，不扎发、不编辫；旧故事中的其他发型以此条覆盖。'},ensure_ascii=False)}]


def validate_visual(data,scene):
    if not isinstance(data,dict):raise ValueError('视觉说明不是对象')
    ids=data.get('character_ids')
    if not isinstance(ids,list) or len(ids)>3 or any(not isinstance(i,str) or i not in scene.get('present_character_ids',[]) for i in ids):raise ValueError('视觉说明出现未出场人物')
    if not isinstance(data.get('description'),str) or not data['description'].strip():raise ValueError('视觉描述为空')
    from .world import CHARACTERS
    description=' '.join(str(data.get(k,'')) for k in ('description','composition','lighting'))
    for cid,card in CHARACTERS.items():
        if cid not in ids and card['name'] in description:
            raise ValueError('视觉描述与人物ID不一致，请重新生成视觉说明')
    return {k:data.get(k,'') for k in ('character_ids','description','lighting','composition')}


def image_prompt(data,state,scene,limit=1900):
    # Composition comes from the visual plan; hardcoded left/right used to conflict with it.
    positions=['画面角色一','画面角色二','画面角色三']
    cast=[f'{positions[i]}：{character_card(cid,state,scene)}' for i,cid in enumerate(data['character_ids'])]
    style=STYLE_COMPACT if limit<=500 else STYLE_DETAIL
    if 'boss' in data['character_ids']:
        style=STYLE_NONHUMAN
        cast=[f'{positions[i]}：'+('巨大无脸无毛发的核心聚合装置，中央球形惨白核光，多层黑曜分节甲壳与悬浮同心圆环，紫黑裂隙、断裂管线和碎核冠；主体没有人形躯干、头颅或四肢' if cid=='boss' else character_card(cid,state,scene)) for i,cid in enumerate(data['character_ids'])]
    if limit<=500:
        cast=[part.split('。')[0][:150] for part in cast]
    monster=scene.get('monster') or {}
    scale=(f"魔物{monster.get('name')}：{monster.get('description')}。{monster.get('scale_instruction')}" if monster and monster.get('id')!='tower_100' else '')
    visual_description=str(data['description'])[:450]
    composition=str(data.get('composition',''))[:70]
    if monster.get('id')=='polluted_beetle':
        scale=('巨型甲虫是画面主体，与成年男子并排站在同一地面：甲虫身体从头到尾长约三米，'
               '明显长于成年男子身高；背甲顶部高及成年男子胸口，粗壮长颚、六条粗壮节肢和厚重背甲。'
               '甲虫占画面宽度的至少一半，以人物全身为尺寸参照，近距离低机位构图。')
        visual_description='成年男子在废墟中持维修刀，与巨型甲虫近距离对峙。'
        composition='同一地面的人物全身与巨型甲虫并排，甲虫占据画面主体'
    elif monster.get('id')=='tower_100':
        scale=('巨大悬浮圆球形机械核心阵列占据画面主体：中央发光球体嵌在层叠同心圆环与几何装甲之中，'
               '周围仅有悬浮碎核和短管线；形态如漂浮的天文仪器，绝无头部、躯干、肩膀、手臂和腿。')
        visual_description='一名成年男子在塔顶平台面对远处巨大的球形核心阵列。'
        composition='广角全景，球形核心阵列占据画面大部分，人物作为尺寸参照'
    prompt='。'.join(part for part in [scale,style,*cast,visual_description,str(data.get('lighting',''))[:70],composition] if part)
    negative='文字，字幕，水印，重复人物，多余肢体，人物发色瞳色互换，眼睛发射激光，无来源装备，体格超前，色情，血腥特写，脸颊叉形疤痕'
    if 'heroine' in data['character_ids']:negative+='，马尾，编辫，扎发'
    if monster.get('id')=='polluted_beetle':negative+='，小昆虫，手掌大小，宠物甲虫，玩具甲虫，甲虫比人物小'
    if 'boss' in data['character_ids']:negative+='，人形母皇，女性母皇，长发怪物，人脸怪物，人形躯干，怪物四肢'
    return prompt[:limit],negative+'，'+STYLE_NEGATIVE
