"""Read-only, branch-local view data for the v2 interface."""
from html import escape
from copy import deepcopy
from .campaign import available_milestones
from .catalog import MONSTERS, ABILITIES, EQUIPMENT, codex_entries, ABILITY_RANKS
from .combat import RANKS, _known_skills
from .equipment import equipment_stats, SLOTS
from .models_v2 import validate_state_v2
from .progression import info
from .progression_v2 import growth_cost
from .world import REALMS
from .status_panel import icon
from .player_labels import format_stats, format_recipe, material_name, SLOTS as PLAYER_SLOTS, SLOTS_EN, ability_rank_label,ability_label,monster_kind

ITEMS = {'food': ('🥫', '食物', '休整、训练和排毒使用。'),
         'raw_core': ('🔴', '原核', '可在核心熔炉中净化，消耗能量并产生污染。'),
         'clean_core': ('🔷', '净核', '可吸收、突破、打造或用于研究。'),
         'material': ('⚙️', '通用材料', '从战利品取得，用于打造装备。')}
ITEMS.update({'iron_king_fragment': ('💠', '铁脊王碎片', '第十层守卫的特殊材料，可用于打造铁脊王甲。'),
              'gravity_fragment': ('💠', '重力法则碎片', '高层守卫掉落的材料，可用于打造折域战靴。'),
              'time_fragment': ('💠', '时间法则碎片', '高层守卫掉落的材料，可用于打造时隙锚饰。')})
ITEMS.update({'elite_iron_shell': ('🪨', '精英铁甲片', '重甲精英甲虫掉落，用于打造铁骨基础装备。'),
              'elite_tough_hide': ('🧵', '精英韧皮', '裂爪精英掉落，用于打造强化猎人装备。'),
              'elite_conductive_crystal': ('💎', '导能晶骨', '雷脊精英掉落，用于打造精炼核心装备。')})
for _item in EQUIPMENT.values():
    if _item.get('unlock_material_name'):
        ITEMS[_item['unlock_material']] = ('💠', _item['unlock_material_name'], '首领掉落的核心装备材料。')
SLOT_LABELS = dict(zip(SLOTS, ('⚔️ 武器', '🪖 头部', '🛡️ 胸甲', '🧤 手部', '👖 腿部', '👢 足部', '💍 饰品')))


def available_actions(state):
    validate_state_v2(state)
    groups = {'story': [], 'ordinary': [], 'battle': [], 'combat': []}
    from .story_flow import continuation_actions
    from .ordinary_v2 import ordinary_options
    groups['story'].extend(continuation_actions(state))
    if not state.get('flags',{}).get('victory'):groups['ordinary'].extend(ordinary_options(state))
    if state['hp'] <= 0 or state.get('flags', {}).get('victory'):
        return groups
    if not state['flags'].get('system_bound'):
        groups['story'].append({'id': 'opening', 'label': '初遇：接受沈霁月救援并绑定系统'})
        return groups
    if state.get('combat'):
        if state.get('legacy_battle_requires_old_rules'):
            return groups
        groups['combat'] = [{'id': 'attack', 'label': '普通攻击'}, {'id': 'auto_attack', 'label': '连续普通攻击（危险时停止）'}, {'id': 'guard', 'label': '防御'},
                            {'id': 'retreat', 'label': '撤离'}]
        if state['combat'].get('monster_id') == 'tower_100' and state['combat'].get('exchange', 0) >= 2 and state['ability_rank'] == 'UR':
            groups['combat'].append({'id': 'awaken', 'label': '临场悟道：突破ULTRA'})
        return groups
    costs={'heroine_sss':5,'heroine_ur':8}
    groups['story'].extend(x for x in available_milestones(state)
                           if state['inventory'].get('clean_core',0)>=costs.get(x['id'],0))
    flags = state['flags']
    if flags.get('wall_saved') and not flags.get('boss_defeated'):
        floor = state.get('tower_floor', 0)
        if not floor or floor % 10:
            groups['story'].append({'id': 'tower_segment', 'label': '攻略通天塔普通楼层'})
    if flags.get('final_phase') == 'purification':
        groups['story'].append({'id': 'final_purify', 'label': '反向净化终焉母核'})
    if flags.get('final_phase') == 'epilogue_ready':
        groups['story'].append({'id': 'epilogue', 'label': '文明存续：迎来结局'})
    inventory = state['inventory']; food = inventory.get('food', 0)
    defeated=set(state.get('bestiary',{}).get('defeated_bosses',[])); unlocked=set(state.get('unlocked_recipes',[]))
    if any(item.get('special_effect') and item.get('boss_id') in defeated and item['id'] not in unlocked
           and (not item.get('unlock_after_purification') or state.get('flags',{}).get('civilization_saved')) for item in EQUIPMENT.values()):
        groups['ordinary'].append({'id':'claim_legacy_boss_rewards','label':'补领已击败首领的新增装备材料'})
    step=state['realm_index']*3+state['realm_stage']
    trial_ok = state['realm_stage'] != 2 or flags.get('trials_v2', {}).get(str(state['realm_index']))
    if step < 29 and trial_ok and state['xp'] >= growth_cost(step) and inventory.get('clean_core',0):
        groups['ordinary'].append({'id': 'breakthrough', 'label': '境界突破'})
    rank = state['ability_rank'] if state['ability_rank'] != 'UNRANKED' else 'F-'
    for mid, monster in MONSTERS.items():
        if (not monster['boss'] and RANKS.index(monster['rank']) <= RANKS.index(rank)):
            groups['battle'].append({'id': mid, 'label': '【'+monster_kind(monster)+'】'+monster['name'] + ' · ' + monster['rank']+'级'})
    for mid in flags.get('unlocked_bosses', []):
        if mid in MONSTERS and mid not in state.get('bestiary', {}).get('defeated_bosses', []):
            monster = MONSTERS[mid]
            if not monster.get('floor') or monster['floor'] == state.get('tower_floor'):
                groups['battle'].append({'id': mid, 'label': '【BOSS】' + monster['name']+' · '+monster['rank']+'级'})
    if state['realm_stage'] == 2 and not flags.get('trials_v2', {}).get(str(state['realm_index'])):
        groups['battle'].append({'id': 'realm_trial', 'label': '本境界独行试炼 · BOSS'})
    return groups


def render_system(state, en=False):
    validate_state_v2(state)
    stats = equipment_stats(state)
    growth = info(state)
    realm = REALMS[state['realm_index']] + '境·' + ('初期', '中期', '后期')[state['realm_stage']]
    def card(kind, label, value, description, current=None, maximum=None):
        gauge = (f'<progress value="{current}" max="{maximum}"></progress>'
                 if current is not None and maximum else '')
        return (f'<details class="status-card"><summary><span class="status-label">{icon(kind)}'
                f'{escape(label)}</span><strong>{escape(str(value))}</strong>{gauge}'
                f'<span class="status-more">点击查看说明</span></summary><p>{escape(description)}</p></details>')
    cost=growth_cost(state['realm_index']*3+state['realm_stage'])
    if en:
        from .i18n_v2 import REALMS_EN
        realm_en = REALMS_EN[state['realm_index']] + ' · ' + ('early', 'middle', 'late')[state['realm_stage']]
        cards = [
            card('hp','Health',f"{state['hp']}/{state['max_hp']}",'Zero health ends the battle. One rest restores 35% of maximum health.',state['hp'],state['max_hp']),
            card('energy','Core energy',f"{state['energy']}/{state['max_energy']}",'Purifying or absorbing each core costs 8 energy. One rest restores 45% of maximum energy.',state['energy'],state['max_energy']),
            card('pollution','Contamination',f"{state['pollution']}/100",'At 65, absorption and echo fusion stop; at 95, raw-core purification stops. Detox costs food and energy.',state['pollution'],100),
            card('ability','Ability '+('Below F-' if state['ability_rank']=='UNRANKED' else state['ability_rank']),f"{growth['current']}/{growth['required'] or 'MAX'}",'Absorb clean cores to gain ability XP. Low-grade cores give less XP at higher ranks. ULTRA awakens in the finale.',growth['current'],growth['required']),
            card('xp','Cultivation XP',f"{state['xp']}/{cost}",'Advancement requires XP and a clean core; changing realm also requires a solo trial.',min(state['xp'],cost),cost),
            card('realm','Cultivation',realm_en,'Each of ten realms has three stages. Training and recovery gradually improve physique.')]
        meta=f"Attack {stats['attack']} · Defense {stats['defense']} · Story turn {state['story_turn']} · Operations {state['operation_seq']} · Floor {state['tower_floor']}/100"
        return '<section class="player-status"><h2>Lu Lingxiao · System</h2><div class="status-grid">'+''.join(cards)+'</div><p class="status-meta">'+escape(meta)+'</p></section>'
    cards=[
        card('hp','生命',f"{state['hp']}/{state['max_hp']}",'生命归零会结束本次战斗；可以回档。每次进食休整恢复最大生命的35%，升级上限不会自动回复。',state['hp'],state['max_hp']),
        card('energy','核心能量',f"{state['energy']}/{state['max_energy']}",'净化和吸收每颗消耗8能量；能力按各自说明消耗。每次休整恢复最大能量的45%。',state['energy'],state['max_energy']),
        card('pollution','污染',f"{state['pollution']}/100",'污染达到65不能继续吸收净核或融合，达到95不能继续净化原核。排毒消耗2食物、20能量，降低15污染。',state['pollution'],100),
        card('ability','异能 '+('低于F-' if state['ability_rank']=='UNRANKED' else state['ability_rank']),f"{growth['current']}/{growth['required'] or 'MAX'}",'异能经验由吸收净核获得；低阶核心对高阶角色收益递减。UR之后需要在终战中觉醒ULTRA。',growth['current'],growth['required']),
        card('xp','修炼经验',f"{state['xp']}/{cost}",'修炼经验与异能经验分开计算；每次突破需要经验和净核，跨大境界还要完成独行试炼。',min(state['xp'],cost),cost),
        card('realm','境界',realm,'十个大境界各有初、中、后三阶段。体格随训练和恢复逐渐变化，不会只因升级立即变壮。')]
    meta=(f"攻击 {stats['attack']} · 防御 {stats['defense']} · 剧情回合 {state['story_turn']} · "
          f"操作记录 {state['operation_seq']} · 塔层 {state['tower_floor']}/100")
    return '<section class="player-status"><h2>陆凌霄 · 系统</h2><div class="status-grid">'+''.join(cards)+'</div><p class="status-meta">'+escape(meta)+'</p></section>'


def render_inventory(state, en=False):
    validate_state_v2(state)
    lines = ['## 🎒 Inventory' if en else '## 🎒 背包']
    for key, amount in state['inventory'].items():
        icon, label, desc = ITEMS.get(key, ('💠', material_name(key), '用于对应装备的制作。'))
        if en:
            from .i18n_v2 import TERMS_EN
            label, desc = TERMS_EN.get(key, (key.replace('_', ' ').title(), 'Boss material used in crafting.'))
        lines.append(f"- {icon} **{escape(label)} × {amount}**：{escape(desc)}")
    return '\n'.join(lines)


def render_abilities(state, en=False):
    from .i18n_v2 import ABILITY_EN, EFFECT_EN
    lines = ['## ✨ Known abilities' if en else '## ✨ 已掌握能力']
    lines.append('Ability rating and mastery level are separate.' if en else '能力评级表示能力层次；精通等级表示通过残响强化的程度，与主角自身异能等级分别展示。')
    if state.get('flags', {}).get('system_bound'):
        rank=ability_rank_label(state.get('ability_rank'),en)
        lines.append(f'**独核掠夺·残响转化（系统专属 · 当前评级：{rank}，随宿主成长）**：亲自击败魔物后可获得其能力残响；在此选择并融合残响可掌握对应能力。融合需要15能量，增加8污染，污染达到65时无法融合。' if not en else f'**Core Plunder: Echo Fusion · System ability · Current rating {rank}**: Defeat a creature to obtain an ability echo, then fuse it here for 15 energy and 8 pollution. Fusion requires pollution below 65.')
    for key in sorted(_known_skills(state),key=lambda k:(ABILITY_RANKS.index(ABILITIES[k]['rank']),k)):
        if key not in ABILITIES:
            continue
        item = ABILITIES[key]
        level=next((x.get('level',1) for x in state.get('skills',[]) if x.get('catalog_id',x.get('id'))==key),1)
        name = ABILITY_EN.get(key, key) if en else item['name']
        description = EFFECT_EN.get(item['effect'], item['effect']) if en else item['description']
        cost = f"energy {item['energy_cost']}, cooldown {item['cooldown']} exchanges" if en else f"能量 {item['energy_cost']}，冷却 {item['cooldown']} 次交锋"
        effective=round(item['multiplier']*(1+.1*(level-1)),2)
        multiplier = (f" · {effective}× ATK" if en else f" · 伤害 {effective}×攻击") if item['multiplier'] else ''
        effect_note = ''
        if item['effect'] in ('bleed', 'poison', 'burn'):
            percent=round(12*(1+.1*(level-1)),1)
            effect_note = f' · {percent}% ATK for 2 exchanges' if en else f' · 持续2次交锋，每次{percent}%攻击伤害'
        elif item['effect'] == 'heal':effect_note = f' · restores {35+5*(level-1)}% max HP' if en else f' · 恢复{35+5*(level-1)}%最大生命'
        elif item['effect'] == 'energy_heal':effect_note = f' · costs 10% max HP; restores {25+5*(level-1)}% max energy' if en else f' · 消耗10%最大生命，恢复{25+5*(level-1)}%最大能量'
        elif item['effect'] == 'shield':effect_note = f' · {level+1} shielded exchanges' if en else f' · 护盾持续{level+1}次受击'
        elif item['effect'] == 'weaken':effect_note = f' · weakens enemy for {level+1} exchanges' if en else f' · 削弱敌人并破甲，持续{level+1}次交锋'
        rank=ability_rank_label(item['rank'],en)
        mastery=f'Mastery Lv.{level}' if en else f'精通 Lv.{level}'
        lines.append(f"- **{escape(name)} · {rank} · {mastery}**：{escape(description)} （{cost}{multiplier}{effect_note}）")
    return '\n'.join(lines)


def render_equipment(state, en=False):
    from .i18n_v2 import GEAR_EN, SPECIAL_EN
    lines = ['## 🛡️ Equipment' if en else '## 🛡️ 装备']
    for slot, label in SLOT_LABELS.items():
        instance = state['equipment_slots'].get(slot)
        item_id = state['equipment_items'].get(instance, {}).get('item_id') if instance else None
        item = EQUIPMENT.get(item_id)
        description = (f"**{escape(GEAR_EN.get(item_id,item['name']))}**: {escape(format_stats(item['stats'],True))}; special: {escape(SPECIAL_EN.get(item_id,item.get('special','None.')))}"
                       if item and en else f"**{escape(item['name'])}**：{escape(item['description'])}；{escape(format_stats(item['stats']))}；特殊能力：{escape(item.get('special','无'))}"
                       if item else ('未知旧装备 ' + escape(str(item_id)) if item_id else '空'))
        if en:
            label = {'weapon':'Weapon','head':'Head','chest':'Chest','hands':'Hands','legs':'Legs','feet':'Feet','accessory':'Accessory'}[slot]
            if not item_id:description='Empty'
        lines.append(f'- {label}：{description}')
    return '\n'.join(lines)


def preview_equipment(state, instance_id, slot):
    validate_state_v2(state)
    instance = state.get('equipment_items', {}).get(instance_id)
    item = EQUIPMENT.get(instance.get('item_id')) if instance else None
    if not item or slot not in SLOTS or item['slot'] != slot:
        raise ValueError('请选择适合该部位的装备')
    if instance_id in state['equipment_slots'].values():
        raise ValueError('这件装备已穿戴')
    before = equipment_stats(state)
    candidate = deepcopy(state); candidate['equipment_slots'][slot] = instance_id
    after = equipment_stats(candidate)
    changes = {key: after[key] - before[key] for key in ('max_hp', 'max_energy', 'attack', 'defense')}
    return f"{item['name']}：{item['description']}。特殊能力：{item.get('special','无')}。穿戴变化：" + format_stats(changes)


def render_codex(state, en=False):
    from .i18n_v2 import ACTION_EN, ABILITY_EN, GEAR_EN, SPECIAL_EN, DUNGEON_EN, EFFECT_EN, action_label
    blocks = []
    for kind, label in (('monster', '魔物'), ('ability', '能力'), ('equipment', '装备'), ('dungeon', '地下城')):
        entries = codex_entries(state, kind); rows = []
        for item in entries:
            name = item['name']
            if en:
                mapping = {'monster': ACTION_EN, 'ability': ABILITY_EN, 'equipment': GEAR_EN, 'dungeon': DUNGEON_EN}[kind]
                name = mapping.get(item['id'], item['id'].replace('_', ' ').title())
            if kind=='monster':name='【'+monster_kind(item,en)+'】'+name
            if kind=='ability':name=ability_rank_label(item['rank'],en)+' · '+name
            details = ('Details locked; the system senses its presence.' if not item['unlocked'] else '') if en else escape(item.get('description', ''))
            if en and kind == 'equipment' and not item['unlocked']:
                source = EQUIPMENT[item['id']].get('boss_id') or EQUIPMENT[item['id']].get('elite_id')
                details = 'Defeating ' + escape(action_label({'id': source, 'label': source})) + ' may reveal this recipe.' if source else 'Obtain the required material to unlock.'
            if kind == 'monster' and item['unlocked']:
                abilities = ', '.join(ability_label(x,en) for x in item['abilities'])
                details += (f"<br>Rank {escape(item['rank'])} · HP {item['hp']} · ATK {item['attack']} · Length {item['length_m']} m<br>Abilities: {escape(abilities)}" if en else f"<br>评级 {escape(item['rank'])} · 生命 {item['hp']} · 攻击 {item['attack']} · 体长 {item['length_m']}米<br>能力：{escape(abilities)}")
                if item['boss']:
                    details += '<br>Bosses cannot be challenged repeatedly.' if en else '<br>重要首领不可重复挑战。'
            elif kind == 'ability':
                details += (f"{escape(EFFECT_EN.get(item['effect'],item['effect']))}<br>Rating: {escape(ability_rank_label(item['rank'],True))}<br>Energy {item['energy_cost']} · cooldown {item['cooldown']} exchanges" if en else f"<br>能力评级：{escape(ability_rank_label(item['rank']))}<br>能量消耗 {item['energy_cost']} · 冷却 {item['cooldown']} 次交锋")
            elif kind == 'equipment' and item['unlocked']:
                slot=(SLOTS_EN if en else PLAYER_SLOTS).get(item['slot'],'其他')
                details += (f"<br>Slot: {escape(slot)} · {escape(format_stats(item['stats'],True))}<br>Special: {escape(SPECIAL_EN.get(item['id'],item['special']))}<br>Recipe: {escape(format_recipe(item['recipe'],state['inventory'],True))}" if en else f"<br>部位：{escape(slot)}<br>属性：{escape(format_stats(item['stats']))}<br>特殊能力：{escape(item['special'])}<br>打造材料：{escape(format_recipe(item['recipe'],state['inventory']))}")
            elif kind == 'dungeon' and item['unlocked']:
                details += (f"<br>Rank: {escape(item['rank'])}" if en else f"<br>评级：{escape(item['rank'])}")
            status = ('Unlocked' if item['unlocked'] else 'Locked') if en else ('已解锁' if item['unlocked'] else '尚未解锁')
            rows.append(f"<details class=\"codex-entry\"><summary>{escape(name)} · {status}</summary><p>{details}</p></details>")
        heading = {'monster':'Creatures','ability':'Abilities','equipment':'Equipment','dungeon':'Dungeons'}[kind] if en else label
        blocks.append(f"<details><summary>{heading} · {sum(bool(x['unlocked']) for x in entries)}/{len(entries)}</summary>{''.join(rows)}</details>")
    return '<section class="player-status"><h2>'+('Codex' if en else '图鉴')+'</h2>' + ''.join(blocks) + '</section>'
