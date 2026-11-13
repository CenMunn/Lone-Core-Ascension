from duhe.scene_v2 import scene_for_v2
from duhe.models_v2 import migrate_state
from duhe.rules import new_game, apply_action
from duhe.combat import start_encounter
from duhe.prompts import image_prompt


def test_opening_and_beetle_use_authoritative_scene_cast():
    old, event = apply_action(new_game(), 'opening')
    state = migrate_state(old, story_turn=1, operation_seq=1)
    frame = scene_for_v2(state, event)
    assert frame['present_character_ids'] == ['protagonist', 'heroine']
    fight, event = start_encounter(state, 'polluted_beetle', 'fight')
    frame = scene_for_v2(fight, event, frame)
    assert frame['present_character_ids'] == ['protagonist']
    assert frame['monster']['length_m'] == 3.0
    assert '成年' in frame['monster']['scale_instruction']
    prompt, negative = image_prompt({'character_ids': ['protagonist'], 'description': '远处一只小甲虫'}, fight, frame)
    assert '小甲虫' not in prompt and '巨型' in prompt
    assert '手掌大小' in negative
