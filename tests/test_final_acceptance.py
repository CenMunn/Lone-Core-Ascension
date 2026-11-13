import asyncio
import pytest
from duhe.engine import Engine
from duhe.providers import Settings
from duhe.rooms import RoomService
from duhe.recommendations import choice_token, resolve


def test_room_ai_vote_preserves_intent_and_rejects_replaced_recommendation(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            cid=e.create('owner')
            async for _ in e.execute('owner',cid,'opening',0,offline=True,with_image=False):pass
            node=e.store.node('owner',cid)
            items=[{'action_id':'rest','label':'先包扎肋伤再休息','intent':'用干净布条包扎肋伤后进食休息'}]
            e.store.set_recommendations('owner',cid,node['id'],items)
            node=e.store.node('owner',cid);token=choice_token(node,0)
            rooms=RoomService(e.store);room=rooms.create('owner',cid);host=room['host_token']
            guest=rooms.join(room['invite_token'],'同行者')['member_token']
            rooms.vote(host,1,token);rooms.vote(guest,1,token)
            locked=rooms.lock_round(host,1)
            assert locked['action_id']=='rest' and locked['intent']==items[0]['intent']
            rooms.finish_round(host,1,False)
            e.store.set_recommendations('owner',cid,node['id'],[{'action_id':'train','label':'新训练建议','intent':'负重步法'}])
            again=rooms.lock_round(host,1,token)
            assert again['operation_id']==locked['operation_id'] and again['intent']==locked['intent']
            async for _ in e.execute('owner',cid,again['action_id'],1,offline=True,with_image=False,operation_id=again['operation_id'],intent=again['intent']):pass
            rooms.finish_round(host,1,True)
            assert e.store.node('owner',cid)['event']['player_intent']==items[0]['intent']
            assert e.store.node('owner',cid)['state']['inventory']['food']==node['state']['inventory']['food']-1
            # Old node IDs and same-node content replacements both invalidate tokens.
            with pytest.raises(ValueError):rooms.vote(guest,2,token)
            e.store.select('owner',cid,node['id'])
            replacement=[dict(items[0],intent='换一种休整方式')]
            e.store.set_recommendations('owner',cid,node['id'],replacement)
            with pytest.raises(ValueError):resolve(e.store.node('owner',cid),token)
        finally:await e.close()
    asyncio.run(run())


def test_vote_cannot_silently_change_when_recommendations_refresh(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            cid=e.create('owner')
            async for _ in e.execute('owner',cid,'opening',0,offline=True,with_image=False):pass
            n=e.store.node('owner',cid)
            e.store.set_recommendations('owner',cid,n['id'],[{'action_id':'rest','label':'休整','intent':'包扎休息'}])
            token=choice_token(e.store.node('owner',cid),0)
            r=RoomService(e.store);h=r.create('owner',cid)['host_token'];r.vote(h,1,token)
            e.store.set_recommendations('owner',cid,n['id'],[{'action_id':'train','label':'训练','intent':'练习步法'}])
            with pytest.raises(ValueError):r.lock_round(h,1)
        finally:await e.close()
    asyncio.run(run())


def test_late_free_action_does_not_replace_new_campaign(tmp_path):
    from duhe.app import build_app
    async def run():
        e=Engine(tmp_path,Settings())
        class SlowResolver:
            async def structured(self,m):
                await gate.wait();return {'action_id':'rest'}
            async def close(self):pass
        gate=asyncio.Event()
        try:
            await e.text.close();e.text=SlowResolver();owner='a'*32;cid=e.create(owner)
            async for _ in e.execute(owner,cid,'opening',0,offline=True,with_image=False):pass
            app=build_app(e);fn={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
            stream=fn['advance']({'owner':owner,'cid':cid},'train',1,'api',False,'中文','包扎后休息')
            assert '正在理解' in (await anext(stream))[9]
            pending=asyncio.create_task(anext(stream))
            new=fn['begin']({'owner':owner},'normal','opening','谨慎观察','克制细腻','漫画','中文')
            gate.set()
            with pytest.raises(StopAsyncIteration):await pending
            assert new[0]['cid']!=cid and e.store.campaign(owner,cid)['revision']==1
        finally:await e.close()
    asyncio.run(run())


def test_cancel_partial_stream_then_retry_once_and_keep_failed_image_state(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        class Stream:
            async def stream(self,m):
                yield {'type':'delta','text':'还未完成的文字'}
                await asyncio.sleep(100)
            async def close(self):pass
        class FailedImage:
            def validate_submission(self,*a,**k):pass
            async def generate(self,*a,**k):
                yield {'status':'PENDING','task_id':'persisted-task'}
                raise TimeoutError('模拟图片排队超时')
            async def close(self):pass
        try:
            await e.text.close();e.text=Stream();cid=e.create('owner')
            before=e.store.node('owner',cid)
            gen=e.execute('owner',cid,'opening',0,with_image=False)
            await anext(gen);await anext(gen);await gen.aclose()
            assert e.store.node('owner',cid)['state']==before['state']
            async for _ in e.execute('owner',cid,'opening',0,offline=True,with_image=False,operation_id='only-once'):pass
            committed=e.store.node('owner',cid)
            async for _ in e.execute('owner',cid,'opening',0,offline=True,with_image=False,operation_id='only-once'):pass
            assert e.store.campaign('owner',cid)['revision']==1
            e.store.set_image('owner',cid,committed['id'],{'status':'PREPARED','prompt':'废墟'})
            await e.images.close();e.images=FailedImage()
            async for _ in e.make_image('owner',cid,committed['id']):pass
            after=e.store.node('owner',cid)
            assert after['state']==committed['state'] and after['text']==committed['text']
            assert after['image']['task_id']=='persisted-task'
        finally:await e.close()
    asyncio.run(run())


def test_leave_room_suppresses_delayed_recommendation_frame(tmp_path):
    from duhe.app import build_app
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            owner='a'*32;cid=e.create(owner)
            async for _ in e.execute(owner,cid,'opening',0,offline=True,with_image=False):pass
            app=build_app(e);fn={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
            session=fn['create_room']({'owner':owner,'cid':cid},'中文')[0]
            async def delayed(*a):return []
            e.recommend=delayed
            gen=fn['refresh_recommendations'](session,'api','中文');await anext(gen)
            left=fn['leave_room'](session,'中文')[0];assert 'room_token' not in left
            with pytest.raises(StopAsyncIteration):await anext(gen)
        finally:await e.close()
    asyncio.run(run())
