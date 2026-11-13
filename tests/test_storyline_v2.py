import pytest
from duhe.campaign import available_milestones, perform_milestone
from duhe.models_v2 import migrate_state
from duhe.rules import new_game, apply_action


def ready():
    old, _ = apply_action(new_game(), 'opening')
    return migrate_state(old, story_turn=1, operation_seq=1)


def test_heroine_study_has_prerequisites_and_is_branch_local():
    s = ready()
    assert 'heroine_sss' not in {x['id'] for x in available_milestones(s)}
    s['ability_rank'] = 'A'
    s['inventory']['clean_core'] = 5
    s['clean_core_grades'] = {'ungraded': 5}
    s['flags']['rival_resolved'] = True
    changed, event = perform_milestone(s, 'heroine_sss', 'study')
    assert changed['heroine_rank'] == 'SSS' and s['heroine_rank'] == 'SS'
    assert changed['story_turn'] == s['story_turn'] + 1
    assert event['present_character_ids'] == ['protagonist', 'heroine']


def test_wall_boss_must_be_unlocked_by_story_and_not_marked_defeated():
    s = ready()
    s['ability_rank'] = 'S'
    s['flags'].update(rival_resolved=True, heroine_sss=True)
    changed, event = perform_milestone(s, 'wall_prepare', 'wall')
    assert 'wall_boss' in changed['flags']['unlocked_bosses']
    assert not changed['flags'].get('wall_saved')
    with pytest.raises(ValueError):
        perform_milestone(changed, 'wall_prepare', 'again')


def test_courier_branches_are_mutually_exclusive_and_stateful():
    s = ready(); s['ability_rank'] = 'B'; s['flags']['rival_resolved'] = True
    choices = {x['id'] for x in available_milestones(s)}
    assert {'help_couriers', 'secure_samples'} <= choices
    rescued, event = perform_milestone(s, 'help_couriers', 'help')
    secured, _ = perform_milestone(s, 'secure_samples', 'sample')
    assert rescued['relationships']['friend']['trust'] > secured['relationships']['friend']['trust']
    assert rescued['flags']['courier_decision'] != secured['flags']['courier_decision']
    assert 'secure_samples' not in {x['id'] for x in available_milestones(rescued)}
    assert event['present_character_ids'] == ['protagonist', 'friend']
