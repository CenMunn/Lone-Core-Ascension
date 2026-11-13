"""实验四 Gradio Blocks 入口。"""
import asyncio
import html
import json
import os
import re
import uuid
from pathlib import Path
os.environ.setdefault('GRADIO_ANALYTICS_ENABLED','False')
os.environ.setdefault('GRADIO_TEMP_DIR',str(Path(__file__).resolve().parents[1]/'data/gradio_cache'))
import gradio as gr
from .engine import Engine
from .rules import actions_for,scene_for,validate_state
from .world import REALMS,CHARACTERS
from .rooms import RoomService
from .audio import ambient
from .speech import narrate
from .art_style import STYLE_LABEL
from .profiles import profile_text,portrait_path
from .recommendations import choice_token,resolve as resolve_recommendation
from .creative import TEMPLATES,TERMS
from .status_panel import render as render_status,WORLD_INTRO
from .content_guard import leaks_secret,normalize_text

ROOT=Path(__file__).resolve().parents[1]
CSS=(ROOT/'duhe/ui.css').read_text('utf-8')
ACTION_EN={'opening':'The first encounter','train':'Train and review','rest':'Eat and recover','forage':'Scavenge for food','explore':'Explore this region','trial':'Solo trial','scan':'Scan and review tasks','refine':'Purify a core','breakthrough':'Advance cultivation','forge':'Forge equipment','heroine_sss':'Support Shen Jiyue → SSS','wall_defend':'Defend the north wall','enter_floor':'Enter the next tower floor','attack':'Attack','guard':'Guard','dodge':'Dodge','skill':'Use ability','retreat':'Retreat','absorb':'Fuse an ability echo'}
ACTION_EN.update(detox='Recover from contamination',purify='Purify contamination',craft='Craft black-iron armor',rival_refuse='Reject Pei Jingheng’s contract',rival_trade='Negotiate a limited trade',reject_harvest='Reject sacrificing civilians',heroine_ur='Support Shen Jiyue → UR',final_purify='Purify the Final Core',absorb_core='Absorb a clean core · Gain ability and cultivation XP')
ACTION_HINT_EN={'opening':'Shen Jiyue rescues you; this is not your kill.','rest':'Spend 1 food and 1 turn; restore up to 70 energy and 80 HP.','train':'Spend 20 energy, 1 food and time; gain 18 cultivation XP.','forage':'Lose 4 HP and 1 turn; gain 3 food.','scan':'Spend 1 turn to review threats and advancement conditions. No resources awarded.','explore':'Spend 8 energy to begin an encounter; rewards require your own victory.','guard':'Reduce incoming damage and recover energy; tactics affect the exact values.','skill':'Spend 12 energy and gain contamination; damage follows the current combat rules.'}


def build_app(engine=None):
    e=engine or Engine(ROOT); rooms=RoomService(e.store);widgets=[];epochs={}
    def context_key(s):return s.get('personal_owner',s.get('owner',''))
    def activate(s):
        key=context_key(s);epochs[key]=epochs.get(key,0)+1
    def current(s,epoch):return epochs.get(context_key(s),0)==epoch
    secret_path=e.root/'data/browser-state.key'
    if not secret_path.exists():secret_path.write_text(uuid.uuid4().hex+uuid.uuid4().hex,encoding='ascii')
    def word(c,prop,zh,en):widgets.append((c,prop,zh,en));return c
    def language(code):return 'en-US' if code=='English' else 'zh-CN'
    def valid_session(s):
        s=dict(s or {})
        if not re.fullmatch('[a-f0-9]{32}',str(s.get('owner',''))):s={'owner':uuid.uuid4().hex}
        return s
    def view(s,locale='中文',stage='准备就绪',text_override=None,busy=False):
        s=valid_session(s);cid=s.get('cid');en=locale=='English'
        if en:
            translated={'准备就绪':'Ready','正在书写这一回合':'Writing this turn','回合已保存':'Turn saved','正在生成适合当前情景的行动推荐':'Generating contextual recommendations','正在生成情景行动推荐…':'Generating contextual recommendations…','AI生成推荐已更新，请在下一步行动中选择。':'Recommendations updated. Choose your next action.','冒险已创建，选择第一个行动开始。':'Adventure created. Choose the first action.','正文已保存，准备场景插图':'Story saved; preparing the illustration','正在提炼场景绘图提示词':'Preparing the scene illustration prompt','图片任务排队中':'Image task queued','正在生成场景插图':'Generating the scene illustration','场景插图已保存':'Scene illustration saved','已停止等待；完整正文保留，未完成正文不结算。已提交的图片任务可稍后恢复。':'Stopped waiting. Complete turns are saved; incomplete prose is not settled. Submitted image tasks can be resumed.'}
            stage=translated.get(stage,stage)
        if not cid:return (s,s,0,'## '+('Your story starts here' if en else '从废墟中的第一次相遇开始')+'\n\n'+('Create a new adventure, or load a saved branch.' if en else '创建冒险，或载入已经保存的故事。'),None,'',gr.update(choices=[],value=None),gr.update(choices=[],value=None),{},f'<div class="statusline" role="status" aria-live="polite">{html.escape(stage)}</div>',gr.update(interactive=not busy),gr.update(interactive=not busy))
        camp=e.store.campaign(s['owner'],cid);n=e.store.node(s['owner'],cid);state=n['state']
        acts=actions_for(state);choices=[((('Fuse ability echo · '+a['id'].split(':',1)[1][:8] if a['id'].startswith('absorb:') else ACTION_EN.get(a['id'],a['label'])) if en else a['label']),a['id']) for a in acts]
        for i,item in enumerate(n.get('meta',{}).get('recommendations',[])):
            if leaks_secret(item.get('label','')+' '+item.get('intent','')):continue
            if '\ufffd' in item.get('label','')+item.get('intent',''):continue
            if item.get('action_id') in {a['id'] for a in acts}:choices.append((('AI生成推荐 · ' if not en else 'AI recommendation · ')+item['label'],choice_token(n,i)))
        allnodes=e.store.nodes(s['owner'],cid)
        branches=[(f"{x['state'].get('turn',0):03d} · {x.get('event',{}).get('action_id','起点')} · {x['id'][:6]}",x['id']) for x in allnodes]
        stats=render_status(state,n.get('event'),en)
        img=n.get('image') or {};path=img.get('path');path=path if path and Path(path).is_file() else None
        details={'state':state,'scene':n.get('meta',{}).get('scene'),'event':n.get('event'),'source':n.get('meta',{}).get('source'),'prompt_version':n.get('meta',{}).get('prompt_version'),'image':{k:v for k,v in img.items() if k!='url'},'api_budget':e.budget.status()}
        content=n.get('text') or ('选择行动开始这一章。' if not en else 'Choose an action to begin this chapter.')
        if text_override is not None:content=text_override or ('正在生成…' if not en else 'Writing…')
        content=normalize_text(content,False)
        can_act=not busy and not s.get('room_token')
        return (s,s,camp['revision'],content,path,stats,gr.update(choices=choices,value=choices[0][1] if choices else None),gr.update(choices=branches,value=n['id']),details,f'<div class="statusline" role="status" aria-live="polite">{html.escape(stage)}</div>',gr.update(interactive=can_act),gr.update(interactive=can_act))
    with gr.Blocks(title='独核通天 · 核心纪元',analytics_enabled=False) as app:
        sess=gr.State({});browser=gr.BrowserState({},storage_key='duhe-story-session-v2',secret=secret_path.read_text('ascii'));revision=gr.Number(value=0,visible=False)
        gr.HTML('<div id="banner"><h1>独核通天</h1><p>核心纪元 · 从废墟走向通天塔　　An interactive chronicle of survival and ascent</p></div>')
        word(gr.Markdown('**你扮演的主角：陆凌霄** · 黑发蓝瞳的底层幸存者。你的选择决定他的训练、战斗和命运；独行升级、拯救文明是主线。'),'value','**你扮演的主角：陆凌霄** · 黑发蓝瞳的底层幸存者。你的选择决定他的训练、战斗和命运；独行升级、拯救文明是主线。','**You play Lu Lingxiao**, a survivor with black hair and blue eyes. Your choices shape his training, battles and path to saving civilization.')
        with gr.Accordion('世界观与玩法入门 / World & play guide',open=False):
            gr.Markdown(WORLD_INTRO)
        with gr.Accordion('冒险设置 / Adventure settings',open=False):
            with gr.Row():
                locale=gr.Dropdown(['中文','English'],value='中文',label='语言 / Language',scale=1)
                source=gr.Radio([('真实模型 / Live models','api'),('本地规则演示 / Local rules','offline')],value='api',label='生成方式 / Generation',scale=2)
                mode=gr.Radio([('正常冒险 / Campaign','normal'),('章节演示 / Checkpoint','demo')],value='normal',label='游玩模式 / Mode',scale=2)
                checkpoint=gr.Dropdown([('初遇与救援','opening'),('突破试炼','breakthrough'),('北墙守城','wall'),('第十层守卫','guardian'),('终焉决战','finale')],value='opening',label='演示章节 / Checkpoint',scale=1)
        with gr.Accordion('角色与叙述偏好 / Character & narration',open=False):
            gr.Markdown('陆凌霄固定黑发蓝瞳；沈霁月固定白发紫瞳。服装、伤势和体格随实际进度变化。')
            with gr.Row():
                approach=gr.Dropdown(['谨慎观察','利用环境','正面突破'],value='谨慎观察',label='战斗倾向 / Approach')
                style=gr.Dropdown(['克制细腻','紧张爽快','探索悬疑'],value='克制细腻',label='叙述风格 / Prose')
                art=gr.Dropdown([STYLE_LABEL],value=STYLE_LABEL,label='统一画风 / Art style',interactive=False)
            with gr.Row():
                perspective=gr.Dropdown([('第一人称 / First person','first'),('第三人称 / Third person','third')],value='first',label='叙述视角 / Perspective')
                content_level=gr.Dropdown([('克制战斗 / Restrained combat','restrained'),('标准冒险 / Standard adventure','standard')],value='restrained',label='内容偏好 / Content preference')
                scene_template=gr.Dropdown([('根据事件自动选择 / Automatic','auto')]+[(x[0]+' / '+x[1],k) for k,x in TEMPLATES.items()],value='auto',label='场景模板 / Scene template')
            gr.Markdown('以上偏好在创建新冒险时保存；模板只调整表达，不会改变事件、资源和人物设定。')
            gr.Markdown('全部人物参考图与新场景使用同一套漫画风格提示：干净细线、自然比例、清透上色、细腻眼神与柔和光影。已有场景可点击“按新参数重绘”更新画风。')
        with gr.Row(elem_id='adventure-toolbar'):
            start=word(gr.Button('创建冒险',variant='primary'),'value','创建冒险','Create adventure')
            refresh=word(gr.Button('刷新当前进度'),'value','刷新当前进度','Refresh progress')
            save=word(gr.Button('导出完整存档'),'value','导出完整存档','Export save')
            upload=gr.UploadButton('载入存档 / Load save',file_types=['.zip'],file_count='single')
        status=gr.HTML('<div class="statusline" role="status" aria-live="polite">选择模式后创建冒险。真实模式调用API并记录使用次数，当前不设调用上限。</div>')
        download=gr.File(label='完整故事存档 / Save archive',interactive=False,visible=False,elem_id='save-download')
        stats=gr.HTML(elem_id='player-status')
        with gr.Row(equal_height=False):
            with gr.Column(scale=6):
                story=gr.Markdown('## 从废墟中的第一次相遇开始\n\n创建冒险，或载入已经保存的故事。',elem_id='story',sanitize_html=True)
                choices=word(gr.Radio([],label='下一步行动',elem_id='choices'),'label','下一步行动','Your next action')
                action_hint=gr.Markdown('选择行动可查看规则代价；AI推荐会保留具体做法。',elem_id='action-hint')
                recommend_button=word(gr.Button('刷新情景推荐 / AI生成推荐'),'value','刷新情景推荐 / AI生成推荐','Refresh AI recommendations')
                gr.Markdown('AI推荐提供具体做法，与当前合法行动对应；数值代价按游戏规则结算。')
                with gr.Row():
                    go=word(gr.Button('执行选择',variant='primary'),'value','执行选择','Continue')
                    stop=word(gr.Button('停止生成'),'value','停止生成','Stop')
                free=word(gr.Textbox(label='自由行动',placeholder='例如：先休息恢复，再准备独行试炼。'),'label','自由行动','Describe an action')
                free_go=word(gr.Button('理解并执行自由行动'),'value','理解并执行自由行动','Interpret and act')
                with gr.Accordion('故事分支与回溯 / Branches',open=False):
                    branches=gr.Dropdown([],label='已探索的节点 / Explored nodes')
                    restore=gr.Button('回到这个节点 / Return to node')
                    branch_note=gr.Markdown('回到旧节点后继续选择会保留原分支。物品、能力和人物关系随当前分支恢复。')
                    slotname=gr.Textbox(value='我的冒险',label='存档槽位名称 / Save slot')
                    with gr.Row():
                        slotsave=gr.Button('保存到槽位 / Save slot');slotrefresh=gr.Button('列出我的槽位 / List saves')
                    slots=gr.Dropdown([],label='我的存档 / My saves');slotload=gr.Button('读取选中槽位 / Load slot')
                    reading=gr.Button('导出剧情文本 / Export Markdown')
                with gr.Accordion('创作修订 / Edit prose',open=False):
                    gr.Markdown('可润色当前正文并建立新分支。数值与事件结算保持原记录，旧图会标记待核对。')
                    editload=gr.Button('载入当前正文 / Load text');edited=gr.Textbox(lines=8,label='正文修订 / Revised prose')
                    editsave=gr.Button('保存为新分支 / Fork edited prose')
            with gr.Column(scale=5):
                picture=gr.Image(label='场景插图 / Scene illustration',height=430,type='filepath',interactive=False)
                autoimage=gr.Checkbox(value=True,label='每回合自动配图 / Illustrate each turn')
                retry=gr.Button('生成或恢复本场景配图 / Generate or resume image')
                with gr.Accordion('图像参数与提示词 / Image controls',open=False):
                    size=gr.Dropdown(['1280*1280','1440*1440','1024*1024'],value=e.settings.image_size,label='尺寸 / Size')
                    seed=gr.Number(value=-1,precision=0,label='随机种子（-1不指定） / Seed')
                    extend=gr.Checkbox(value=True,label='提示词智能改写 / Prompt extension')
                    repaint=gr.Button('按新参数重绘（新任务） / Regenerate')
                with gr.Accordion('人物档案 / Character files',open=False):
                    gr.Markdown('玩家操纵**陆凌霄**。参考图用于展示固定形象；场景插图仍由文生图独立生成，服装和体格以当前存档为准。反派档案含设定信息，可按需展开。')
                    for character_id,card in CHARACTERS.items():
                        with gr.Accordion(card['name']+(' · 玩家角色' if character_id=='protagonist' else ''),open=character_id=='protagonist'):
                            with gr.Row():
                                with gr.Column(scale=2,min_width=160):gr.Image(value=portrait_path(e.root,character_id),label=card['name']+' · 人物参考',height=310,interactive=False)
                                with gr.Column(scale=3,min_width=220):gr.Markdown(profile_text(e.root,character_id))
                with gr.Accordion('图文反馈 / Feedback',open=False):
                    rating=gr.Slider(1,5,value=4,step=1,label='连贯性与图文匹配 / Quality')
                    tags=gr.CheckboxGroup(['外貌不一致','装备错误','体格超前','人物性格不符','感情戏过多','图文不匹配'],label='问题标签 / Issues')
                    observation=gr.Textbox(label='观察到的细节或修正意见 / Observation',lines=2)
                    confirmed=gr.Checkbox(label='确认仅将环境观察带入后续叙述 / Use confirmed environmental observation',value=False)
                    sendfeedback=gr.Button('保存反馈 / Save feedback');feedback_note=gr.Markdown()
                with gr.Accordion('体验反馈 / Playtest feedback',open=False):
                    gr.Markdown('请由实际体验者填写，可使用匿名代号。此处与图文问题反馈分开保存。 / For actual participants; aliases are welcome.')
                    participant=gr.Textbox(label='体验者代号 / Participant alias')
                    playtask=gr.Dropdown(['连续行动 / Consecutive actions','分支存档 / Branch and save','多人投票 / Cooperative vote','界面阅读 / Reading'],value=None,label='本次任务 / Task')
                    completed=gr.Radio([('完成 / Completed','yes'),('未完成 / Incomplete','no')],value=None,label='任务结果 / Outcome')
                    usability=gr.Radio([1,2,3,4,5],value=None,label='易用性 1–5 / Ease of use')
                    playnote=gr.Textbox(label='卡住的位置与改进建议 / Difficulty and suggestion',lines=2)
                    playsend=gr.Button('保存体验反馈 / Save playtest feedback');playresult=gr.Markdown()
                with gr.Accordion('故事配音 / Neural narration',open=False):
                    gr.Markdown('Edge TTS 在线神经语音，无需API密钥；点击后将本轮正文发送到语音服务。属于免费访问方案，受网络和服务可用性影响。用于朗读故事，不生成背景音乐。')
                    voice=gr.Dropdown(['中文女声','中文男声','English'],value='中文女声',label='配音音色')
                    speak=gr.Button('生成当前故事配音');speech_status=gr.Markdown()
                    speech_player=gr.Audio(type='filepath',label='最近生成的故事朗读（按按钮更新）',autoplay=False,interactive=False)
                with gr.Accordion('氛围音 / Ambience',open=False):
                    sound=gr.Dropdown([('营地','camp'),('废墟','ruins'),('通天塔','tower')],value='camp',label='场景 / Scene')
                    volume=gr.Slider(0,1,value=.3,label='音量 / Volume')
                    soundload=gr.Button('准备氛围音 / Prepare ambience')
                    player=gr.Audio(label='本地合成氛围音 · 点击播放 / Synthesized audio',type='filepath',interactive=False,autoplay=False,loop=True)
        with gr.Accordion('多人共同决策 / Cooperative decisions',open=False):
            gr.Markdown('多个玩家共同为陆凌霄投票。塔内仍是单人试炼；房主锁定结果后只生成一次。生成失败后再次锁定会重试上次已确定的行动与做法。 / After a failed generation, resolve again to retry the frozen action and approach.')
            with gr.Row():
                roomcreate=gr.Button('为当前故事创建房间 / Create room')
                invite=gr.Textbox(label='邀请口令 / Invite token',type='password')
                showinvite=gr.Checkbox(value=False,label='显示邀请口令 / Show invite')
                displayname=gr.Textbox(value='同行者',label='昵称 / Name')
                roomjoin=gr.Button('加入房间 / Join')
            roomtoken=gr.State('');hosttoken=gr.State('')
            roominfo=gr.JSON(label='房间进度 / Room state')
            with gr.Row():
                roomrefresh=gr.Button('同步房间故事 / Sync room')
                roomvote=gr.Button('为当前选择投票 / Vote')
                roomlock=gr.Button('房主锁定并执行 / Resolve round')
                roomleave=gr.Button('离开房间 / Leave room')
            roomnote=gr.Markdown()
        with gr.Accordion('实验运行记录 / Run details',open=False):
            gr.Markdown(f'文本模型：**{e.settings.text_model}**　·　场景与人物图：**{e.settings.image_model}**　·　故事配音：**Edge Neural**（点击生成）')
            gr.Markdown('### 术语对照 / Terminology\n\n'+ '\n'.join(f'- **{zh}** — {en}' for zh,en in TERMS.items()))
            details=gr.JSON(label='状态、提示词与实际调用记录 / Evidence')
        outputs=[sess,browser,revision,story,picture,stats,choices,branches,details,status,go,free_go]

        def load_session(b,loc):
            s=valid_session(b)
            token=s.get('room_token','')
            try:
                snapshot=rooms.snapshot(token) if token else {}
                if token:s.update(owner=snapshot['owner'],cid=snapshot['campaign_id'])
                return (*view(s,loc,'已恢复房间进度。' if token else '准备就绪'),token,token,snapshot)
            except Exception:
                personal={'owner':s.get('personal_owner',s['owner'])}
                if s.get('personal_cid'):personal['cid']=s['personal_cid']
                try:return (*view(personal,loc,'房间或存档不可用，已恢复个人进度。'),'','',{})
                except Exception:return (*view({'owner':personal['owner']},loc,'请创建冒险或导入存档。'),'','',{})
        app.load(load_session,[browser,locale],[*outputs,roomtoken,hosttoken,roominfo])
        def toggle_invite(visible):return gr.update(type='text' if visible else 'password')
        showinvite.change(toggle_invite,[showinvite],invite,queue=False,api_name=False)
        def begin(s,m,cp,a,st,ar,loc,pov='third',content='restrained',template='auto'):
            if (s or {}).get('room_token'):raise gr.Error('请先离开协作房间，再创建个人冒险。 / Leave the room before creating an adventure.')
            s=valid_session(s);s={'owner':s.get('personal_owner',s['owner'])};s['cid']=e.create(s['owner'],m,cp if m=='demo' else 'opening',{'approach':a,'style':st,'art_style':ar,'perspective':pov,'content_level':content,'scene_template':template})
            activate(s)
            return view(s,loc,'冒险已创建，选择第一个行动开始。')
        start.click(begin,[sess,mode,checkpoint,approach,style,art,locale,perspective,content_level,scene_template],outputs,api_name=False)
        refresh.click(lambda s,l:view(s,l),[sess,locale],outputs,api_name=False)
        async def advance(s,choice,rev,src,images,loc,free_text=None,opid=None,narrative_intent=None):
            s=valid_session(s);epoch=epochs.get(context_key(s),0)
            if not s.get('cid'):yield view(s,loc,'请先创建冒险。');return
            try:
                if s.get('room_token') and not opid:raise ValueError('协作房间请先投票，由房主锁定后统一执行。')
                if free_text is not None:
                    yield view(s,loc,'正在理解你的自由行动…（最多60秒）',busy=True)
                    choice=await e.resolve_action(s['owner'],s['cid'],free_text,src=='offline')
                    if not current(s,epoch):return
                    yield view(s,loc,'已理解，本次执行：'+next(a['label'] for a in actions_for(e.store.node(s['owner'],s['cid'])['state']) if a['id']==choice),busy=True)
                if not choice:raise ValueError('请先选择一个行动。')
                async for v in e.execute(s['owner'],s['cid'],choice,rev,offline=src=='offline',with_image=images,language=language(loc),operation_id=opid,intent=free_text or narrative_intent):
                    if not current(s,epoch):return
                    yield view(s,loc,v['stage'],v.get('text'),v.get('busy',False))
            except TimeoutError:
                if not current(s,epoch):return
                yield view(s,loc,'自由行动理解超过60秒，已停止等待；本轮未执行，请重试或选择下方基础行动。')
            except Exception as exc:
                if not current(s,epoch):return
                yield view(s,loc,str(exc) or '本次行动未完成，请刷新后重试。')
        async def refresh_recommendations(s,src,loc):
            epoch=epochs.get(context_key(s),0)
            if not s.get('cid'):yield view(s,loc,'请先创建并生成故事。');return
            if src=='offline':yield view(s,loc,'AI推荐需要切换到真实模型；本地基础行动仍可使用。');return
            yield view(s,loc,'正在生成情景行动推荐…',busy=True)
            try:
                await e.recommend(s['owner'],s['cid'],language(loc))
                if not current(s,epoch):return
                yield view(s,loc,'AI生成推荐已更新，请在下一步行动中选择。')
            except Exception as exc:
                if not current(s,epoch):return
                yield view(s,loc,f'推荐生成失败（{type(exc).__name__}），可继续使用基础行动。')
        def describe_choice(s,choice,loc):
            if not s.get('cid') or not choice:return ''
            node=e.store.node(s['owner'],s['cid']);intent=None
            try:
                base,intent=resolve_recommendation(node,choice) if choice.startswith('ai:') else (choice,None)
                action=next(a for a in actions_for(node['state']) if a['id']==base)
                if loc=='English':return '**Rule settlement:** '+ACTION_HINT_EN.get(base,'One legal action; costs follow the current rule state.')+('\n\n**Planned approach:** '+intent if intent else '')
                return '**规则代价：** '+action['hint']+('\n\n**具体做法：** '+intent if intent else '')
            except (ValueError,StopIteration):return '选项已更新，请刷新当前进度。 / This choice has changed; refresh progress.'
        choices.change(describe_choice,[sess,choices,locale],action_hint,api_name=False)
        recommend_event=recommend_button.click(refresh_recommendations,[sess,source,locale],outputs,concurrency_limit=1,api_name=False)
        async def speak_story(s,v):
            epoch=epochs.get(context_key(s),0)
            yield None,'正在生成神经配音…（最多60秒）'
            try:
                path=await narrate(e.root,e.store.node(s['owner'],s['cid'])['text'],v)
                if not current(s,epoch):return
                yield path,'配音已就绪，点击播放。'
            except Exception as exc:
                if not current(s,epoch):return
                yield None,str(exc)
        speech_event=speak.click(speak_story,[sess,voice],[speech_player,speech_status],api_name=False)
        run_event=go.click(advance,[sess,choices,revision,source,autoimage,locale],outputs,concurrency_limit=3,concurrency_id='story',api_name=False)
        free_event=free_go.click(advance,[sess,choices,revision,source,autoimage,locale,free],outputs,concurrency_limit=3,concurrency_id='story',api_name=False)
        stop.click(lambda s,l:view(s,l,'已停止等待；完整正文保留，未完成正文不结算。已提交的图片任务可稍后恢复。'),[sess,locale],outputs,cancels=[run_event,free_event],queue=False,api_name=False)
        def switch(s,nid,loc):
            if s.get('room_token'):raise gr.Error('协作期间不能单方改变分支，可导出后在个人模式探索。')
            if e.locks.get(s['cid']) and e.locks[s['cid']].locked():raise gr.Error('请先停止当前生成再切换分支。')
            e.store.select(s['owner'],s['cid'],nid);activate(s);return view(s,loc,'已恢复所选节点。')
        restore.click(switch,[sess,branches,locale],outputs,api_name=False)
        def list_slots(s):return gr.update(choices=[(x['label']+' · '+x['mode'],x['id']) for x in e.store.slots(s.get('personal_owner',s['owner']))],value=None)
        def save_slot(s,label):
            if s.get('room_token'):raise gr.Error('协作故事请先导出；个人槽位只保存自己的冒险。')
            e.store.save_slot(s['owner'],s['cid'],label);return list_slots(s)
        slotsave.click(save_slot,[sess,slotname],slots,api_name=False)
        slotrefresh.click(list_slots,[sess],slots,api_name=False)
        def load_slot(s,sid,loc):
            if s.get('room_token'):raise gr.Error('请先离开协作房间，再读取个人存档。 / Leave the room before loading a save.')
            owner=s.get('personal_owner',s['owner']);r=e.store.load_slot(owner,sid)
            loaded={'owner':owner,'cid':r['campaign_id']};activate(loaded)
            return view(loaded,loc,'存档槽位已恢复。')
        slotload.click(load_slot,[sess,slots,locale],outputs,api_name=False)
        def export_progress(s,b,loc,kind):
            en=loc=='English'
            def note(text):return '<div class="statusline" role="status" aria-live="polite">'+html.escape(text)+'</div>'
            # A server restart can lose gr.State while BrowserState still has the saved entry.
            selected=dict(s or {})
            if not selected.get('owner') or not selected.get('cid'):selected=dict(b or {})
            epoch=epochs.get(context_key(selected),0)
            empty=gr.update(value=None,visible=False)
            yield gr.skip(),gr.skip(),empty,note('Preparing your save…' if en else '正在打包存档，请稍候…')
            try:
                if not selected.get('owner') or not selected.get('cid'):
                    raise ValueError('Create or load an adventure first.' if en else '请先创建或载入冒险，再导出存档。')
                if selected.get('room_token'):
                    snapshot=rooms.snapshot(selected['room_token'])
                    selected.update(owner=snapshot['owner'],cid=snapshot['campaign_id'])
                export=e.store.export_bundle if kind=='bundle' else e.store.export_text
                path=export(selected['owner'],selected['cid'],e.root/'output/saves')
                if not current(selected,epoch):return
                label=('完整故事存档 / Save archive' if kind=='bundle' else '剧情文本 / Story Markdown')
                message=('Save ready. Click the download arrow in the file below.' if en else '存档已生成，请点击下方文件右侧的下载箭头保存到电脑。')
                yield selected,selected,gr.update(value=str(path),visible=True,label=label),note(message)
            except PermissionError:
                if current(selected,epoch):
                    yield gr.skip(),gr.skip(),empty,note('Save unavailable. Refresh the page and retry.' if en else '当前存档不可用，请刷新页面后重试。')
            except Exception as exc:
                if current(selected,epoch):
                    message=str(exc) if isinstance(exc,ValueError) else ('Export failed. Please retry.' if en else '导出失败，请稍后重试。')
                    yield gr.skip(),gr.skip(),empty,note(message)
        def export_save(s,b,loc):yield from export_progress(s,b,loc,'bundle')
        def export_reading(s,b,loc):yield from export_progress(s,b,loc,'text')
        reading.click(export_reading,[sess,browser,locale],[sess,browser,download,status],api_name=False)
        editload.click(lambda s:e.store.node(s['owner'],s['cid'])['text'],[sess],edited,api_name=False)
        def edit_text(s,text,loc):
            if s.get('room_token'):raise gr.Error('协作期间不能单方改写剧情。')
            if e.locks.get(s['cid']) and e.locks[s['cid']].locked():raise gr.Error('请先停止生成再修订。')
            n=e.store.node(s['owner'],s['cid']);e.store.fork_text(s['owner'],s['cid'],n['id'],text)
            activate(s)
            return view(s,loc,'已创建人工修订分支；旧图片待核对。')
        editsave.click(edit_text,[sess,edited,locale],outputs,api_name=False)
        save.click(export_save,[sess,browser,locale],[sess,browser,download,status],api_name=False)
        def import_save(path,s,loc):
            if s.get('room_token'):raise gr.Error('请先离开协作房间，再载入个人存档。 / Leave the room before importing a save.')
            s=valid_session(s);s={'owner':s.get('personal_owner',s['owner'])};s['cid']=e.store.import_bundle(s['owner'],Path(path));validate_state(e.store.node(s['owner'],s['cid'])['state']);activate(s);return view(s,loc,'存档已载入。')
        upload.upload(import_save,[upload,sess,locale],outputs,api_name=False)
        async def render_image(s,loc,sz,sd,ex,new=False):
            epoch=epochs.get(context_key(s),0)
            if not s.get('cid'):yield view(s,loc,'请先创建并完成一个回合。');return
            node=e.store.node(s['owner'],s['cid'])
            if not node['text']:yield view(s,loc,'请先完成故事正文。');return
            async for v in e.make_image(s['owner'],s['cid'],node['id'],force_new=new,size=sz,seed=None if sd<0 else int(sd),prompt_extend=ex):
                if not current(s,epoch):return
                yield view(s,loc,v['stage'])
        image_event=retry.click(render_image,[sess,locale,size,seed,extend],outputs,concurrency_limit=2,concurrency_id='image',api_name=False)
        async def redo(s,loc,sz,sd,ex):
            async for v in render_image(s,loc,sz,sd,ex,True):yield v
        repaint_event=repaint.click(redo,[sess,locale,size,seed,extend],outputs,concurrency_limit=2,concurrency_id='image',api_name=False)
        def feedback(s,r,t,o,c):
            n=e.store.node(s['owner'],s['cid'])
            # 只批准环境观察；规则/人物冲突由重绘和反馈处理，不写入属性。
            blocked=bool(re.search('升级|突破|装备|白发|黑发|蓝瞳|紫瞳|ULTRA|SSS',o))
            e.store.feedback(s['owner'],s['cid'],n['id'],{'rating':r,'tags':t,'observation':o[:1000],'confirmed':bool(c and not blocked),'prompt_version':n.get('meta',{}).get('prompt_version')})
            return '反馈已保存。'+('涉及人物或规则的改动已作为问题记录，请重绘或调整设定。' if c and blocked else '确认的环境观察将用于当前分支后续叙述。' if c else '')
        sendfeedback.click(feedback,[sess,rating,tags,observation,confirmed],feedback_note,api_name=False)
        def save_playtest(s,alias,task,outcome,score,note):
            if not s.get('cid'):raise gr.Error('请先创建或载入冒险。 / Create or load an adventure first.')
            if not str(alias or '').strip() or not task or outcome not in ('yes','no') or score is None or not 1<=score<=5:
                raise gr.Error('请填写代号、任务、结果与评分。 / Complete alias, task, outcome and rating.')
            n=e.store.node(s['owner'],s['cid'])
            e.store.feedback(s['owner'],s['cid'],n['id'],{'source':'peer_playtest','participant':str(alias).strip()[:60],'task':task,'completed':outcome=='yes','usability':score,'note':str(note or '')[:1500],'confirmed':False})
            return '体验反馈已保存。 / Playtest feedback saved.'
        playsend.click(save_playtest,[sess,participant,playtask,completed,usability,playnote],playresult,api_name=False)
        soundload.click(lambda k,v:ambient(e.root,k,v),[sound,volume],player,api_name=False)
        def create_room(s,loc):
            if s.get('room_token'):raise gr.Error('已经在协作房间中，请先离开。 / You are already in a room.')
            r=rooms.create(s['owner'],s['cid']);s=dict(s);s.setdefault('personal_owner',s['owner']);s.setdefault('personal_cid',s['cid']);s['room_token']=r['host_token']
            activate(s)
            return (*view(s,loc,'房间已创建。请投票，由房主锁定执行。'),r['invite_token'],r['host_token'],r['host_token'],rooms.snapshot(r['host_token']),'房间已创建。将邀请口令私下提供给同伴。')
        roomcreate.click(create_room,[sess,locale],[*outputs,invite,roomtoken,hosttoken,roominfo,roomnote],api_name=False)
        def join_room(token,name,s,loc):
            try:r=rooms.join((token or '').strip(),name)
            except PermissionError:
                raise gr.Error('邀请口令无效，请向房主索取完整口令；房主可勾选“显示邀请口令”后复制。') from None
            except ValueError as exc:
                message='房间已满，最多支持4位成员（含房主）。' if 'four members' in str(exc) else '昵称不能为空，且不能超过40个字符。'
                raise gr.Error(message) from None
            synced=sync_room(r['member_token'],s,loc)
            return (*synced[:-1],r['member_token'],'',synced[-1],'已加入并同步房间，请为当前行动投票。')
        roomjoin.click(join_room,[invite,displayname,sess,locale],[*outputs,roomtoken,hosttoken,roominfo,roomnote],api_name=False)
        def sync_room(token,s,loc):
            snap=rooms.snapshot(token);s=valid_session(s)
            s.setdefault('personal_owner',s['owner']);s.setdefault('personal_cid',s.get('cid'))
            s.update(owner=snap['owner'],cid=snap['campaign_id'],room_token=token);activate(s);return (*view(s,loc,'房间进度已同步。请投票后由房主执行。'),snap)
        roomrefresh.click(sync_room,[roomtoken,sess,locale],[*outputs,roominfo],api_name=False)
        roomvote.click(lambda tok,rev,action:rooms.vote(tok,int(rev),action),[roomtoken,revision,choices],roominfo,api_name=False)
        async def resolve_room(host,s,rev,choice,src,images,loc):
            snap=rooms.snapshot(host)
            result=rooms.lock_round(host,int(rev),None if snap.get('retry_action_id') else choice)
            s=dict(s or {});s.update(owner=result['owner'],cid=result['campaign_id'],room_token=host);success=False
            try:
                async for v in advance(s,result['action_id'],result['revision'],src,images,loc,opid=result['operation_id'],narrative_intent=result.get('intent')):yield v
                success=e.store.campaign(result['owner'],result['campaign_id'])['revision']>result['revision']
            finally:
                success=e.store.campaign(result['owner'],result['campaign_id'])['revision']>result['revision']
                rooms.finish_round(host,int(rev),success)
        room_event=roomlock.click(resolve_room,[hosttoken,sess,revision,choices,source,autoimage,locale],outputs,concurrency_limit=3,concurrency_id='story',api_name=False)
        def leave_room(s,loc):
            s=valid_session(s);out={'owner':s.get('personal_owner',s['owner'])}
            if s.get('personal_cid'):out['cid']=s['personal_cid']
            activate(out)
            return (*view(out,loc,'已离开房间，恢复个人进度。'),'','')
        roomleave.click(leave_room,[sess,locale],[*outputs,roomtoken,hosttoken],api_name=False)
        stop.click(fn=None,cancels=[room_event,image_event,repaint_event,recommend_event,speech_event],queue=False,api_name=False)
        for block in app.blocks.values():
            prop='value' if isinstance(block,gr.Button) else 'label'
            value=getattr(block,prop,None)
            if isinstance(value,str) and ' / ' in value:
                zh,en=value.split(' / ',1)
                if not any(w[0] is block and w[1]==prop for w in widgets):word(block,prop,value,en)
            options=getattr(block,'choices',None)
            if isinstance(options,list) and options:
                names={'谨慎观察':'Cautious observation','利用环境':'Use the environment','正面突破':'Direct assault','克制细腻':'Subtle and restrained','紧张爽快':'Tense and brisk','探索悬疑':'Exploration and mystery','初遇与救援':'First encounter and rescue','突破试炼':'Advancement trial','北墙守城':'North-wall defense','第十层守卫':'Floor 10 guardian','终焉决战':'Final confrontation'}
                english=[(label.split(' / ',1)[-1] if ' / ' in label else names.get(label,label),value) for label,value in options]
                if english!=options:word(block,'choices',options,english)
        locale.change(lambda loc:[gr.update(**{prop:en if loc=='English' else zh}) for _,prop,zh,en in widgets],[locale],[x[0] for x in widgets],api_name=False).then(lambda s,l:view(s,l),[sess,locale],outputs,api_name=False)
    app.queue(default_concurrency_limit=3,max_size=30)
    app.duhe_engine=e
    return app


def main():
    app=build_app()
    app.launch(server_name=os.getenv('DUHE_HOST','127.0.0.1'),server_port=int(os.getenv('DUHE_PORT','7864')),inbrowser=False,
               theme=gr.themes.Soft(primary_hue='blue',neutral_hue='slate'),css=CSS,allowed_paths=[str(ROOT/'output'),str(ROOT/'data/stories_media')],
               blocked_paths=[str(ROOT/'.env'),str(ROOT/'data/api_budget.sqlite'),str(ROOT/'data/stories.sqlite')],show_error=False,footer_links=[])


if __name__=='__main__':main()
