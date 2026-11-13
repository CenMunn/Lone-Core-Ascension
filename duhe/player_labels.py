"""Player-facing labels shared by inventory, equipment and the codex."""
from .catalog import EQUIPMENT,ABILITIES

STATS={'attack':'攻击力','defense':'防御力','max_hp':'最大生命','max_energy':'最大核心能量'}
STATS.update({'hp':'生命','energy':'核心能量','pollution':'污染','xp':'修炼经验','ability_xp':'异能经验','raw_core':'污染核心','clean_core':'净化核心'})
STATS_EN={'attack':'Attack','defense':'Defense','max_hp':'Max health','max_energy':'Max core energy'}
SLOTS={'weapon':'武器','head':'头部','chest':'胸甲','hands':'手部','legs':'腿部','feet':'足部','accessory':'饰品'}
SLOTS_EN={'weapon':'Weapon','head':'Head','chest':'Chest','hands':'Hands','legs':'Legs','feet':'Feet','accessory':'Accessory'}
MATERIALS={'food':'食物','material':'通用材料','raw_core':'污染核心','clean_core':'净化核心',
           'iron_king_fragment':'铁脊王碎片','gravity_fragment':'重力法则碎片','time_fragment':'时间法则碎片',
           'elite_iron_shell':'精英铁甲片','elite_tough_hide':'精英韧皮','elite_conductive_crystal':'导能晶骨'}
MATERIALS.update({x['unlock_material']:x['unlock_material_name'] for x in EQUIPMENT.values() if x.get('unlock_material_name')})
MATERIALS_EN={'food':'Food','material':'Common material','raw_core':'Contaminated core','clean_core':'Purified core'}

def material_name(key,en=False):
    return MATERIALS_EN.get(key,MATERIALS.get(key,'Other material')) if en else MATERIALS.get(key,'其他制作材料')

def format_stats(stats,en=False):
    labels=STATS_EN if en else STATS
    return '、'.join(f'{labels.get(key,"附加属性")} {value:+g}' for key,value in stats.items()) or ('None' if en else '无属性变化')

def format_recipe(recipe,inventory=None,en=False):
    if not recipe:return 'Starting equipment; no recipe.' if en else '初始装备，无需打造。'
    rows=[]
    for key,required in recipe.items():
        line=f'{material_name(key,en)} ×{required}'
        if inventory is not None:
            owned=inventory.get(key,0);missing=max(0,required-owned)
            line+=(f' (owned {owned}; missing {missing})' if en else f'（持有 {owned}，'+(f'还缺 {missing}' if missing else '已足够')+'）')
        rows.append(line)
    return '；'.join(rows)

def format_effects(effects):
    labels={'bleed':'撕裂','poison':'毒蚀','burn':'灼烧','shield':'护盾','control':'凝滞','weaken':'削弱'}
    return '、'.join(labels.get(x.get('type'),'其他状态')+f"（剩余{x.get('remaining',0)}次交锋）" for x in effects) or '无'

def format_cooldowns(combat):
    from .catalog import ABILITIES
    values=[]
    for key,ready in combat.get('cooldowns',{}).items():
        remaining=max(0,ready-combat.get('exchange',0)-1)
        if remaining:values.append(ABILITIES.get(key,{}).get('name','能力')+f'：还需{remaining}次交锋')
    return '；'.join(values) or '所有能力均可使用（仍需满足能量等条件）'

def ability_rank_label(rank,en=False):
    if rank=='UNRANKED':return 'Below F-' if en else '低于F-'
    if not rank:return 'Unrated' if en else '评级未记录'
    return rank if en else rank+'级'

def ability_label(ability_id,en=False):
    ability=ABILITIES.get(ability_id)
    if not ability:return 'Unknown ability' if en else '未知能力'
    if en:
        from .i18n_v2 import ABILITY_EN
        name=ABILITY_EN.get(ability_id,ability['name'])
    else:name=ability['name']
    return name+'（'+ability_rank_label(ability.get('rank'),en)+'）'

def monster_kind(monster,en=False):
    if monster.get('boss'):return 'BOSS'
    if monster.get('elite') or monster.get('elite_material'):return 'Elite' if en else '精英'
    return 'Normal' if en else '普通'
