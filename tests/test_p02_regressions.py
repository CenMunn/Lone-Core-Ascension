import asyncio
import pytest
from duhe.engine import Engine
from duhe.providers import Settings
from duhe.storage import Store
from duhe.rules import new_game
from duhe.rules import apply_action, scene_for
from duhe.scene import build_scene

def test_free_action_rejects_unmatched_intent(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        class Text:
            async def structured(self,m):return {'status':'unsupported','action_id':'rest','reason':'当前场景不能完成该行动'}
            async def close(self):pass
        try:
            await e.text.close();e.text=Text();cid=e.create('owner')
            async for _ in e.execute('owner',cid,'opening',0,offline=True,with_image=False):pass
            before=e.store.node('owner',cid)
            with pytest.raises(ValueError,match='当前场景不能完成'):
                await e.resolve_action('owner',cid,'亲吻沈霁月')
            assert e.store.node('owner',cid)==before
        finally:await e.close()
    asyncio.run(run())

def test_rest_keeps_rescuer_from_parent_scene_instead_of_inventing_friend():
    state,event=apply_action(new_game(),'opening')
    previous=scene_for(state,event)
    state,event=apply_action(state,'rest')
    frame=build_scene(state,event,previous)
    assert frame['present_character_ids']==['protagonist','heroine']
    assert 'heroine' in frame['appearance_snapshots'] and 'friend' not in frame['appearance_snapshots']

def test_reused_operation_must_match_parent_and_payload(tmp_path):
    store=Store(tmp_path/'db.sqlite');cid=store.create('owner',new_game())
    root=store.campaign('owner',cid);state=new_game()
    first=store.commit('owner',cid,root['current_node'],0,'operation',state,'a',{'action_id':'rest'})
    assert store.commit('owner',cid,root['current_node'],0,'operation',state,'a',{'action_id':'rest'})['id']==first['id']
    with pytest.raises(ValueError):
        store.commit('owner',cid,root['current_node'],0,'operation',state,'b',{'action_id':'scan'})
    with pytest.raises(ValueError):
        store.commit('owner',cid,first['id'],1,'operation',state,'a',{'action_id':'rest'})

def test_rewind_new_absorption_branch_does_not_inherit_rest_or_scan(tmp_path):
    store=Store(tmp_path/'branch.sqlite')
    state,_=apply_action(new_game(),'opening');state['inventory']['clean_core']=1
    cid=store.create('owner',state);root=store.campaign('owner',cid)
    rested,event=apply_action(state,'rest','rest-op')
    first=store.commit('owner',cid,root['current_node'],0,'rest-op',rested,'休整',event)
    scanned,event=apply_action(rested,'scan','scan-op')
    second=store.commit('owner',cid,first['id'],1,'scan-op',scanned,'扫描',event)
    store.select('owner',cid,root['current_node']);revision=store.campaign('owner',cid)['revision']
    absorbed,event=apply_action(state,'absorb_core','absorb-op')
    branch=store.commit('owner',cid,root['current_node'],revision,'absorb-op',absorbed,'吸收',event)
    assert [n['id'] for n in store.history('owner',cid)]==[root['current_node'],branch['id']]
    assert branch['parent_id']==root['current_node'] and second['parent_id']==first['id']
    assert 'rest-op' not in branch['state']['completed_operations']
    assert 'scan-op' not in branch['state']['completed_operations']
    assert len(store.nodes('owner',cid))==4

def test_problem_feedback_does_not_become_world_observation(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            cid=e.create('owner');node=e.store.node('owner',cid)
            e.store.feedback('owner',cid,node['id'],{'confirmed':True,'tags':['外貌不一致'],'observation':'男主不是小孩'})
            e.store.feedback('owner',cid,node['id'],{'confirmed':True,'tags':[],'observation':'门框上有霜痕'})
            assert e.observations('owner',cid)==['门框上有霜痕']
        finally:await e.close()
    asyncio.run(run())
