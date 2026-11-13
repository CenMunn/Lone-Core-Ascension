import asyncio
import pytest
from duhe.rules import new_game,apply_action,scene_for
from duhe.recommendations import validate,resolve
from duhe.engine import Engine
from duhe.providers import Settings
from duhe.profiles import CARDS

def test_dossiers_restore_detail_and_player_identity():
    assert '你操纵的主角就是陆凌霄' in CARDS['protagonist']['text']
    assert all(len(card['text'])>150 for card in CARDS.values())
    assert '高马尾' not in CARDS['heroine']['text']

def test_recommendations_reject_illegal_choices_and_stale_nodes():
    s,_=apply_action(new_game(),'opening')
    items=validate({'choices':[{'action_id':'rest','label':'处理裂开的肋伤','intent':'先包扎再休息'},
                               {'action_id':'train','label':'利用碎石负重训练','intent':'训练步法'},
                               {'action_id':'cheat','label':'升到神话','intent':'作弊'}]},s)
    assert len(items)==2
    n={'id':'one','meta':{'recommendations':items},'state':s}
    assert resolve(n,'ai:one:0')==('rest','先包扎再休息')
    with pytest.raises(ValueError):resolve(n,'ai:other:0')
    with pytest.raises(ValueError):resolve(n,'ai:one:99')

def test_free_action_understanding_provides_immediate_feedback(tmp_path):
    from duhe.app import build_app
    class Fake:
        async def structured(self,m):return {'status':'supported','action_id':'rest','reason':''}
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings());await e.text.close();e.text=Fake()
        try:
            owner='f'*32;cid=e.create(owner)
            async for _ in e.execute(owner,cid,'opening',0,offline=True,with_image=False):pass
            app=build_app(e);fn={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
            stream=fn['advance']({'owner':owner,'cid':cid},'train',1,'api',False,'中文','先处理伤口并休息')
            frame=await anext(stream)
            assert '正在理解' in frame[9]
            frame=await anext(stream)
            assert '进食休整' in frame[9]
            await stream.aclose()
            with pytest.raises(ValueError):await e.resolve_action(owner,cid,'  ')
        finally:await e.close()
    asyncio.run(run())

def test_heroine_fixed_loose_hair_even_in_combat():
    s,_=apply_action(new_game(),'opening');s,_=apply_action(s,'explore')
    scene=scene_for(s)
    assert scene['heroine_hairstyle']=='loose'
