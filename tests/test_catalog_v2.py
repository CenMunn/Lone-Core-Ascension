from duhe.catalog import ABILITIES, MONSTERS, EQUIPMENT, DUNGEONS, codex_entries

def test_catalog_has_unique_bosses_full_tower_and_large_beetle():
    monsters=list(MONSTERS.values())
    assert len(monsters)>=23 and len(MONSTERS)==len({m['id'] for m in monsters})
    assert sorted(m['floor'] for m in monsters if m.get('floor'))==list(range(10,101,10))
    boss=next(m for m in monsters if m.get('floor')==100)
    assert boss['name']=='噬核母皇·终焉之核' and boss['boss'] and boss['nonhuman']
    beetle=next(m for m in monsters if m['name']=='污染甲虫')
    assert beetle['length_m']>=3 and beetle['hp']>0 and beetle['attack']>0
    assert all(skill in ABILITIES for m in monsters for skill in m['abilities'])
    assert DUNGEONS

def test_locked_monsters_reveal_only_sensed_information_and_bosses_never_repeat():
    state={'bestiary':{'seen':['polluted_beetle','tower_10']},'combat':None,'hp':100}
    entries={x['id']:x for x in codex_entries(state,'monster')}
    assert entries['polluted_beetle']['challengeable'] and entries['polluted_beetle']['hp']>0
    assert not entries['tower_10']['challengeable']
    assert 'hp' not in entries['tower_100'] and entries['tower_100']['name']
    state['combat']={'id':'ongoing'}
    assert not next(x for x in codex_entries(state,'monster') if x['id']=='polluted_beetle')['challengeable']

def test_locked_boss_equipment_shows_name_and_clue_until_material_obtained():
    state={'inventory':{},'bestiary':{'seen':[]}}
    item=next(x for x in codex_entries(state,'equipment') if x['id']=='iron_king_chest')
    assert not item['unlocked'] and '也许击败' in item['description'] and 'stats' not in item
    state['inventory']['iron_king_fragment']=1
    item=next(x for x in codex_entries(state,'equipment') if x['id']=='iron_king_chest')
    assert item['unlocked'] and item['stats'] and item['recipe']
