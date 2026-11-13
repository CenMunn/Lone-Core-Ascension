import asyncio
from duhe.engine import Engine
from duhe.providers import Settings
from duhe.budget import Budget
from duhe.streaming import timed_events


def test_default_budget_has_no_cap_and_keeps_existing_counts(tmp_path):
    path=tmp_path/'usage.sqlite'
    budget=Budget(path)
    for _ in range(25):budget.charge('text','test')
    for _ in range(13):budget.charge('image','test')
    reopened=Budget(path)
    reopened.ensure_available(text=100,image=100)
    assert reopened.status()=={'text':{'used':25,'limit':None},'image':{'used':13,'limit':None}}


def test_continuous_partial_stream_has_whole_turn_deadline(tmp_path):
    class Slow:
        closed=False
        async def stream(self,messages):
            try:
                while True:
                    yield {'type':'delta','text':'未完成'}
                    await asyncio.sleep(.01)
            finally:self.closed=True
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings(timeout=.05));await e.text.close();e.text=Slow()
        try:
            cid=e.create('owner')
            result=[v async for v in e.execute('owner',cid,'opening',0,with_image=False)]
            assert result[-1]['error'] and '超过' in result[-1]['stage']
            assert e.store.campaign('owner',cid)['revision']==0 and e.text.closed
            assert not e.locks[cid].locked()
        finally:await e.close()
    asyncio.run(run())


def test_insufficient_full_pipeline_budget_rejected_before_call(tmp_path):
    class Text:
        calls=0
        async def stream(self,messages):
            self.calls+=1
            yield {'type':'delta','text':'完整的本轮叙述。'}
            yield {'type':'done'}
        async def close(self):pass
    async def run():
        e=Engine(tmp_path,Settings());await e.text.close();e.text=Text()
        e.budget=Budget(tmp_path/'budget-test.sqlite',{'text':1,'image':1})
        try:
            cid=e.create('owner')
            result=[v async for v in e.execute('owner',cid,'opening',0,with_image=True)]
            assert result[-1]['error'] and '额度不足' in result[-1]['stage']
            assert e.text.calls==0 and e.budget.status()['text']['used']==0
            result=[v async for v in e.execute('owner',cid,'opening',0,with_image=False)]
            assert not result[-1].get('error') and e.text.calls==1
        finally:await e.close()
    asyncio.run(run())


def test_waiting_feedback_and_cancellation_close_pending_stream():
    async def run():
        closed=[]
        async def slow():
            try:
                await asyncio.sleep(10)
                yield {'type':'done'}
            finally:closed.append(True)
        stream=timed_events(slow(),1,heartbeat=.01)
        assert (await anext(stream))['type']=='waiting'
        await stream.aclose()
        assert closed==[True]
    asyncio.run(run())
