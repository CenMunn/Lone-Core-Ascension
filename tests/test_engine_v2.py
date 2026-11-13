import asyncio
import pytest
from duhe.engine_v2 import EngineV2
from duhe.providers import Settings


def test_frozen_story_suggestion_streams_the_story(tmp_path):
    class Text:
        def __init__(self): self.called = False
        async def stream(self, messages):
            self.called = True
            yield {'type': 'delta', 'text': '沈霁月挡在我身前，我终于脱险。'}
            yield {'type': 'done'}
        async def close(self): pass
    async def run():
        e = EngineV2(tmp_path, Settings()); await e.text.close(); e.text = Text()
        cid = e.create_v2('owner')
        request = {'action': 'frozen_suggestion', 'request': {'action': 'opening'}, 'intent': '先设法从魔兽追杀中活下来'}
        frames = [part async for part in e.execute_v2('owner', cid, request, 0)]
        assert e.text.called
        assert frames[-1]['node']['event']['player_intent'] == request['intent']
        await e.close()
    asyncio.run(run())


def test_incomplete_story_does_not_commit(tmp_path):
    class Broken:
        async def stream(self, messages):
            yield {'type': 'delta', 'text': '没有结束的故事'}
            raise RuntimeError('断线')
        async def close(self): pass
    async def run():
        e = EngineV2(tmp_path, Settings())
        await e.text.close(); e.text = Broken()
        cid = e.create_v2('owner')
        result = [part async for part in e.execute_v2('owner', cid, {'action': 'opening'}, 0)]
        assert result[-1]['error']
        assert e.store.campaign('owner', cid)['revision'] == 0
        await e.close()
    asyncio.run(run())


def test_image_work_does_not_hold_story_lock(tmp_path):
    class Text:
        async def stream(self, messages):
            yield {'type': 'delta', 'text': '沈霁月挡住追来的怪物，我终于活了下来。'}
            yield {'type': 'done'}
        async def close(self): pass
    async def run():
        e = EngineV2(tmp_path, Settings())
        await e.text.close(); e.text = Text()
        started = asyncio.Event(); finish = asyncio.Event()
        async def slow_image(owner, cid, nid):
            started.set(); await finish.wait()
            yield {'stage': '完成'}
        e.make_image = slow_image
        cid = e.create_v2('owner')
        result = [part async for part in e.execute_v2('owner', cid, {'action': 'opening'}, 0, with_image=True)]
        await asyncio.wait_for(started.wait(), 1)
        assert result[-1]['node']['state']['story_turn'] == 1
        assert not e.locks[cid].locked()
        next_result = [part async for part in e.execute_v2('owner', cid, {'action': 'rest'}, 1)]
        assert next_result[-1]['node']['state']['story_turn'] == 1
        finish.set(); await e.close()
    asyncio.run(run())


def test_late_image_is_stored_only_on_its_original_node(tmp_path):
    class Text:
        async def stream(self, messages):
            yield {'type': 'delta', 'text': '沈霁月挡住怪物，我暂时得以喘息。'}
            yield {'type': 'done'}
        async def close(self): pass
    async def run():
        e = EngineV2(tmp_path, Settings()); await e.text.close(); e.text = Text()
        started = asyncio.Event(); finish = asyncio.Event()
        async def delayed(owner, cid, nid):
            started.set(); await finish.wait()
            e.store.set_image(owner, cid, nid, {'status': 'SUCCEEDED', 'path': 'old.png'})
            yield {'stage': '完成'}
        e.make_image = delayed
        cid = e.create_v2('owner')
        frames = [x async for x in e.execute_v2('owner', cid, {'action': 'opening'}, 0, with_image=True)]
        first = frames[-1]['node']['id']; await asyncio.wait_for(started.wait(), 1)
        frames = [x async for x in e.execute_v2('owner', cid, {'action': 'rest'}, 1)]
        current = frames[-1]['node']['id']; finish.set()
        await asyncio.gather(*list(e.background_tasks))
        assert e.store.node('owner', cid, first)['image']['path'] == 'old.png'
        assert e.store.node('owner', cid, current)['image'] is None
        await e.close()
    asyncio.run(run())


def test_visual_cast_mismatch_uses_committed_scene_for_v2(tmp_path):
    class Text:
        async def structured(self, messages):
            return {'character_ids': ['friend'], 'description': '沈霁月出现'}
        async def close(self): pass
    class Image:
        async def generate(self, prompt, negative, dest, **kwargs):
            assert '沈霁月' in prompt and '陆凌霄' in prompt
            yield {'status': 'SUCCEEDED', 'path': str(dest)}
        async def close(self): pass
    async def run():
        e = EngineV2(tmp_path, Settings()); await e.text.close(); await e.images.close()
        e.text = Text(); e.images = Image()
        cid = e.create_v2('owner')
        frames = [x async for x in e.execute_v2('owner', cid, {'action': 'opening'}, 0, offline=True)]
        nid = frames[-1]['node']['id']
        result = [x async for x in e.make_image('owner', cid, nid)]
        assert result[-1]['node']['image']['status'] == 'SUCCEEDED'
        assert result[-1]['node']['image']['visual']['character_ids'] == ['protagonist', 'heroine']
        await e.close()
    asyncio.run(run())


def test_two_sessions_advance_at_the_same_time_without_crossing(tmp_path):
    class Text:
        async def stream(self, messages):
            await asyncio.sleep(.01)
            yield {'type': 'delta', 'text': '沈霁月及时挡住魔兽，我终于脱险。'}
            yield {'type': 'done'}
        async def close(self): pass
    async def run():
        e = EngineV2(tmp_path, Settings()); await e.text.close(); e.text = Text()
        a = e.create_v2('owner-a'); b = e.create_v2('owner-b')
        async def advance(owner, cid):
            return [x async for x in e.execute_v2(owner, cid, {'action': 'opening'}, 0)]
        one, two = await asyncio.gather(advance('owner-a', a), advance('owner-b', b))
        assert one[-1]['node']['id'] != two[-1]['node']['id']
        assert e.store.campaign('owner-a', a)['revision'] == 1
        assert e.store.campaign('owner-b', b)['revision'] == 1
        with pytest.raises(PermissionError):
            e.store.node('owner-a', b)
        await e.close()
    asyncio.run(run())


def test_late_recommendation_stays_bound_to_its_node(tmp_path):
    class Text:
        def __init__(self):
            self.started=asyncio.Event();self.finish=asyncio.Event()
        async def stream(self,messages):
            yield {'type':'delta','text':'沈霁月挡住了魔兽，我终于脱险。'}
            yield {'type':'done'}
        async def structured(self,messages):
            self.started.set();await self.finish.wait()
            return {'choices':[{'key':'ordinary:rest','label':'进食休整','intent':'先吃东西恢复体力'}]}
        async def close(self):pass
    async def run():
        e=EngineV2(tmp_path,Settings());await e.text.close();e.text=Text()
        cid=e.create_v2('owner')
        first=[x async for x in e.execute_v2('owner',cid,{'action':'opening'},0,auto_recommend=True)]
        old=first[-1]['node']['id'];await asyncio.wait_for(e.text.started.wait(),1)
        second=[x async for x in e.execute_v2('owner',cid,{'action':'rest'},1,offline=True)]
        current=second[-1]['node']['id'];e.text.finish.set()
        await asyncio.gather(*list(e.background_tasks))
        assert e.store.node('owner',cid,old)['meta'].get('suggestions_v2')
        assert not e.store.node('owner',cid,current)['meta'].get('suggestions_v2')
        await e.close()
    asyncio.run(run())
