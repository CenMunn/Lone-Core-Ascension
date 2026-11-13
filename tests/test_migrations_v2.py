import copy
from duhe.models_v2 import migrate_state, derive_story_turn, validate_state_v2
from duhe.rules import new_game, apply_action
from duhe.migrations import migrate_campaign

def test_legacy_four_phases_map_to_three_and_preserve_progress():
    old=new_game(mode='demo',checkpoint='wall')
    old['realm_stage']=3;old['xp']=439;old['hp']=old['max_hp']//2;old['energy']=30
    before=copy.deepcopy(old)
    new=migrate_state(old,story_turn=17,operation_seq=125)
    assert old==before
    assert new['schema']==2 and new['rules_version']==2
    assert new['realm_index']==old['realm_index'] and new['realm_stage']==2
    assert new['xp']==439 and new['inventory']==old['inventory']
    assert new['ability_rank']==old['ability_rank'] and new['relationships']==old['relationships']
    assert new['legacy_turn']==old['turn'] and new['story_turn']==17 and new['operation_seq']==125
    assert abs(new['hp']/new['max_hp']-old['hp']/old['max_hp']) < .01
    assert abs(new['energy']/new['max_energy']-.3) < .01
    assert new['countdown']==5000-17 and new['legacy_countdown']==old['countdown']
    validate_state_v2(new)

def test_story_clock_only_counts_entry_to_combat_once():
    state,event=apply_action(new_game(),'opening')
    assert derive_story_turn(0,{},event)==1
    assert derive_story_turn(1,state,{'action_id':'refine'})==1
    assert derive_story_turn(1,state,{'action_id':'explore'})==2
    state['combat']={'kind':'explore'}
    assert derive_story_turn(2,state,{'action_id':'attack'})==2

def test_all_branches_migrate_with_independent_clocks_and_new_ids():
    initial=new_game();opening,event=apply_action(initial,'opening')
    rested,rest_event=apply_action(opening,'rest')
    explored,explore_event=apply_action(opening,'explore')
    graph={'campaign':{'id':'old','owner':'owner','current_node':'explore','revision':2},'nodes':[
        {'id':'root','parent_id':None,'state':initial,'event':{},'text':'','meta':{},'image':None},
        {'id':'open','parent_id':'root','state':opening,'event':event,'text':'开场','meta':{},'image':None},
        {'id':'rest','parent_id':'open','state':rested,'event':rest_event,'text':'休整','meta':{},'image':None},
        {'id':'explore','parent_id':'open','state':explored,'event':explore_event,'text':'探索','meta':{},'image':None}], 'feedback':[]}
    before=copy.deepcopy(graph);converted,mapping=migrate_campaign(graph)
    assert graph==before and set(mapping)=={'root','open','rest','explore'}
    assert all(k!=v for k,v in mapping.items())
    nodes={n['id']:n for n in converted['nodes']}
    assert nodes[mapping['rest']]['parent_id']==mapping['open']
    assert nodes[mapping['rest']]['state']['story_turn']==1
    assert nodes[mapping['explore']]['state']['story_turn']==2
    assert converted['campaign']['current_node']==mapping['explore']

def test_migrated_legacy_battle_requires_explicit_safe_completion():
    from duhe.combat import combat_step
    import pytest
    old,_=apply_action(new_game(),'opening');old,_=apply_action(old,'explore')
    migrated=migrate_state(old,story_turn=2,operation_seq=2)
    assert migrated['combat']==old['combat'] and migrated['legacy_battle_requires_old_rules']
    with pytest.raises(ValueError,match='旧版战斗'):
        combat_step(migrated,{'action':'attack'},'op')

def test_v2_validation_rejects_inconsistent_inventory_grades():
    import pytest
    state=migrate_state(new_game(),story_turn=0,operation_seq=0)
    state['core_grades']={'F-':1}
    with pytest.raises(ValueError,match='核心品质'):
        validate_state_v2(state)

def test_import_legacy_bundle_creates_v2_copy_with_branch_tree_and_image(tmp_path):
    from duhe.storage import Store
    store=Store(tmp_path/'source.sqlite');owner='owner';initial=new_game();cid=store.create(owner,initial)
    root=store.campaign(owner,cid);opened,event=apply_action(initial,'opening','op1')
    node=store.commit(owner,cid,root['current_node'],0,'op1',opened,'救援',event)
    image=tmp_path/'scene.png';image.write_bytes(b'old-image')
    store.set_image(owner,cid,node['id'],{'status':'SUCCEEDED','path':str(image)})
    bundle=store.export_bundle(owner,cid,tmp_path/'out')
    imported=store.import_bundle('new-owner',bundle,migrate_v2=True)
    converted=store.node('new-owner',imported)
    assert converted['state']['schema']==2 and converted['state']['story_turn']==1
    assert converted['text']=='救援' and len(store.nodes('new-owner',imported))==2
    assert converted['image']['path']!=str(image) and open(converted['image']['path'],'rb').read()==b'old-image'
    assert store.node(owner,cid)['state']['schema']==1
    v2_bundle=store.export_bundle('new-owner',imported,tmp_path/'v2')
    import pytest
    with pytest.raises(ValueError,match='新版'):
        store.import_bundle('new-owner',v2_bundle)
    imported_again=store.import_bundle('new-owner',v2_bundle,migrate_v2=True)
    assert store.node('new-owner',imported_again)['state']['schema']==2
