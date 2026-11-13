import asyncio
import copy
import json
import pytest
from duhe.rules import new_game,apply_action
from duhe.models_v2 import migrate_state
from duhe.free_story import prepare_free_story,verified_scene
from duhe.engine_v2 import EngineV2
from duhe.providers import Settings

def ready():
    old,_=apply_action(new_game(),'opening')
    return migrate_state(old,story_turn=1,operation_seq=1)

def test_search_and_tracking_go_directly_to_narrative_without_action_matching():
    state=ready();before=copy.deepcopy(state)
    intent='沿冰霜痕迹追踪，去旧城区寻找沈霁月，先看看她是否安全。'
    result,event=prepare_free_story(state,intent,'free-1')
    assert event['player_intent']==intent and event['action_id']=='free_story'
    assert result['story_turn']==2 and state==before
    for field in ('inventory','ability_rank','xp','flags','hp','energy'):assert result[field]==state[field]

def test_scene_does_not_add_a_person_only_because_the_action_searched_for_them():
    state=ready();text='我没有找到沈霁月，来到旧仓库后，只看见破碎的门框。'
    frame=verified_scene(text,{'location':'旧仓库','location_evidence':'来到旧仓库',
                              'present':[{'id':'protagonist'}]}, {'location':'废墟','present_character_ids':['protagonist']},state)
    assert frame['present_character_ids']==['protagonist']
    with pytest.raises(ValueError,match='证据'):
        verified_scene(text,{'present':[{'id':'heroine','evidence':'她站在我身旁'}]},frame,state)

def test_free_story_sends_original_prompt_and_commits_the_actual_scene(tmp_path):
    class Text:
        def __init__(self):self.messages=None
        async def stream(self,messages):
            self.messages=messages
            yield {'type':'delta','text':'我沿着冰霜痕迹找到旧仓库。沈霁月站在仓库门口，听见脚步后转头看向我。'}
            yield {'type':'done'}
        async def structured(self,messages):
            return {'location':'旧仓库门口','location_evidence':'站在仓库门口',
                    'present':[{'id':'protagonist'},{'id':'heroine','evidence':'沈霁月站在仓库门口'}]}
        async def close(self):pass
    async def run():
        e=EngineV2(tmp_path,Settings());await e.text.close();e.text=Text()
        cid=e.create_v2('owner');first=e.controller_v2.act('owner',cid,{'action':'opening'},0,'opening')
        frame=dict(first['meta']['scene'],present_character_ids=['protagonist'],location='废墟东路',chapter=1)
        e.store.set_scene('owner',cid,first['id'],frame)
        intent='沿冰霜痕迹寻找沈霁月，我想确认她是否安全。'
        frames=[x async for x in e.execute_v2('owner',cid,{'action':'free_story','intent':intent},1)]
        assert not frames[-1].get('error')
        node=frames[-1]['node'];scene=node['meta']['scene']
        payload=json.loads(e.text.messages[-1]['content'])
        assert payload['用户自由行动原文']==intent
        assert scene['location']=='旧仓库门口' and scene['present_character_ids']==['protagonist','heroine']
        assert scene['appearance_snapshots']['heroine']['character_id']=='heroine'
        following=e.controller_v2.act('owner',cid,{'action':'continue_story'},2,'continue')
        assert following['meta']['scene']['location']=='旧仓库门口'
        e.store.select('owner',cid,first['id'])
        assert e.store.node('owner',cid)['meta']['scene']['present_character_ids']==['protagonist']
        await e.close()
    asyncio.run(run())

def test_scene_service_failure_does_not_discard_the_finished_free_story(tmp_path):
    class Text:
        async def stream(self,messages):
            yield {'type':'delta','text':'我追踪冰霜痕迹，走到一处残破的仓库前。'};yield {'type':'done'}
        async def structured(self,messages):raise RuntimeError('暂时断线')
        async def close(self):pass
    async def run():
        e=EngineV2(tmp_path,Settings());await e.text.close();e.text=Text();cid=e.create_v2('owner')
        e.controller_v2.act('owner',cid,{'action':'opening'},0,'opening')
        frames=[x async for x in e.execute_v2('owner',cid,{'action':'free_story','intent':'追踪冰霜痕迹'},1)]
        assert frames[-1]['node']['text'].startswith('我追踪')
        assert frames[-1]['node']['meta']['scene']['scene_verified'] is False
        assert e.store.campaign('owner',cid)['revision']==2
        await e.close()
    asyncio.run(run())
