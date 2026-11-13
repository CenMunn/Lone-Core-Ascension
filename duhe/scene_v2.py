"""One authoritative frame for the text, illustration and speaker pipeline."""
from .catalog import MONSTERS
from .world import appearance_for

LOCATIONS = {1: '外环废墟', 2: '要塞训练营', 3: '要塞物资站', 4: '高阶地下城',
             5: '北墙防线', 6: '通天塔', 7: '终焉母核'}


def scene_for_v2(state, event, previous=None):
    action = event.get('action_id', '')
    combat = state.get('combat')
    inherit=previous and (previous.get('chapter')==state['chapter'] or previous.get('location')==LOCATIONS.get(state['chapter'],'要塞'))
    if action == 'opening':
        cast = ['protagonist', 'heroine']
    elif event.get('present_character_ids'):
        cast = list(dict.fromkeys(event['present_character_ids']))
    elif combat or action in ('start_encounter', 'attack', 'auto_attack', 'skill', 'guard', 'retreat', 'awaken'):
        cast = ['protagonist']
    elif inherit:
        cast = list(previous.get('present_character_ids') or ['protagonist'])
    else:
        cast = ['protagonist']
    monster_id = (combat or {}).get('monster_id') or event.get('monster_id')
    if monster_id == 'tower_100' and 'boss' not in cast:
        cast.append('boss')
    frame = {'scene_id': f"v2-{event.get('id', 'current')}",
             'chapter':state['chapter'],
             'location':previous['location'] if inherit else LOCATIONS.get(state['chapter'], '要塞'),
             'present_character_ids': cast, 'combat_active': bool(combat),
             'core_power_active': bool(combat and action in ('attack', 'skill', 'awaken')),
             'main_action': event.get('summary', ''), 'romance_budget': 0,
             'heroine_hairstyle': 'loose', 'known_facts': list(state.get('known_facts', []))}
    if monster_id in MONSTERS:
        monster = MONSTERS[monster_id]
        frame['monster'] = {'id': monster_id, 'name': monster['name'],
                            'kind':'BOSS' if monster['boss'] else '精英' if monster.get('elite_material') else '普通',
                            'rank':monster['rank'],
                            'description': monster['description'], 'length_m': monster['length_m'],
                            'scale_instruction': '以成年男性为参照，低机位表现怪物实际体型与压迫感。'}
    frame['appearance_snapshots'] = {cid: appearance_for(cid, state, frame) for cid in cast}
    return frame
