import asyncio
import copy
from pathlib import Path
from duhe.affinity import scores,initialize,apply_observations,narrative_context,render_affinity
from duhe.controller_v2 import ControllerV2
from duhe.storage import Store
from duhe.rules import new_game,apply_action
from duhe.models_v2 import migrate_state
from duhe.engine_v2 import EngineV2
from duhe.providers import Settings

def ready():
    old,_=apply_action(new_game(),'opening');state=migrate_state(old,story_turn=1,operation_seq=1)
    return initialize(state)

def test_initial_attitudes_and_no_explicit_intimacy_unlocks(tmp_path):
    c=ControllerV2(Store(tmp_path/'save.sqlite'));state=c.store.node('a',c.create('a'))['state']
    values=scores(state)
    assert all(values[k]>0 for k in ('heroine','friend','mentor','commander'))
    assert all(values[k]<0 for k in ('rival','antagonist','boss'))
    html=render_affinity(state)
    assert '沈霁月' in html and '周野' in html and '随着好感度提升或下降' in html
    assert not any(word in html for word in ('拥抱','亲吻','解锁'))

def test_scripted_choice_rewind_and_portable_save_keep_separate_affinities(tmp_path):
    c=ControllerV2(Store(tmp_path/'save.sqlite'));state=ready()
    state['flags']['rival_resolved']=True;state['ability_rank']='B'
    cid=c.store.create('a',state);root=c.store.node('a',cid)
    helped=c.act('a',cid,{'action':'help_couriers'},0,'help')
    assert scores(helped['state'])['friend']==40
    c.store.select('a',cid,root['id']);rev=c.store.campaign('a',cid)['revision']
    samples=c.act('a',cid,{'action':'secure_samples'},rev,'samples')
    assert scores(samples['state'])['friend']==23
    assert scores(c.store.node('a',cid,helped['id'])['state'])['friend']==40
    archive=c.store.export_bundle('a',cid,tmp_path/'exports')
    copied=c.store.import_bundle('b',Path(archive),migrate_v2=True)
    assert scores(c.store.node('b',copied)['state'])['friend']==23

def test_grounded_free_action_and_repeat_farming_guard():
    state=ready();intent='我帮助周野检查危险的运输路线，提前向他示警。'
    text='周野收到我的示警，确认运输车避开了危险，认真向我道谢。'
    observations=[{'character_id':'friend','tone':'positive','impact':'meaningful',
                   'intent_evidence':'帮助周野检查危险的运输路线','outcome_evidence':'确认运输车避开了危险','reason':'主动帮助运输队避险'}]
    event={'player_intent':intent}
    apply_observations(state,event,text,observations)
    assert scores(state)['friend']==35
    state['story_turn']+=1;again={'player_intent':intent}
    apply_observations(state,again,text,observations)
    assert scores(state)['friend']==35
    invented=[dict(observations[0],outcome_evidence='正文里没有的帮助')]
    apply_observations(state,{'player_intent':intent},text,invented)
    assert scores(state)['friend']==35

def test_enemies_stay_hostile_and_intimacy_is_only_internal_context():
    state=ready();event={'player_intent':'我赞美裴景珩的判断。'}
    apply_observations(state,event,'裴景珩点头回应我的赞美。',[{'character_id':'rival','tone':'positive','impact':'major',
        'intent_evidence':'赞美裴景珩','outcome_evidence':'点头回应','reason':'赞美'}])
    assert scores(state)['rival']==-18
    assert '亲吻' not in narrative_context(state)['heroine']['attitude']
    state['relationships']['heroine']['affinity']=85
    assert '亲吻' in narrative_context(state)['heroine']['attitude']
    assert '亲吻' not in render_affinity(state)
    assert '更愿意主动帮忙' in narrative_context(dict(state,relationships=dict(state['relationships'],friend={'affinity':70})))['friend']['attitude']

def test_legacy_view_preserves_existing_trust_without_mutating_input():
    state={'relationships':{'heroine':{'trust':3,'events':['旧事件']}}};before=copy.deepcopy(state)
    assert scores(state)['heroine']==24 and state==before

def test_selected_dialogue_can_have_a_small_grounded_effect():
    state=ready();event={'action_id':'story_converse','summary':'与沈霁月交流当前的研究线索'}
    before=scores(state)['heroine']
    apply_observations(state,event,'沈霁月认可了我认真倾听的态度。',[{'character_id':'heroine','tone':'positive','impact':'major',
        'intent_evidence':'交流当前的研究线索','outcome_evidence':'认可了我认真倾听的态度','reason':'认真交流'}])
    assert scores(state)['heroine']==before+3

def test_passive_reading_and_unrelated_character_do_not_gain_affinity():
    state=ready();event={'action_id':'continue_story'}
    apply_observations(state,event,'周野带着运输车出现了。',[{'character_id':'friend','tone':'positive','impact':'major',
        'intent_evidence':'继续故事','outcome_evidence':'周野带着运输车出现了','reason':'人物出现'}])
    assert scores(state)['friend']==28

def test_free_action_affinity_is_committed_with_the_same_story_node(tmp_path):
    class Text:
        async def stream(self,messages):
            yield {'type':'delta','text':'我向沈霁月认真道谢，告诉她自己记住了她的帮助。沈霁月听完，放轻语气回应了我的谢意。'}
            yield {'type':'done'}
        async def structured(self,messages):
            return {'location':'外环废墟','location_evidence':'',
                    'present':[{'id':'protagonist'},{'id':'heroine','evidence':'沈霁月听完'}],
                    'affinity_changes':[{'character_id':'heroine','tone':'positive','impact':'small',
                        'intent_evidence':'认真向沈霁月道谢','outcome_evidence':'放轻语气回应了我的谢意','reason':'诚恳回应救援'}]}
        async def close(self):pass
    async def run():
        e=EngineV2(tmp_path,Settings());await e.text.close();e.text=Text();cid=e.create_v2('a')
        opened=e.controller_v2.act('a',cid,{'action':'opening'},0,'opening')
        before=scores(opened['state'])['heroine']
        frames=[x async for x in e.execute_v2('a',cid,{'action':'free_story','intent':'我认真向沈霁月道谢，说明她的救援对我很重要。'},1)]
        node=frames[-1]['node']
        assert scores(node['state'])['heroine']==before+3
        assert node['event']['affinity_changes'][0]['delta']==3
        assert '_affinity_observations' not in node['meta']['scene']
        await e.close()
    asyncio.run(run())
