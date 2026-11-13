from duhe.actions import describe_action

def test_actions_are_grouped_and_battle_counts_only_at_start():
    state={'combat':None}
    for action in ('refine','absorb_core','rest','train','absorb:echo:1'):
        spec=describe_action(state,{'action':action})
        assert spec.category=='ordinary' and not spec.advances_story
    assert describe_action(state,{'action':'explore'}).category=='prepare_battle'
    assert describe_action(state,{'action':'explore'}).advances_story
    assert describe_action(state,{'action':'heroine_sss'}).category=='story'
    for action in ('attack','guard','skill','retreat'):
        spec=describe_action({'combat':{'id':'enemy'}},{'action':action})
        assert spec.category=='combat' and not spec.advances_story
