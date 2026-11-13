import copy
import pytest
from duhe.rules import new_game,apply_action,actions_for,validate_state
from duhe.content_guard import assert_private,normalize_text,leaks_secret
from duhe.progression import info,START


@pytest.mark.parametrize('text',['向沈霁月询问系统与污染的基础常识','向周野展示独行进化系统','沈霁月知道他有系统','Tell Shen Jiyue about my system'])
def test_system_disclosure_is_rejected(text):
    with pytest.raises(ValueError):assert_private(text)


@pytest.mark.parametrize('text',['在意识中默读系统提示','询问沈霁月公开的污染知识','与周野讨论修复供电系统','Ask the system to scan the area','他不会向沈霁月透露系统','Never tell Shen about my system'])
def test_private_use_and_public_knowledge_are_allowed(text):assert_private(text)


def test_character_integrity_and_uncertain_text():
    assert normalize_text('拿起维���刀')=='拿起维修刀'
    assert normalize_text('？？？危险???')=='……危险……'
    with pytest.raises(ValueError):normalize_text('陌生的�符号')
    assert '〔文字缺失〕' in normalize_text('陌生�符号',False)


def test_net_core_gives_both_xp_and_automatic_ability_rank_with_real_costs():
    s,_=apply_action(new_game(),'opening');s['inventory']['clean_core']=5
    before=copy.deepcopy(s)
    s,event=apply_action(s,'absorb_core','absorb-once')
    assert s['inventory']['clean_core']==before['inventory']['clean_core']-1
    assert s['ability_xp']==20 and s['xp']==before['xp']+5
    assert s['energy']==before['energy']-8 and s['pollution']==before['pollution']+2
    with pytest.raises(ValueError):apply_action(s,'absorb_core','absorb-once')
    s,_=apply_action(s,'absorb_core');s,event=apply_action(s,'absorb_core')
    assert s['ability_rank']=='E' and s['max_hp']==106 and s['realm_index']==0
    assert '异能EXP' in event['summary'] and info(s)['core_xp']==30
    assert s['body_stage']=='underfed' # Energy alone is not years of training.


def test_legacy_rank_is_preserved_without_retroactive_core_rewards():
    s=new_game(mode='demo',checkpoint='wall')
    for k in ('growth_version','ability_xp','cores_absorbed'):s.pop(k)
    rank=s['ability_rank'];validate_state(s)
    updated,event=apply_action(s,'scan')
    assert updated['ability_rank']==rank and updated['cores_absorbed']==0
    assert updated['ability_xp']==START[rank]
    assert 'ability_xp' not in s
    assert 'ability_xp' not in event['changes']


def test_status_gauges_and_pollution_explanations_match_action_boundaries():
    from duhe.status_panel import render,pollution_help
    s,_=apply_action(new_game(),'opening');s['inventory']['clean_core']=2
    for pollution in (64,65,84,85,89,90,94,95,100):
        s['pollution']=pollution;ids={a['id'] for a in actions_for(s)}
        assert ('absorb_core' in ids)==(pollution<65)
        assert ('explore' in ids)==(pollution<90)
    panel=render(s)
    assert all(x in panel for x in ('<svg','<progress','生命 HP','异能EXP','修炼EXP','污染','点击查看说明'))
    assert '90起' in pollution_help() and '额外扣8' in pollution_help()


def test_leaking_legacy_recommendation_cannot_be_resolved_or_executed(tmp_path):
    from duhe.recommendations import resolve,validate
    s,event=apply_action(new_game(),'opening')
    item={'action_id':'train','label':'向沈霁月询问系统与污染的基础常识','intent':'做感知练习'}
    n={'id':'legacy','state':s,'meta':{'recommendations':[item]}}
    with pytest.raises(ValueError):resolve(n,'ai:legacy:0')
    with pytest.raises(ValueError):validate({'choices':[item]},s)


def test_undecodable_complete_prose_does_not_commit_or_spend_game_resources(tmp_path):
    import asyncio
    from duhe.engine import Engine
    from duhe.providers import Settings
    async def run():
        e=Engine(tmp_path,Settings())
        class Text:
            async def stream(self,m):
                yield {'type':'delta','text':'无法判断的�片段'}
                yield {'type':'done','usage':{}}
            async def close(self):pass
        try:
            await e.text.close();e.text=Text();cid=e.create('owner');before=e.store.node('owner',cid)
            frames=[x async for x in e.execute('owner',cid,'opening',0,with_image=False)]
            assert frames[-1]['error'] and '缺字' in frames[-1]['stage']
            assert e.store.node('owner',cid)['state']==before['state']
            assert e.store.campaign('owner',cid)['revision']==0
        finally:await e.close()
    asyncio.run(run())


def test_absorption_uses_growth_template_and_checks_missing_main_action():
    from duhe.creative import template_for
    from duhe.prompts import assert_story_event
    assert template_for(new_game(),{'action_id':'absorb_core'})=='breakthrough'
    event={'action_id':'absorb_core','ability_rank_change':{'from':'F-','to':'E'}}
    with pytest.raises(ValueError):assert_story_event('他观察仓库，准备绕行。',event)
    with pytest.raises(ValueError):assert_story_event('他吸收一枚净核，收好维修刀。',event)
    assert_story_event('他吸收净核，异能升到E级。',event)


def test_program_settlement_is_not_replayed_as_narrative_history():
    from duhe.content_guard import strip_model_settlement,safe_history
    text='他在意识中吸收净核。\n\n> 【仅陆凌霄可见 · 系统结算】错误的数字。\n\n> 【仅陆凌霄可见 · 系统结算】程序数据。'
    assert normalize_text(text).count('系统结算')==1
    assert strip_model_settlement(text)=='他在意识中吸收净核。'
    assert '系统结算' not in safe_history(text)
