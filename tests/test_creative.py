from duhe.creative import direction,template_for,TERMS
from duhe.rules import new_game,apply_action,scene_for
from duhe.prompts import build_messages


def test_preferences_reach_prompt_without_altering_rules():
    a=new_game({'perspective':'first','content_level':'restrained','scene_template':'dialogue'})
    b=new_game()
    a,ea=apply_action(a,'opening','same');b,eb=apply_action(b,'opening','same')
    assert {k:v for k,v in a.items() if k!='preferences'}=={k:v for k,v in b.items() if k!='preferences'}
    msg=build_messages(a,ea,[],'en-US',scene_for(a,ea))
    assert '第一人称' in msg[-1]['content'] and 'Body Tempering' in msg[-1]['content']
    assert direction(a,ea,'en-US')['template_id']=='dialogue'


def test_auto_templates_and_complete_realm_terms():
    s=new_game();assert template_for(s,{'action_id':'opening'})=='rescue'
    assert template_for(s,{'action_id':'scan'})=='exploration'
    assert template_for(s,{'action_id':'train'})=='breakthrough'
    assert template_for(s,{'action_id':'rival_refuse'})=='dialogue'
    from duhe.world import REALMS
    assert all(x in TERMS for x in REALMS)


def test_boss_prompt_keeps_human_face_rules_out_of_global_style():
    from duhe.prompts import image_prompt
    s=new_game(mode='demo',checkpoint='finale');s,event=apply_action(s,'enter_floor')
    prompt,negative=image_prompt({'character_ids':['protagonist','boss'],'description':'塔顶对峙','composition':'主角在右，母核在左'},s,scene_for(s,event))
    assert '精致而克制的五官' not in prompt and '无脸无毛发' in prompt
    assert '白发紫瞳人类女性' not in prompt and '人形母皇' in negative
    assert '画面左侧或主体' not in prompt
    short,_=image_prompt({'character_ids':['protagonist','boss'],'description':'塔顶'},s,scene_for(s,event),limit=500)
    assert '无脸无毛发' in short and '白发紫瞳人类女性' not in short


def test_english_recommendations_reject_chinese_despite_legal_ids():
    import pytest
    from duhe.recommendations import validate,messages
    s,event=apply_action(new_game(),'opening')
    items=[{'action_id':'rest','label':'先休息','intent':'处理伤口'},{'action_id':'train','label':'训练','intent':'练步法'}]
    with pytest.raises(ValueError):validate({'choices':items},s,'en-US')
    good=[{'action_id':'rest','label':'Rest in the shelter','intent':'Dress the wound and rest'},{'action_id':'train','label':'Practice footwork','intent':'Train on the cleared ground'}]
    assert len(validate({'choices':good},s,'en-US'))==2
    assert messages({'id':'n','state':s,'event':event,'text':'Test'},'en-US')[0]['content'].startswith('OUTPUT LANGUAGE: ENGLISH')
