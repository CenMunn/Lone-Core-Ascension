"""Read-only draft catalog shared by v2 rules and future UI panels."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/'config'

def _load(name):
    data=json.loads((ROOT/name).read_text('utf-8'))
    if not isinstance(data,list):raise ValueError(f'{name} 必须是列表')
    result={}
    for item in data:
        if not isinstance(item,dict) or not isinstance(item.get('id'),str) or item['id'] in result:
            raise ValueError(f'{name} 含无效或重复ID')
        result[item['id']]=item
    return result

ABILITIES=_load('abilities.json')
MONSTERS=_load('monsters.json')
EQUIPMENT=_load('equipment.json')
DUNGEONS=_load('dungeons.json')
ABILITY_RANKS=('UNRANKED','F-','E','D','C','B','A','S','SS','SSS','UR','ULTRA')
for ability in ABILITIES.values():
    if ability.get('rank') not in ABILITY_RANKS:raise ValueError('能力缺少有效评级：'+ability['id'])
for monster in MONSTERS.values():
    if any(skill not in ABILITIES for skill in monster['abilities']):raise ValueError('魔物能力引用不存在')
for item in EQUIPMENT.values():
    if item.get('boss_id') and item['boss_id'] not in MONSTERS:raise ValueError('装备BOSS引用不存在')
for dungeon in DUNGEONS.values():
    if any(mid not in MONSTERS for mid in dungeon['monster_ids']):raise ValueError('地下城魔物引用不存在')

def codex_entries(state,kind):
    """Return only information this branch has unlocked."""
    bestiary=state.get('bestiary') or {}
    if kind=='monster':
        seen=set(bestiary.get('seen',[]));entries=[]
        for mid,monster in MONSTERS.items():
            entry={'id':mid,'name':monster['name'],'unlocked':mid in seen,'boss':monster['boss'],'elite':bool(monster.get('elite_material'))}
            if mid in seen:
                entry.update({k:monster[k] for k in ('rank','hp','attack','length_m','description','abilities')})
                entry['challengeable']=not monster['boss'] and not state.get('combat') and state.get('hp',0)>0
            else:
                entry.update(description=monster['sensed'],challengeable=False)
            entries.append(entry)
        return entries
    if kind=='equipment':
        inventory=state.get('inventory') or {};learned=set(state.get('unlocked_recipes',[]));entries=[]
        for iid,item in EQUIPMENT.items():
            material=item.get('unlock_material');unlocked=not material or inventory.get(material,0)>0 or iid in learned
            entry={'id':iid,'name':item['name'],'unlocked':unlocked}
            if unlocked:
                entry.update({k:item[k] for k in ('slot','stats','description','recipe')})
                entry['special']=item.get('special','无特殊能力')
            else:
                source=item.get('boss_id') or item.get('elite_id')
                if item.get('unlock_after_purification'):
                    entry['description']='击败终焉之核并完成反向净化后，或许能获得制作方法。'
                else:
                    entry['description']='也许击败'+MONSTERS[source]['name']+'会获得该装备的制作方法。' if source in MONSTERS else '获得对应材料后解锁配方。'
            entries.append(entry)
        return entries
    if kind=='ability':
        visible=set(bestiary.get('abilities_seen',[]))
        visible.update(x.get('catalog_id') or x.get('id') for x in state.get('skills',[]) if isinstance(x,dict))
        return [dict(item,unlocked=True) for aid,item in ABILITIES.items() if aid in visible]
    if kind=='dungeon':
        visible=set(bestiary.get('dungeons_seen',[]));entries=[]
        for did,item in DUNGEONS.items():
            entry={'id':did,'name':item['name'],'unlocked':did in visible}
            if did in visible:entry.update({k:item[k] for k in ('rank','description','monster_ids')})
            else:entry['description']='系统感受到该区域存在，详细信息尚未解锁。'
            entries.append(entry)
        return entries
    raise ValueError('未知图鉴分类')
