"""Bounded author preferences and bilingual terminology; no rule transitions."""
TEMPLATES={
    'rescue':('救援','Rescue','以追逐中的空间、呼吸与救援动作建立紧迫感；救援者保有实力，获救者不抢占击杀。'),
    'exploration':('探索','Exploration','围绕可观察线索、地形与未知威胁展开，不把猜测写成已经揭露的真相。'),
    'combat':('战斗','Combat','明确双方位置、意图与本回合一次交锋，强调判断、动作和已结算代价，不提前宣布胜利。'),
    'breakthrough':('突破','Breakthrough','表现训练与资源积累后的身体感受、风险与克制的成就感，不跳过规则要求。'),
    'dialogue':('交谈','Dialogue','用简短对话、停顿与具体行动呈现动机差异；关系仅随已发生事件发展。'),
}
TERMS={
    '陆凌霄':'Lu Lingxiao','沈霁月':'Shen Jiyue','周野':'Zhou Ye','顾砺山':'Gu Lishan',
    '闻峥':'Wen Zheng','裴景珩':'Pei Jingheng','谢玄策':'Xie Xuance',
    '淬体':'Body Tempering','开脉':'Meridian Opening','凝核':'Core Formation','化罡':'Aura Manifestation',
    '通幽':'Veil Perception','法相':'Avatar Manifestation','涅槃':'Rebirth','天劫':'Heavenly Trial',
    '超凡':'Transcendence','神话':'Mythic Unity','命核':'Life Core','污染':'Contamination',
    '通天塔':'Skyreach Tower','独行进化系统':'Solo Evolution System',
    '噬核母皇·终焉之核':'Core-Devouring Matriarch — the Final Core',
}


def template_for(state,event):
    selected=state.get('preferences',{}).get('scene_template','auto')
    if selected in TEMPLATES:return selected
    action=event.get('action_id','')
    if action=='opening':return 'rescue'
    if state.get('combat') or action in ('attack','guard','skill','retreat','wall_defend','final_purify'):return 'combat'
    if action in ('breakthrough','heroine_sss','heroine_ur','train','absorb_core') or action.startswith('absorb:'):return 'breakthrough'
    if action.startswith('rival_') or action in ('reject_harvest','rest'):return 'dialogue'
    return 'exploration'


def direction(state,event,language):
    p=state.get('preferences',{});key=template_for(state,event)
    perspective='以陆凌霄第一人称“我”叙述；英文用I。' if p.get('perspective','first')=='first' else '以陆凌霄为中心的第三人称有限视角，不读取未出场人物内心。'
    content='战斗不描写血腥解剖或细密伤口，以动作、疼痛和后果表达危险。' if p.get('content_level','restrained')=='restrained' else '可简洁描述战斗伤势，但不渲染血腥细节。'
    locale='英文首次出现修炼专名时用自然短语解释，不套用现实文化刻板印象；对话保留人物动机而非逐字翻译。' if language=='en-US' else '使用自然中文，以具体行动表达尊重与亲疏，避免堆砌网络套话和文化刻板印象。'
    return {'template_id':key,'template':TEMPLATES[key][2]+' 模板只改变表达，不能引入未结算事件。','perspective':perspective,'content':content,'localization':locale,'glossary':TERMS if language=='en-US' else {}}
