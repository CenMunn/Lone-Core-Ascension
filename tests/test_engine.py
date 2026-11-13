import asyncio
import pytest
from duhe.engine import Engine
from duhe.providers import Settings


def test_offline_opening_and_stale_revision(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        cid=e.create('owner')
        assert e.store.node('owner',cid)['state']['ability_rank']=='UNRANKED'
        events=[v async for v in e.execute('owner',cid,'opening',0,offline=True,with_image=False)]
        assert events[-1]['stage']=='回合已保存'
        node=e.store.node('owner',cid)
        assert '沈霁月' in node['text'] and node['state']['body_stage']=='underfed'
        stale=[v async for v in e.execute('owner',cid,'train',0,offline=True,with_image=False)]
        assert stale[-1]['error'] and e.store.campaign('owner',cid)['revision']==1
        await e.close()
    asyncio.run(run())


def test_partial_network_text_not_committed(tmp_path):
    class Broken:
        async def stream(self,messages):
            yield {'type':'delta','text':'不完整故事'}
            raise RuntimeError('模拟断线')
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings());await e.text.close();e.text=Broken()
        cid=e.create('owner')
        events=[v async for v in e.execute('owner',cid,'opening',0,with_image=False)]
        assert events[-1]['error']
        assert e.store.campaign('owner',cid)['revision']==0
        assert e.budget.status()['text']['used']==1
        await e.close()
    asyncio.run(run())


def test_cancelled_resume_keeps_original_task(tmp_path):
    class Images:
        def __init__(self):self.calls=[]
        async def generate(self,*args,**kwargs):
            self.calls.append(kwargs.get('task_id'))
            yield {'status':'RESUMING','task_id':kwargs.get('task_id')}
            yield {'status':'RUNNING','task_id':kwargs.get('task_id')}
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings());await e.images.close();e.images=Images();cid=e.create('a')
        async for _ in e.execute('a',cid,'opening',0,offline=True,with_image=False):pass
        node=e.store.node('a',cid);e.store.set_image('a',cid,node['id'],{'status':'TIMEOUT','task_id':'old','prompt':'a','negative_prompt':'b'})
        gen=e.make_image('a',cid,node['id']);await anext(gen);await gen.aclose()
        async for _ in e.make_image('a',cid,node['id']):pass
        assert e.images.calls==['old','old']
        assert e.budget.status()['image']['used']==0
        await e.close()
    asyncio.run(run())


def test_same_node_image_requests_do_not_double_submit(tmp_path):
    class Images:
        def __init__(self):self.count=0
        async def generate(self,*args,**kwargs):
            self.count+=1
            yield {'status':'PENDING','task_id':'job'}
            await asyncio.sleep(.05)
            yield {'status':'TIMEOUT','task_id':'job'}
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings());await e.images.close();e.images=Images();cid=e.create('a')
        async for _ in e.execute('a',cid,'opening',0,offline=True,with_image=False):pass
        n=e.store.node('a',cid);e.store.set_image('a',cid,n['id'],{'status':'PREPARED','prompt':'a','negative_prompt':'b'})
        async def collect():return [v async for v in e.make_image('a',cid,n['id'])]
        await asyncio.gather(collect(),collect())
        assert e.images.count==1
        assert e.budget.status()['image']['used']==1
        await e.close()
    asyncio.run(run())


def test_room_creation_immediately_blocks_direct_advance(tmp_path):
    from duhe.app import build_app
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            app=build_app(e)
            callbacks={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
            owner='a'*32;cid=e.create(owner)
            created=callbacks['create_room']({'owner':owner,'cid':cid},'中文')
            session=created[0]
            assert session['room_token']
            frames=[v async for v in callbacks['advance'](session,'opening',0,'offline',False,'中文')]
            assert '协作房间请先投票' in frames[-1][9]
            assert e.store.campaign(owner,cid)['revision']==0
            assert len(e.store.nodes(owner,cid))==1
        finally:await e.close()
    asyncio.run(run())


def test_existing_long_wan21_prompt_is_repaired_before_retry(tmp_path):
    class Images:
        def __init__(self):self.prompts=[]
        async def generate(self,prompt,*args,**kwargs):
            self.prompts.append(prompt)
            yield {'status':'PENDING','task_id':'new-task'}
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings());await e.images.close();e.images=Images()
        try:
            cid=e.create('owner')
            async for _ in e.execute('owner',cid,'opening',0,offline=True,with_image=False):pass
            n=e.store.node('owner',cid)
            e.store.set_image('owner',cid,n['id'],{'status':'FAILED','prompt':'过长旧提示'*150,
                'visual':{'character_ids':['protagonist','heroine'],'description':'废墟细雨'*150}})
            frames=[v async for v in e.make_image('owner',cid,n['id'])]
            assert not frames[-1].get('error')
            assert len(e.images.prompts)==1 and len(e.images.prompts[0])<=500
            assert all(x in e.images.prompts[0] for x in ('陆凌霄','黑发','蓝瞳','沈霁月','白发','紫瞳'))
            assert e.budget.status()['text']['used']==0
        finally:await e.close()
    asyncio.run(run())


def test_invalid_image_parameters_do_not_charge_submission(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings(image_key='test'))
        try:
            cid=e.create('owner');n=e.store.node('owner',cid)
            e.store.set_image('owner',cid,n['id'],{'status':'PREPARED','prompt':'废墟'})
            frames=[v async for v in e.make_image('owner',cid,n['id'],size='1*1')]
            assert frames[-1]['error']
            assert e.budget.status()['image']['used']==0
        finally:await e.close()
    asyncio.run(run())
