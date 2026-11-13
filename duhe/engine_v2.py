"""Streaming narrative and node-bound asynchronous illustration for v2."""
import asyncio
import time
import uuid

from .controller_v2 import ControllerV2
from .engine import Engine
from .content_guard import assert_private, normalize_text
from .prompts import build_messages, assert_story_event, assert_story_language, PROMPT_VERSION
from .streaming import timed_events

NARRATIVE_ACTIONS = {'opening', 'first_hunt_report', 'rival_refuse', 'rival_trade', 'help_couriers',
                     'secure_samples', 'reject_harvest', 'heroine_sss', 'heroine_ur', 'wall_prepare',
                     'start_encounter', 'realm_trial', 'tower_segment', 'final_purify', 'epilogue'}
NARRATIVE_ACTIONS.update(('continue_story','story_investigate','story_converse','free_story'))


class EngineV2(Engine):
    def __init__(self, root, settings=None):
        super().__init__(root, settings)
        self.controller_v2 = ControllerV2(self.store)
        self.background_tasks = set()
        self.speech_jobs = {}
        self.image_tasks = {}
        self.recommendation_jobs = {}
        self.recommendation_tasks = {}
        self.recommendation_semaphore = asyncio.Semaphore(2)

    def create_v2(self, owner, preferences=None):
        return self.controller_v2.create(owner, preferences)

    async def derive_free_scene(self,text,frame,state,affinity_event=None):
        from .free_story import scene_messages,verified_scene
        from .affinity import evaluation_context
        try:
            self.budget.ensure_available(text=1);self.budget.charge('text','自由行动场景核对')
            async with asyncio.timeout(min(20,self.settings.timeout)):
                data=await self.text.structured(scene_messages(text,frame,evaluation_context(state,affinity_event) if affinity_event else None))
            result=verified_scene(text,data,frame,state)
            if affinity_event:result['_affinity_observations']=data.get('affinity_changes',[])
            return result
        except Exception:
            return dict(frame,scene_verified=False,scene_note='正文已保存；场景人物暂未核对，可重试配图。')

    async def make_image(self,owner,cid,nid,**kwargs):
        node=self.store.node(owner,cid,nid);frame=node.get('meta',{}).get('scene') or {}
        if frame.get('scene_verified') is False:
            frame=await self.derive_free_scene(node['text'],frame,node['state'])
            self.store.set_scene(owner,cid,nid,frame)
            if frame.get('scene_verified') is False:
                self.store.set_image(owner,cid,nid,{'status':'FAILED','error':'场景人物尚未核对，请重试配图；正文可以继续。'})
                yield {'stage':'场景人物尚未核对，请重试配图；正文可以继续。','error':True}
                return
        async for update in super().make_image(owner,cid,nid,**kwargs):yield update

    async def recommend_tactics(self, owner, cid, node_id, language='zh-CN'):
        from .tactics_v2 import messages, validate_tactics
        node = self.store.node(owner, cid, node_id)
        if not node['state'].get('combat'):
            raise ValueError('当前不在战斗中')
        self.budget.ensure_available(text=1)
        self.budget.charge('text', '新版战术推荐')
        async with asyncio.timeout(self.settings.timeout):
            choices = validate_tactics(await self.text.structured(messages(node, language)), node['state'])
        self.store.set_tactics_v2(owner, cid, node_id, choices)
        return choices

    async def recommend_suggestions(self, owner, cid, node_id, language='zh-CN'):
        from .suggestions_v2 import messages, validate
        node = self.store.node(owner, cid, node_id)
        self.budget.ensure_available(text=1); self.budget.charge('text', '新版情景推荐')
        async with asyncio.timeout(self.settings.timeout):
            choices = validate(await self.text.structured(messages(node, language)), node['state'])
        self.store.set_suggestions_v2(owner, cid, node_id, choices)
        return choices

    async def understand_free_tactic(self, owner, cid, node_id, intent):
        import json
        from .tactics_v2 import validate_tactics, tactic_token
        intent = str(intent or '').strip()
        if not intent:
            raise ValueError('请先描述要执行的行动')
        assert_private(intent)
        node = self.store.node(owner, cid, node_id)
        if not node['state'].get('combat'):
            raise ValueError('自由战术目前仅支持战斗中；请使用当前普通行动或剧情行动。')
        system = ('判断玩家的战斗意图是否可在当前单次交锋直接实现；不能实现、目标不明确或要求不存在的能力时，'
                  '只返回JSON {"status":"unsupported或clarify","reason":"原因"}。可实现时返回'
                  '{"status":"supported","choice":{"label":"名称","intent":"忠实保留用户的目标和做法",'
                  '"multiplier":1.0,"energy_cost":8,"effect":"none"}}。倍率0.8至1.4，消耗4至20整数，'
                  '倍率大于1.2至少10能量；effect只能是none或weaken，weaken至少8能量。不能偷偷更换用户行动。')
        self.budget.ensure_available(text=1); self.budget.charge('text', '新版自由战术理解')
        async with asyncio.timeout(self.settings.timeout):
            data = await self.text.structured([{'role': 'system', 'content': system},
                {'role': 'user', 'content': json.dumps({'玩家行动': intent[:1000], '场景': node.get('meta', {}).get('scene'),
                     '战斗': node['state']['combat'], '能量': node['state']['energy'],
                     '已掌握能力': node['state']['skills']}, ensure_ascii=False)}])
        if not isinstance(data, dict) or data.get('status') != 'supported':
            raise ValueError(str(data.get('reason', '当前无法理解或执行此行动。'))[:200] if isinstance(data, dict) else '无法理解此行动。')
        if isinstance(data.get('choice'), dict):
            data['choice']['intent'] = intent[:300]
        choices = validate_tactics({'choices': [data.get('choice')]}, node['state'])
        self.store.set_tactics_v2(owner, cid, node_id, choices)
        return tactic_token(self.store.node(owner, cid, node_id), 0), choices[0]

    def _spawn_image(self, owner, cid, nid):
        key = (owner, cid, nid)
        existing = self.image_tasks.get(key)
        if existing is not None and not existing.done():
            return
        async def work():
            async for _ in self.make_image(owner, cid, nid):
                pass
        task = asyncio.create_task(work())
        self.image_tasks[key] = task
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    def stop_image(self, owner, cid, nid):
        self.store.node(owner, cid, nid)
        task = self.image_tasks.get((owner, cid, nid))
        if task and not task.done():
            task.cancel()
            return True
        return False

    def _spawn_recommendation(self, owner, cid, nid, language):
        key = (owner, cid, nid)
        if self.recommendation_jobs.get(key, {}).get('status') == 'running':
            return
        self.recommendation_jobs[key] = {'status': 'running'}
        async def work():
            try:
                async with self.recommendation_semaphore:
                    node = self.store.node(owner, cid)
                    if node['id'] != nid:
                        self.recommendation_jobs[key] = {'status': 'stale'}; return
                    if node['state'].get('combat'):
                        await self.recommend_tactics(owner, cid, nid, language); kind = 'tactics'
                    else:
                        from .suggestions_v2 import legal_requests
                        if not legal_requests(node['state']):
                            self.recommendation_jobs[key] = {'status': 'empty'}; return
                        await self.recommend_suggestions(owner, cid, nid, language); kind = 'suggestions'
                    self.recommendation_jobs[key] = {'status': 'succeeded', 'kind': kind}
            except asyncio.CancelledError:
                self.recommendation_jobs[key] = {'status': 'cancelled'}; raise
            except Exception as exc:
                self.recommendation_jobs[key] = {'status': 'failed', 'error': type(exc).__name__}
        task = asyncio.create_task(work()); self.recommendation_tasks[key] = task; self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    def cancel_recommendation(self, owner, cid, nid):
        task = self.recommendation_tasks.get((owner, cid, nid))
        if task and not task.done():
            task.cancel()

    def _spawn_speech(self, owner, cid, nid):
        from .speech_v2 import segment_messages, validate_segments, render_segments, describe_speech_error
        key = (owner, cid, nid)
        if self.speech_jobs.get(key, {}).get('status') in ('running', 'succeeded'):
            return
        self.speech_jobs[key] = {'status': 'running'}
        async def work():
            try:
                node = self.store.node(owner, cid, nid)
                text = node['text']; speech_scene=node.get('meta', {}).get('scene') or {}
                present = speech_scene.get('present_character_ids', []) if speech_scene.get('scene_verified') is not False else []
                try:
                    self.budget.ensure_available(text=1); self.budget.charge('text', '新版配音分段')
                    async with asyncio.timeout(self.settings.timeout):
                        data = await self.text.structured(segment_messages(node))
                    segments = validate_segments(text, data.get('segments') if isinstance(data, dict) else None, present)
                    segmentation = '模型分段（已核对正文与在场人物）'
                except (ValueError, RuntimeError, TimeoutError):
                    segments = [{'speaker_id': 'narrator', 'kind': 'narration', 'text': text}]
                    segmentation = '分段不可用，退回旁白'
                try:
                    path = await render_segments(self.root, text, segments, present, node.get('meta', {}).get('language', 'zh-CN'))
                except Exception:
                    if len(segments) == 1 and segments[0]['speaker_id'] == 'narrator':
                        raise
                    segments = [{'speaker_id': 'narrator', 'kind': 'narration', 'text': text}]
                    segmentation = '角色配音未完成，已改用旁白'
                    path = await render_segments(self.root, text, segments, present, node.get('meta', {}).get('language', 'zh-CN'))
                self.speech_jobs[key] = {'status': 'succeeded', 'path': path, 'segmentation': segmentation}
            except asyncio.CancelledError:
                self.speech_jobs[key] = {'status': 'cancelled'}
                raise
            except Exception as exc:
                self.speech_jobs[key] = {'status': 'failed', 'error': type(exc).__name__, 'message': describe_speech_error(exc)}
        task = asyncio.create_task(work()); self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def close(self):
        tasks = list(self.background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await super().close()

    async def execute_v2(self, owner, cid, request, revision, *, offline=False,
                         with_image=False, auto_voice=False, auto_recommend=False, operation_id=None, language='zh-CN'):
        lock = self.locks.setdefault(cid, asyncio.Lock())
        if lock.locked():
            yield {'stage': '当前操作仍在处理中', 'error': True}
            return
        async with lock:
            text = ''; node = None
            try:
                op = operation_id or uuid.uuid4().hex
                before, state, event, frame = self.controller_v2.prepare(owner, cid, request, revision, op)
                action = event.get('action_id', request['action']) if request['action'] in ('use_suggestion', 'frozen_suggestion') else request['action']
                narrative = action in NARRATIVE_ACTIONS or event.get('outcome') in ('victory', 'defeat')
                meta = {'source': 'offline' if offline else 'api', 'scene': frame,
                        'prompt_version': PROMPT_VERSION, 'language': language}
                if not narrative:
                    text = event.get('summary') or '操作已结算：' + action
                    meta['source'] = 'v2-rules'
                elif offline:
                    text = '【离线规则演示】\n\n' + (event.get('description') or event.get('summary', ''))
                else:
                    self.budget.ensure_available(text=1)
                    history = self.store.history(owner, cid)
                    from .story_flow import is_story_node
                    history = [n for n in history if is_story_node(n)]
                    from .cast_director import choose_focus
                    focus=choose_focus(state,event,history,frame)
                    if focus:event['cast_focus']=focus
                    messages = build_messages(state, event, history, language, frame, self.observations(owner, cid))
                    self.budget.charge('text', '新版剧情:' + action)
                    complete = False
                    start = time.monotonic()
                    last_yield = 0.0
                    async for chunk in timed_events(self.text.stream(messages), self.settings.timeout):
                        if chunk['type'] == 'delta':
                            text += chunk['text']
                            now = time.monotonic()
                            if now - last_yield >= .07:
                                last_yield = now
                                yield {'stage': '正在书写这一回合', 'text': normalize_text(text, False), 'busy': True}
                        elif chunk['type'] == 'done':
                            complete = True; meta['usage'] = chunk.get('usage')
                        elif chunk['type'] == 'waiting':
                            yield {'stage': '正在等待文本模型', 'text': text, 'busy': True}
                    if not complete or not text.strip():
                        raise RuntimeError('正文没有完整返回，本次操作未提交。')
                    text = normalize_text(text)
                    assert_private(text); assert_story_language(text, language); assert_story_event(text, event)
                    meta['model'] = self.settings.text_model
                    meta['text_seconds'] = round(time.monotonic() - start, 3)
                    from .affinity import evaluation_intent
                    if event.get('free_story') or event.get('cast_focus') or evaluation_intent(event):
                        yield {'stage':'正文已生成，正在核对新场景的人物与地点。','text':text,'busy':True}
                        evaluate_affinity=bool(evaluation_intent(event)) and not bool(event.get('affinity_changes'))
                        frame=await self.derive_free_scene(text,frame,state,event if evaluate_affinity else None)
                        observations=frame.pop('_affinity_observations',[])
                        if evaluate_affinity:
                            from .affinity import apply_observations
                            apply_observations(state,event,text,observations,frame)
                            event['affinity_evaluation']='complete' if frame.get('scene_verified') else 'unavailable'
                        meta['scene']=frame
                if event.get('continuation'):
                    event['narrative_excerpt']=text if len(text)<=480 else text[:240]+'…'+text[-240:]
                node = self.store.commit(owner, cid, before['id'], revision, op, state, text, event, meta)
                if narrative and not offline and with_image:
                    self._spawn_image(owner, cid, node['id'])
                if narrative and not offline and auto_voice:
                    self._spawn_speech(owner, cid, node['id'])
                if not offline and auto_recommend and (narrative or state.get('combat')) and not state['flags'].get('victory'):
                    self._spawn_recommendation(owner, cid, node['id'], language)
                from .affinity import feedback
                stage='剧情已保存；配图在后台生成。' if narrative and not offline and with_image else '操作已保存'
                if feedback(event):stage+='；'+feedback(event)
                if event.get('affinity_evaluation')=='unavailable':stage+='；本轮好感度评估暂不可用。'
                yield {'stage': stage,
                       'text': text, 'node': node, 'busy': False}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield {'stage': f'{"正文已保存；" if node else "操作未保存；"}{exc}',
                       'text': text, 'node': node, 'error': True, 'busy': False}
