import tempfile
from pathlib import Path
import pytest
from duhe.prompts import character_card, build_messages, image_prompt, validate_visual, assert_story_language
from duhe.budget import Budget


def state():
    return {'body_stage': 'underfed', 'equipment': [], 'wounds': ['左肩擦伤'], 'ability_rank':'UNRANKED',
            'heroine_ability_rank':'SS', 'known_facts':[], 'relationships':{}, 'preferences':{}}


def test_character_state_does_not_invent_growth():
    s=state()
    calm={'combat_active':False,'core_power_active':True}
    card=character_card('protagonist',s,calm)
    assert '瘦削' in card and '不发光' in card
    s['body_stage']='trained'
    assert '肌肉' in character_card('protagonist',s,{'combat_active':True,'core_power_active':True})
    assert '蓝色流光' in character_card('protagonist',s,{'combat_active':True,'core_power_active':True})


def test_heroine_hair_tracks_scene():
    assert '披散至腰际' in character_card('heroine',state(),{'heroine_hairstyle':'high_ponytail'})
    assert '披散' in character_card('heroine',state(),{'heroine_hairstyle':'loose'})


def test_visual_does_not_add_absent_people():
    scene={'present_character_ids':['protagonist']}
    with pytest.raises(ValueError):
        validate_visual({'character_ids':['heroine'],'description':'双人'},scene)
    data=validate_visual({'character_ids':['protagonist'],'description':'废墟'},scene)
    prompt,negative=image_prompt(data,state(),scene)
    assert '黑发' in prompt and '蓝瞳' in prompt
    assert '沈霁月' not in prompt


def test_bounded_context_keeps_current_state():
    history=[{'id':str(i),'text':'旧文'*3000,'event':{'result':'探索'},'state':{}} for i in range(30)]
    messages=build_messages(state(),{'kind':'rest'},history,'zh-CN',{'present_character_ids':['protagonist']})
    assert sum(len(m['content']) for m in messages)<24000
    assert 'UNRANKED' in str(messages)


def test_budget_is_persistent_and_failed_attempt_consumes():
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'budget.sqlite'
        b=Budget(p,{'text':2,'image':1})
        b.charge('text','test');b.charge('text','failure')
        with pytest.raises(RuntimeError):Budget(p,{'text':2,'image':1}).charge('text','extra')
        assert b.status()['text']['used']==2
        assert b.status()['image']['used']==0

def test_english_contract_rejects_wrong_language():
    with pytest.raises(ValueError):assert_story_language('废墟里的故事。'*20,'en-US')
    assert_story_language('The survivor watched the frost fade from the ruined gate while his companion prepared a safe route back to the shelter. He kept his old knife ready and took one careful step forward.','en-US')

def test_long_operation_ledger_not_sent_to_model():
    s=state();s['completed_operations']=['a'*32]*1000;s['claimed_rewards']=['tower:'+str(i) for i in range(100)]
    m=build_messages(s,{'kind':'train'},[],'en-US',{'present_character_ids':['protagonist']})
    assert 'completed_operations' not in m[-1]['content']
    assert 'OUTPUT LANGUAGE: ENGLISH ONLY' in m[-1]['content']


@pytest.mark.parametrize('combat',[False,True])
def test_wan21_prompt_preserves_both_character_identities_within_limit(combat):
    from duhe.rules import new_game,apply_action,scene_for
    s,event=apply_action(new_game(),'opening');scene=scene_for(s,event)
    scene.update(combat_active=combat,core_power_active=combat,
                 heroine_hairstyle='high_ponytail' if combat else 'loose')
    data=validate_visual({'character_ids':['protagonist','heroine'],
                         'description':'废墟上落着冰冷细雨。'*100,
                         'lighting':'清冷月光'*100,'composition':'中景'*100},scene)
    prompt,_=image_prompt(data,s,scene,limit=500)
    assert len(prompt)<=500
    for detail in ('陆凌霄','黑发','蓝瞳','瘦削','沈霁月','白发','紫瞳'):
        assert detail in prompt
    assert ('蓝色流光' if combat else '不发光') in prompt
    assert '披散至腰际' in prompt and '高马尾' not in prompt
    assert '维修夹克' in prompt
    assert 'repair_jacket' not in prompt and 'repair_knife' not in prompt


def test_image_costume_tracks_actual_armor_without_internal_ids():
    from duhe.rules import new_game,scene_for
    s=new_game(mode='demo',checkpoint='guardian');scene=scene_for(s)
    data={'character_ids':['protagonist'],'description':'塔内站立'}
    for limit in (500,1900):
        prompt,_=image_prompt(data,s,scene,limit=limit)
        assert '黑铁核心护甲' in prompt
        assert 'black_iron_armor' not in prompt and 'repair_knife' not in prompt
    card=character_card('protagonist',s,{'combat_active':False})
    assert '黑铁核心护甲' in card and 'black_iron_armor' not in card


def test_complete_normal_campaign_context_stays_within_22kb():
    from duhe.rules import new_game,apply_action,actions_for,scene_for
    s=new_game();history=[];peak=0
    for step in range(3500):
        if s['flags'].get('victory'):break
        ids={a['id'] for a in actions_for(s)}
        if s['combat']:
            c=s['combat'];key='guard' if c['guardian'] and not c['broken'] else 'skill' if 'skill' in ids else 'attack'
        elif 'opening' in ids:key='opening'
        elif s['inventory']['food']<2:key='forage'
        elif (s['energy']<28 or s['hp']<min(s['max_hp'],110)) and 'rest' in ids:key='rest'
        elif s['pollution']>=40 and 'purify' in ids:key='purify'
        elif 'absorb_core' in ids and s['ability_rank'] != 'UR' and s['realm_index']*4+s['realm_stage']>=4: key='absorb_core'
        elif 'craft' in ids:key='craft'
        elif 'heroine_sss' in ids:key='heroine_sss'
        elif 'wall_defend' in ids:key='wall_defend'
        elif 'heroine_ur' in ids:key='heroine_ur'
        elif 'final_purify' in ids:key='final_purify'
        elif 'breakthrough' in ids:key='breakthrough'
        elif 'enter_floor' in ids:key='enter_floor'
        elif 'trial' in ids:key='trial'
        elif s['inventory']['clean_core']<8 and 'refine' in ids:key='refine'
        elif s['xp']<200 and 'train' in ids:key='train'
        elif 'explore' in ids:key='explore'
        else:key='forage'
        s,event=apply_action(s,key,f'op-{step}')
        for language in ('zh-CN','en-US'):
            messages=build_messages(s,event,history,language,scene_for(s,event),['墙上保留着旧划痕。'])
            size=sum(len(m['content'].encode('utf-8')) for m in messages)
            peak=max(peak,size)
            assert size<=22000,(s['turn'],language,size)
            assert event['summary'] in messages[-1]['content']
        history.append({'id':str(step),'event':event,'text':'风吹过废墟，脚步声渐渐远去。'*150})
    assert s['flags'].get('victory') and s['ability_rank']=='ULTRA'
    assert s['cleared_floors']==list(range(1,101))
    assert s['turn']>100 and peak<=22000

def test_ending_is_not_available_before_final_event():
    from duhe.prompts import assert_story_event
    ending='独行试炼完成。人类文明存续判定：通过。'
    with pytest.raises(ValueError):assert_story_event(ending,{'action_id':'absorb:one'})
    assert_story_event(ending,{'action_id':'final_purify'})
    m=build_messages(state(),{'action_id':'train'},[],'zh-CN',{'present_character_ids':['protagonist']})
    assert ending not in m[0]['content']
