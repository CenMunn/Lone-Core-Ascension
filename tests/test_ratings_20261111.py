from duhe.catalog import ABILITIES,ABILITY_RANKS,codex_entries
from duhe.rules import new_game,apply_action
from duhe.models_v2 import migrate_state
from duhe.viewmodel_v2 import render_abilities,render_codex,available_actions
from duhe.player_labels import ability_label

def ready():
    state,_=apply_action(new_game(),'opening')
    return migrate_state(state,story_turn=1,operation_seq=1)

def test_all_abilities_have_explicit_valid_ratings():
    assert all(item['rank'] in ABILITY_RANKS for item in ABILITIES.values())
    assert ABILITIES['residual_sense']['rank']=='UNRANKED'
    assert ABILITIES['life_return']['rank']=='A'
    assert ABILITIES['time_gap']['rank']=='UR'
    assert ABILITIES['final_corrosion']['rank']=='ULTRA'

def test_ability_rating_is_independent_of_owner_rank_and_mastery():
    state=ready();state['ability_rank']='F-'
    state['skills'].extend([{'id':'rending_charge','level':2},{'id':'time_gap','level':1}])
    text=render_abilities(state)
    assert '裂爪突进 · E级 · 精通 Lv.2' in text
    assert '时隙凝滞 · UR级 · 精通 Lv.1' in text
    assert '微弱能量辨识 · 低于F-' in text
    assert state['ability_rank']=='F-'
    assert 'UR' in ability_label('time_gap',en=True)

def test_boss_markers_are_visible_without_unlocking_stats():
    state=ready();state['bestiary']={'seen':['elite_iron_beetle','tower_10'],'abilities_seen':['shell_guard']}
    entries={x['id']:x for x in codex_entries(state,'monster')}
    assert entries['tower_100']['boss'] and not entries['tower_100']['unlocked'] and 'hp' not in entries['tower_100']
    text=render_codex(state)
    assert '【BOSS】铁脊甲皇' in text and '【BOSS】噬核母皇' in text
    assert '【精英】重甲精英甲虫' in text and '能力评级：F-级' in text
    assert 'shell_guard' not in text
    state['flags']['unlocked_bosses']=['tower_10'];state['tower_floor']=10
    assert '【BOSS】' in next(x['label'] for x in available_actions(state)['battle'] if x['id']=='tower_10')
