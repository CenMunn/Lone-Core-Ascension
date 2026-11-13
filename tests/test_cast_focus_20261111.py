import asyncio
import copy
import json
from duhe.cast_director import choose_focus
from duhe.rules import new_game,apply_action
from duhe.models_v2 import migrate_state
from duhe.engine_v2 import EngineV2
from duhe.providers import Settings

def ready():
    state,_=apply_action(new_game(),'opening')
    return migrate_state(state,story_turn=1,operation_seq=1)

def test_character_contact_respects_free_intent_and_solo_combat():
    state=ready();scene={'location':'外环废墟','present_character_ids':['protagonist']}
    assert choose_focus(state,{'action_id':'free_story'},[],scene) is None
    assert choose_focus(state,{'action_id':'heroine_sss'},[],scene) is None
    state['combat']={'monster_id':'polluted_beetle'}
    assert choose_focus(state,{'action_id':'continue_story','id':'x'},[],scene) is None

def test_tower_contacts_do_not_insert_companions_into_the_party():
    state=ready();state['chapter']=6
    frame={'location':'通天塔','present_character_ids':['protagonist']};before=copy.deepcopy(frame)
    options=[choose_focus(state,{'action_id':'continue_story','id':str(n)},[],frame) for n in range(20)]
    contacts=[x for x in options if x]
    assert contacts and all('保持主角独行' in x['contact'] for x in contacts)
    assert frame==before

def test_focus_character_is_grounded_in_the_actual_generated_scene(tmp_path,monkeypatch):
    monkeypatch.setattr('duhe.cast_director.choose_focus',lambda *args:{'character_id':'friend','thread':'运输线线索','contact':'有来由地相遇','guidance':'推进当前线索'})
    class Text:
        def __init__(self):self.messages=None
        async def stream(self,messages):
            self.messages=messages
            yield {'type':'delta','text':'我走到废墟出口，周野正推着运输车，向我招手。他指向车上那只破损的样本箱。'}
            yield {'type':'done'}
        async def structured(self,messages):
            return {'location':'废墟出口','location_evidence':'走到废墟出口',
                    'present':[{'id':'protagonist'},{'id':'friend','evidence':'周野正推着运输车'}]}
        async def close(self):pass
    async def run():
        e=EngineV2(tmp_path,Settings());await e.text.close();e.text=Text();cid=e.create_v2('owner')
        first=e.controller_v2.act('owner',cid,{'action':'opening'},0,'opening')
        result=[x async for x in e.execute_v2('owner',cid,{'action':'continue_story'},1)]
        node=result[-1]['node']
        assert node['meta']['scene']['present_character_ids']==['protagonist','friend']
        assert node['event']['cast_focus']['character_id']=='friend'
        assert node['state']['inventory']==first['state']['inventory']
        payload=json.loads(e.text.messages[-1]['content'])
        assert '周野' in payload['本轮重要人物联系建议']['character_card']
        await e.close()
    asyncio.run(run())
