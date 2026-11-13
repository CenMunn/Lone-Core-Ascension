"""一次回合只落账一次，图片任务与故事节点独立绑定。"""
import asyncio
import json
import time
import uuid
import logging
from pathlib import Path
from .rules import new_game, actions_for, apply_action, scene_for, validate_state
from .storage import Store
from .providers import Settings, TextService
from .image_jobs import ImageService
from .budget import Budget
from .streaming import timed_events
from . import recommendations
from .content_guard import assert_private,normalize_text,strip_model_settlement
from .progression import info as growth_info
from .scene import build_scene
from .prompts import build_messages, visual_messages, validate_visual, image_prompt, PROMPT_VERSION, assert_story_language, assert_story_event


class Engine:
    def __init__(self, root:Path, settings=None):
        self.root=Path(root).resolve()
        for folder in ('data','output','evaluation'):(self.root/folder).mkdir(parents=True,exist_ok=True)
        self.settings=settings or Settings.from_env(self.root/'.env')
        self.store=Store(self.root/'data/stories.sqlite')
        self.budget=Budget(self.root/'data/api_budget.sqlite')
        self.text=TextService(self.settings);self.images=ImageService(self.settings)
        self.locks={};self.image_locks={}
    def create(self,owner,mode='normal',checkpoint='opening',preferences=None):
        return self.store.create(owner,new_game(preferences,mode,checkpoint))
    async def close(self):
        await self.text.close();await self.images.close()
    def observations(self,owner,cid):
        ancestor_ids={n['id'] for n in self.store.history(owner,cid)}
        return [r['data']['observation'][:300] for r in self.store.feedbacks(owner,cid)
                if r['node_id'] in ancestor_ids and r['data'].get('confirmed')
                and not r['data'].get('tags') and r['data'].get('observation')][-5:]
    async def resolve_action(self,owner,cid,free_text,offline=False):
        if not str(free_text or '').strip():raise ValueError('请先输入你想让陆凌霄做什么。')
        assert_private(free_text)
        node=self.store.node(owner,cid)
        actions=actions_for(node['state'])
        exact=next((a['id'] for a in actions if free_text.strip() in (a['id'],a['label'])),None)
        if exact:return exact
        if offline:raise ValueError('本地演示只支持已列出的行动名称；自由行动解释需要真实文本模型。')
        self.budget.charge('text','自由行动解释')
        async with asyncio.timeout(self.settings.timeout):
            data=await self.text.structured([{'role':'system','content':'你是行动理解器。严格判断用户想做的具体行为能否由当前允许的一个行动直接实现。只输出JSON {"status":"supported或unsupported或clarify","action_id":"行动ID或null","reason":"中文原因"}。只有用户的核心意图与所选行动实际效果一致才可supported；不可为亲吻、交谈或不支持的行为选择休息或扫描等无关动作。无法实现返回unsupported及具体原因，不明确返回clarify。不得自造ID或假装实现额外结果。'},
                {'role':'user','content':json.dumps({'input':free_text[:1000],'story':node['text'][-1800:],'scene':node.get('meta',{}).get('scene') or scene_for(node['state'],node['event']),'allowed':actions},ensure_ascii=False)}])
        if not isinstance(data,dict) or data.get('status')!='supported':
            reason=str(data.get('reason',''))[:200] if isinstance(data,dict) else ''
            raise ValueError(reason or '这个行动当前无法执行，请换一种做法或选择可行行动。')
        if data.get('action_id') not in {a['id'] for a in actions}:raise ValueError('这个行动当前无法执行，请选择界面中的可行行动。')
        return data['action_id']
    async def recommend(self,owner,cid,language='zh-CN'):
        node=self.store.node(owner,cid)
        if not node['text'] or not actions_for(node['state']):return []
        self.budget.charge('text','情景行动推荐')
        async with asyncio.timeout(self.settings.timeout):
            data=await self.text.structured(recommendations.messages(node,language))
        items=recommendations.validate(data,node['state'],language)
        self.store.set_recommendations(owner,cid,node['id'],items)
        return items

    async def execute(self,owner,cid,action_id,expected_revision,*,offline=False,with_image=True,language='zh-CN',operation_id=None,intent=None):
        lock=self.locks.setdefault(cid,asyncio.Lock())
        if lock.locked():
            yield {'stage':'当前回合仍在处理中','error':True};return
        async with lock:
            start=time.monotonic(); text='';node=None
            try:
                camp=self.store.campaign(owner,cid)
                if camp['revision']!=int(expected_revision):raise ValueError('页面进度已改变，请刷新当前分支后再选择。')
                if not offline:self.budget.ensure_available(text=2 if with_image else 1,image=1 if with_image else 0)
                before=self.store.node(owner,cid);op=operation_id or uuid.uuid4().hex
                if action_id.startswith('ai:'):action_id,intent=recommendations.resolve(before,action_id)
                if intent:assert_private(intent)
                state,event=apply_action(before['state'],action_id,op);validate_state(state)
                if intent:event['player_intent']=str(intent)[:400]
                scene=build_scene(state,event,before.get('meta',{}).get('scene'))
                history=self.store.history(owner,cid)
                messages=build_messages(state,event,history,language,scene,self.observations(owner,cid))
                meta={'source':'offline' if offline else 'api','prompt_version':PROMPT_VERSION,'scene':scene,'language':language,
                      'model':None if offline else self.settings.text_model,'usage':None,'system_prompt':messages[0]['content']}
                yield {'stage':'正在书写这一回合','text':'','busy':True}
                if offline:
                    text='【本地规则演示 · 未调用语言模型】\n\n'+event.get('description',event.get('summary',''))
                    text+='\n\n'+('规则结果已记录。画面和文学叙述需切换真实模型生成。' if language=='zh-CN' else 'Local rule preview only. No language or image model has been called.')
                    yield {'stage':'本地规则演示','text':text,'busy':True}
                else:
                    self.budget.charge('text',f'故事:{action_id}')
                    done=False;first=None;last_yield=0
                    async for chunk in timed_events(self.text.stream(messages),self.settings.timeout):
                        if chunk['type']=='delta':
                            text+=chunk['text'];now=time.monotonic()
                            if first is None:first=now-start
                            if now-last_yield>.07:
                                last_yield=now;yield {'stage':'正在书写这一回合','text':normalize_text(text,False),'busy':True}
                        elif chunk['type']=='done':done=True;meta['usage']=chunk.get('usage')
                        elif chunk['type']=='waiting':
                            yield {'stage':f'正在等待文本模型，已用时{chunk["seconds"]}秒（最多{self.settings.timeout:g}秒，可点击停止）','text':text,'busy':True}
                    if not done or not text.strip():raise RuntimeError('正文没有完整返回，本轮状态未提交。')
                    text=normalize_text(text)
                    if action_id=='absorb_core':text=strip_model_settlement(text)
                    assert_private(text)
                    assert_story_language(text,language)
                    assert_story_event(text,event)
                    if action_id=='absorb_core':
                        gains=growth_info(before['state']);level=state['ability_rank'];current=growth_info(state)
                        progress=f"{current['current']}/{current['required']}" if current['required'] else 'UR上限，ULTRA需终战'
                        settlement=(f"【仅陆凌霄可见 · 系统结算】净核 -1；异能EXP +{gains['core_xp']}（当前 {progress}）；修炼EXP +{gains['cultivation_xp']}；能量 -8；污染 +2；当前异能 {level}。" if language=='zh-CN' else f"[Private system settlement] Clean core -1; ability XP +{gains['core_xp']}; cultivation XP +{gains['cultivation_xp']}; energy -8; contamination +2; ability rank {level}.")
                        text+='\n\n> '+settlement
                    meta['first_text_seconds']=first
                meta['text_seconds']=round(time.monotonic()-start,3)
                meta['context_bytes']=sum(len(m['content'].encode('utf-8')) for m in messages)
                meta['context_strategy']='当前状态+最多16条旧事件摘要+最多4轮近文；22KB保守输入预算'
                node=self.store.commit(owner,cid,before['id'],camp['revision'],op,state,text,event,meta)
                yield {'stage':'正文已保存，准备场景插图' if with_image and not offline else '回合已保存','node':node,'text':text,'busy':with_image and not offline}
                if with_image and not offline:
                    async for result in self.make_image(owner,cid,node['id']):yield {**result,'text':text}
                if not offline and actions_for(state):
                    yield {'stage':'正在生成适合当前情景的行动推荐','text':text,'busy':True}
                    try:await self.recommend(owner,cid,language)
                    except Exception as recommendation_error:
                        yield {'stage':f'本轮已保存；AI推荐暂不可用（{type(recommendation_error).__name__}），基础行动可继续使用。','text':text,'busy':False}
                        return
                yield {'stage':'回合已保存','node':self.store.node(owner,cid,node['id']),'text':text,'busy':False}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logging.getLogger(__name__).warning('story_failed campaign=%s action=%s kind=%s',cid,action_id.split(':')[0],type(exc).__name__)
                yield {'stage':f'{"正文已保存；" if node else "本轮未保存；"}{exc}','text':text,'node':node,'error':True,'busy':False}

    async def make_image(self,owner,cid,nid,*,force_new=False,size=None,seed=None,prompt_extend=True):
        lock=self.image_locks.setdefault((cid,nid),asyncio.Lock())
        if lock.locked():
            yield {'stage':'该场景的图片任务正在处理中，请等待或停止后恢复。','error':True,'busy':False};return
        async with lock:
            async for v in self._make_image(owner,cid,nid,force_new=force_new,size=size,seed=seed,prompt_extend=prompt_extend):yield v

    async def _make_image(self,owner,cid,nid,*,force_new=False,size=None,seed=None,prompt_extend=True):
        node=self.store.node(owner,cid,nid);scene=node.get('meta',{}).get('scene') or scene_for(node['state'],node.get('event'))
        record=dict(node.get('image') or {})
        if force_new and record.get('prompt_version') not in (None,PROMPT_VERSION):
            record={}
        try:
            if record.get('status')=='SUCCEEDED' and record.get('path') and Path(record['path']).is_file() and not force_new:
                yield {'stage':'已显示本场景保存的插图。','node':node,'busy':False};return
            if not record.get('prompt'):
                self.budget.ensure_available(text=1,image=1)
                yield {'stage':'正在提炼场景绘图提示词','node':node,'busy':True}
                self.budget.charge('text','场景转绘图提示')
                async with asyncio.timeout(self.settings.timeout):
                    visual=await self.text.structured(visual_messages(node,scene))
                try:
                    data=validate_visual(visual,scene)
                except ValueError:
                    if node['state'].get('schema')!=2:
                        raise
                    # If the model confuses the cast, use a conservative frame derived
                    # from the committed event instead of submitting inconsistent IDs.
                    monster=scene.get('monster') or {}
                    description=(f"{scene.get('location','废墟')}中，角色与{monster['name']}对峙"
                                 if monster.get('name') else f"{scene.get('location','废墟')}中，人物执行当前场景的行动")
                    data=validate_visual({'character_ids':scene.get('present_character_ids',[])[:3],
                                          'description':description,'lighting':'自然环境光',
                                          'composition':'结合场景动作的中景'},scene)
                prompt,negative=image_prompt(data,node['state'],scene,limit=500 if self.settings.image_model.startswith('wanx2.1') else 1900)
                record={'prompt':prompt,'negative_prompt':negative,'visual':data,'status':'PREPARED','prompt_version':PROMPT_VERSION}
                self.store.set_image(owner,cid,nid,record)
            task_id=record.get('task_id') if record.get('status') not in ('FAILED','CANCELED','REVIEW_NEEDED') and not force_new else None
            if not task_id:
                limit=500 if self.settings.image_model.startswith('wanx2.1') else 1900
                if len(record['prompt'])>limit:
                    data=record.get('visual') or {'character_ids':scene.get('present_character_ids',[])[:3],
                                                'description':record['prompt']}
                    data=validate_visual(data,scene)
                    record['prompt'],record['negative_prompt']=image_prompt(data,node['state'],scene,limit=limit)
                    self.store.set_image(owner,cid,nid,record)
                # 本地校验失败不是远端提交尝试，不消耗图片任务额度。
                validator=getattr(self.images,'_parameters',None)
                if validator is not None:validator(size,seed,prompt_extend)
                if not record['prompt'].strip() or len(record.get('negative_prompt',''))>500:
                    raise ValueError('绘图提示词为空或超过模型长度限制。')
                self.budget.charge('image',f'节点:{nid}')
            dest=self.root/'output'/cid/(nid+'-'+uuid.uuid4().hex[:8]+'.png');dest.parent.mkdir(parents=True,exist_ok=True)
            async for part in self.images.generate(record['prompt'],record.get('negative_prompt',''),dest,size=size,seed=seed,prompt_extend=prompt_extend,task_id=task_id):
                record.update(part);record.update({'size':size or self.settings.image_size,'seed':seed,'prompt_extend':prompt_extend})
                self.store.set_image(owner,cid,nid,record)
                yield {'stage':{'PENDING':'图片任务排队中','RUNNING':'正在生成场景插图','SUCCEEDED':'场景插图已保存'}.get(part.get('status'),f"图片状态：{part.get('status')}"),'node':self.store.node(owner,cid,nid),'busy':part.get('status')!='SUCCEEDED'}
        except asyncio.CancelledError:raise
        except Exception as exc:
            tid=getattr(exc,'task_id',None) or record.get('task_id')
            record.update({'status':'TIMEOUT' if tid else 'FAILED','error':str(exc),'task_id':tid})
            self.store.set_image(owner,cid,nid,record)
            yield {'stage':f'正文已保留；配图未完成：{exc}','node':self.store.node(owner,cid,nid),'error':True,'busy':False}
