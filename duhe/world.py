"""Canonical scene facts; no provider calls and no hidden state changes."""
from __future__ import annotations

REALMS = ['淬体','开脉','凝核','化罡','通幽','法相','涅槃','天劫','超凡','神话']
ABILITY_RANKS = ['F-','E','D','C','B','A','S','SS','SSS','UR','ULTRA']

CHARACTERS = {
 'protagonist':dict(name='陆凌霄', appearance='26岁，黑色短发、自然蓝色虹膜，左眉尾短疤，手有维修薄茧。', outfit='褪色炭灰维修夹克、深色工装裤、旧作业靴。', personality='起初怕痛与退让，通过训练学会冷静，容易隐瞒伤势。', goal='不再任人决定生死，寻找失散家人，阻止文明收割。', limits='需要训练、营养和恢复；独行试炼不能由伙伴代打。'),
 'heroine':dict(name='沈霁月', appearance='25岁，白色披发长至腰、轻薄刘海、脸侧长发束，紫瞳，右眼下浅痣，身形修长。', outfit='灰白短防护外套、深紫高领内衬、石墨长裤，左腰样本匣。', personality='外强内温柔敏感，条理清晰、边界分明，向信任的同伴展现脆弱，关心表达克制。', goal='查清研究组覆灭，找到不牺牲普通人的核心净化方法。', limits='封印有距离、时间和身体负担，不能无限恢复主角或替代其关键战斗。'),
 'friend':dict(name='周野', appearance='27岁，栗棕短发、琥珀眼，鼻梁雀斑，左侧酒窝，肩宽手粗。', outfit='土黄旧飞行夹克、墨绿围巾、深棕工装裤、额头护目镜。', personality='嘴碎务实、讲义气，容易接下过多运输委托。', goal='维持贫民也负担得起的物资路线。', limits='补给依赖实际运输库存，不能无限送资源，尊重主角独行。'),
 'mentor':dict(name='顾砺山', appearance='52岁，铁灰寸发、深褐眼，左前臂钢制作业义肢，颈手烧伤。', outfit='深棕皮围裙、卷袖黑衬衣、沉重作业靴。', personality='刻薄认真，以动作与装备承载评价人，旧创使他过于谨慎。', goal='传下可靠锻造方法，避免年轻人重蹈试炼覆辙。', limits='材料和打造有代价，不赠神器，不知系统全部秘密。'),
 'commander':dict(name='闻峥', appearance='36岁，深棕短发、灰褐眼，左颧骨旧伤，站姿笔直。', outfit='暗橄榄制服、灰色胸甲、左肩红识别带、旧信号枪。', personality='言简意赅、守纪律，尊重有证据的方案，也会承担判断错误。', goal='守住北墙供能和普通人的撤离通道。', limits='受兵力和整体防守约束，不能亲自完成所有救援。'),
 'rival':dict(name='裴景珩', appearance='29岁，深金整齐短发、灰绿眼，右手家族纹章戒。', outfit='象牙白黑金战斗长衣，整洁财阀制式装甲。', personality='彬彬有礼却以等级衡量人，害怕被家族替代，失败后调整策略。', goal='证明自己有资格掌握核心配额。', limits='只知财阀情报，不能无故知道独行系统；未有选择不突然洗白。'),
 'antagonist':dict(name='谢玄策', appearance='47岁，黑发夹灰白束、深灰眼、右颈暗金接口纹。', outfit='深石墨长外套、立领内衬、黑薄手套、小型几何徽章。', personality='耐心讲逻辑，坚信牺牲少数可以延续文明。', goal='以部分要塞生命换取可控生存区。', limits='只知部分收割机制，判断可以出错，不取代百层最终敌人。'),
 'boss':dict(name='噬核母皇·终焉之核', appearance='非人类聚合生命，巨大黑曜分节甲壳、同心核心环、紫黑裂隙与惨白核光。', outfit='断裂管线和碎核形成的不对称冠状结构。', personality='通过核心网络复制与收割，维持自身机制。', goal='收割文明的命核并延续污染网络。', limits='仅终局现身，反向净化形态必须由真实终局事件触发，不是白发紫瞳人类女性。'),
}

BODY_DESCRIPTIONS = {'underfed':'瘦削、肩背紧、耐力差，旧伤影响动作', 'recovering':'规律训练恢复后站姿渐稳，前臂背部线条初显', 'trained':'长期训练后肩背宽厚，肌肉匀称，动作稳定', 'hardened':'久经战斗、强健结实，动作经济，保留人类比例与伤痕'}


def appearance_for(character_id, state, scene=None):
    card = CHARACTERS[character_id]
    scene = scene or scene_for(state)
    result = dict(card)
    result['character_id'] = character_id
    result['eye_glow'] = bool(character_id == 'protagonist' and scene.get('combat_active') and scene.get('core_power_active'))
    if character_id == 'protagonist':
        result['body_stage'] = state.get('body_stage','underfed')
        result['body'] = BODY_DESCRIPTIONS[result['body_stage']]
        equipment = state.get('equipment', {})
        values = equipment.values() if isinstance(equipment,dict) else equipment
        if 'black_iron_armor' in values:
            result['outfit'] = '已锻造的哑黑分片黑铁核心护甲、暗蓝能量槽，黑灰工装。'
        result['appearance'] += '眼内蓝色流光，瞳孔清晰，无眼部激光。' if result['eye_glow'] else '蓝瞳自然，不发光。'
    if character_id == 'heroine':
        result['hairstyle'] = 'loose'
        result['appearance'] += '白色长发始终披散至腰，不扎发，轻薄刘海与脸侧长发束。'
    return result


def scene_for(state, events=None):
    chapter = state.get('chapter',1)
    last = state.get('last_action','opening')
    flags = state.get('flags',{})
    combat = last in ('attack','guard','skill') or bool(state.get('combat'))
    cast = ['protagonist']
    locations = {1:'外环废墟',2:'要塞训练营',3:'北墙防线',4:'高阶地下城',5:'北墙决战',6:'通天塔',7:'终焉母核'}
    if chapter < 6:
        if not (state.get('system_bound') or flags.get('system_bound')) or last in ('opening','rescue','bind_system','purify','research','heroine_sss','heroine_ur'):
            cast.append('heroine')
        elif last == 'craft': cast.append('mentor')
        elif last == 'rest': cast.append('friend')
        elif last == 'wall_defend': cast.append('commander')
    story_node='rival' if last in ('rival_refuse','rival_trade') else 'harvest' if last=='reject_harvest' else None
    if story_node:
        cast=['protagonist','rival' if story_node=='rival' else 'antagonist']
    if state.get('combat',{} ) and state['combat'].get('floor')==100: cast.append('boss')
    romance = 1 if state.get('romance_event',False) and 'heroine' in cast and not combat else 0
    scene = dict(scene_id=f"ch{chapter}-turn{state.get('turn',0)}", location=locations.get(chapter,'要塞'), present_character_ids=cast, combat_active=combat, core_power_active=combat and last in ('skill','attack') and bool(state.get('system_bound') or flags.get('system_bound')), main_action=state.get('last_event','在危险中判断下一步行动'), romance_budget=romance, heroine_hairstyle='loose', known_facts=list(state.get('known_facts',[])))
    if story_node:
        scene['location']='要塞物资交涉站' if story_node=='rival' else '要塞临时议事厅'
    scene['appearance_snapshots'] = {cid:appearance_for(cid,state,scene) for cid in cast}
    return scene
