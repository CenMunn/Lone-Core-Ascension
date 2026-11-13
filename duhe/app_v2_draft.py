"""Offline v2 integration harness.  Not the production launcher."""
import asyncio
import os
import re
import uuid
from pathlib import Path
import gradio as gr
from .catalog import ABILITIES, EQUIPMENT, MONSTERS, ABILITY_RANKS, codex_entries
from .combat import _known_skills
from .controller_v2 import ControllerV2
from .engine_v2 import EngineV2
from .inventory import preview_resource_action
from .media_view_v2 import displayed_image
from .rooms_v2 import RoomServiceV2, choice_token as room_choice
from .storage import Store
from .status_panel import WORLD_INTRO
from .world import CHARACTERS
from .profiles import profile_text, portrait_path
from .audio import ambient
from .story_flow import reading_node, route_hint, CONTINUATIONS
from .equipment import craftable_items
from .player_labels import format_recipe,format_stats,format_effects,format_cooldowns,ability_label,monster_kind
from .affinity import render_affinity
from .creative import TERMS
from .branding import banner_html, artwork_css
from .viewmodel_v2 import (available_actions, render_system, render_inventory,
                           render_abilities, render_equipment, render_codex, preview_equipment)

ROOT = Path(__file__).resolve().parents[1]


def require_live_mode(mode):
    if mode != 'api':
        raise ValueError('离线模式不会调用模型；请先切换到真实模型模式。')


def build_draft(store=None):
    engine = EngineV2(ROOT)
    engine.store = store or Store(ROOT / 'data' / 'v2-draft.sqlite')
    controller = engine.controller_v2 = ControllerV2(engine.store)
    rooms = RoomServiceV2(engine.store)
    secret_path = ROOT / 'data' / 'browser-state.key'
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    if not secret_path.exists():
        secret_path.write_text(uuid.uuid4().hex + uuid.uuid4().hex, encoding='ascii')
    def new(s, checkpoint, approach, style, perspective, content_level):
        if (s or {}).get('room_token'):
            return show(s, '请先离开协作房间，再创建个人冒险。')
        s = {'owner': (s or {}).get('owner') or uuid.uuid4().hex, 'locale': (s or {}).get('locale', 'zh-CN')}
        demo = checkpoint != 'normal'
        preferences = {'approach': approach, 'style': style, 'perspective': perspective, 'content_level': content_level}
        s['cid'] = controller.create(s['owner'], preferences, mode='demo' if demo else 'normal',
                                     checkpoint=checkpoint if demo else 'opening')
        return show(s, '已创建明确标注的章节演示存档。' if demo else '新版正常冒险已创建。')

    def show(s, note='准备就绪', text_override=None):
        if not s or not s.get('cid') or not s.get('owner'):
            return (s or {}, s or {}, 0, '请选择模式并创建冒险，或加载已有存档。', '', '', '', '', '',
                    gr.update(choices=[], value=None), gr.update(choices=[], value=None),
                    gr.update(choices=[], value=None), gr.update(choices=[], value=None),
                    gr.update(choices=[], value=None), gr.update(choices=[], value=None),
                    gr.update(choices=[], value=None), gr.update(choices=[], value=None),
                    gr.update(choices=[], value=None), gr.update(choices=[], value=None), note, '创建冒险后，普通续写与关键节点会分别说明。',
                    gr.update(choices=[],value=None), '当前没有可打造装备。', gr.update(interactive=False), '创建冒险后可查看人物好感度。')
        node = controller.store.node(s['owner'], s['cid'])
        campaign = controller.store.campaign(s['owner'], s['cid'])
        state = node['state']; groups = available_actions(state)
        en = s.get('locale') == 'en-US'
        from .i18n_v2 import action_label
        choice = lambda rows: gr.update(choices=[(action_label(x) if en else x['label'], x['id']) for x in rows], value=None)
        skills = [(ability_label(k,en)+' · '+('精通 ' if not en else 'Mastery ')+f"Lv.{next((x.get('level',1) for x in state['skills'] if x.get('catalog_id',x.get('id'))==k),1)}", k)
                  for k in sorted(_known_skills(state),key=lambda k:(ABILITY_RANKS.index(ABILITIES[k]['rank']),k))
                  if k in ABILITIES and ABILITIES[k]['effect'] != 'passive']
        outside_skills = [(label, key) for label, key in skills if ABILITIES[key].get('outside_combat')]
        instances = [(EQUIPMENT.get(v['item_id'], {}).get('name', v['item_id']), k)
                     for k, v in state['equipment_items'].items()]
        branches = [(f"剧情{n['state']['story_turn']} · {n.get('event', {}).get('action_id', '起点')} · {n['id'][:6]}", n['id'])
                    for n in controller.store.nodes(s['owner'], s['cid'])]
        all_echoes = state.get('echoes', []); consumed = set(state.get('consumed_echoes', []))
        chosen_enemies = {x.get('enemy_id') for x in all_echoes if x.get('id') in consumed and x.get('enemy_id')}
        echoes = [(ability_label(x['catalog_id'],en) if x.get('catalog_id') in ABILITIES else x.get('skill_name','未知残响')+'（评级未记录）', x['id'])
                  for x in all_echoes if x.get('id') not in consumed and x.get('enemy_id') not in chosen_enemies]
        combat = state.get('combat')
        enemy_record=MONSTERS.get((combat or {}).get('monster_id'),{})
        enemy_heading=('【'+monster_kind(enemy_record,en)+'】'+combat.get('name','敌人')+' · '+enemy_record.get('rank','?')+'级') if combat else ''
        if combat and state.get('legacy_battle_requires_old_rules'):
            hud = '## ⚔️ 旧版战斗尚未结束\n\n请在旧版完成此战后重新导入；本副本保留原战斗状态。\n\n'
        else:
            hud = (f"## ⚔️ {enemy_heading}\n\n敌方生命 **{combat['hp']}/{combat['max_hp']}** · "
                   f"第 **{combat['exchange']}** 次交锋\n\n"
                   f"敌方异常：{format_effects(combat.get('effects', []))} · "
                   f"我方异常：{format_effects(combat.get('player_effects', []))} · "
                   f"能力冷却：{format_cooldowns(combat)}\n\n" if combat else '')
        codex = render_codex(state, en)
        challengeable = [('【'+monster_kind(x,en)+'】'+x['name']+' · '+x['rank']+'级', x['id']) for x in codex_entries(state, 'monster') if x['challengeable']]
        reading=reading_node(controller.store,s['owner'],s['cid'])
        content = text_override if text_override is not None else (reading['text'] or '你的故事从废墟开始。')
        story_rows=[(('普通续写 · ' if x['id'] in CONTINUATIONS else '关键节点 · ')+
                    (action_label(x) if en else x['label']),x['id']) for x in groups['story']]
        ordinary_rows=[(action_label(x)+(f" ({x['reason']})" if x.get('reason') else '') if en else x['label'],x['id']) for x in groups['ordinary']]
        last=state.get('last_ordinary_action')
        ordinary_value=last if last in {x[1] for x in ordinary_rows} else next((x['id'] for x in groups['ordinary'] if x.get('available',True)),ordinary_rows[0][1] if ordinary_rows else None)
        craftable=craftable_items(state)
        recipe_rows=[(x['name']+' · '+format_recipe(x['recipe']),x['id']) for x in craftable]
        cost_text=('**打造消耗：** '+format_recipe(craftable[0]['recipe'],state['inventory'])) if craftable else '当前没有已解锁且材料足够的装备；可在图鉴查看材料来源。'
        return (s, s, campaign['revision'], hud + content,
                render_system(state, en), render_inventory(state, en), render_abilities(state, en),
                render_equipment(state, en), codex, gr.update(choices=story_rows,value=story_rows[0][1] if story_rows else None), gr.update(choices=ordinary_rows,value=ordinary_value),
                choice(groups['battle']), choice(groups['combat']),
                gr.update(choices=skills, value=None), gr.update(choices=outside_skills, value=None), gr.update(choices=instances, value=None),
                gr.update(choices=branches, value=node['id']), gr.update(choices=echoes, value=None),
                gr.update(choices=challengeable, value=None), note, route_hint(state),
                gr.update(choices=recipe_rows,value=recipe_rows[0][1] if recipe_rows else None),cost_text,gr.update(interactive=bool(craftable)),render_affinity(state))

    async def act(s, rev, action, target=None, quantity=None, item=None, *, mode='offline', images=False, voice=False, source='story', intent=None):
        if not s or not s.get('cid') or not s.get('owner'):
            yield show(s, '请先创建冒险。'); return
        try:
            if s.get('room_token'):
                raise ValueError('协作房间请投票后由房主锁定执行。')
            if not action:
                raise ValueError('请先选择行动')
            request = {'action': action}
            if action=='free_story':request['intent']=intent
            if action in ('refine', 'absorb_core'):
                request['quantity'] = int(quantity) if quantity is not None else 0
            elif action == 'start_encounter':
                if target == 'realm_trial':
                    request['action'] = 'realm_trial'
                else:
                    request['monster_id'] = target
                    request['source'] = source
            elif action == 'skill':
                request['skill_id'] = target
            elif action in ('fuse', 'use_ability'):
                request['target'] = target
            elif action in ('use_tactic', 'use_suggestion'):
                request['token'] = target
            elif action == 'craft_equipment':
                request['item_id'] = target
            elif action == 'equip':
                request.update(instance_id=target, slot=item)
            elif action == 'unequip':
                request['slot'] = item
            async for update in engine.execute_v2(s['owner'], s['cid'], request, int(rev),
                                                  operation_id=uuid.uuid4().hex,
                                                  offline=(mode == 'offline'), with_image=bool(images), auto_voice=bool(voice),
                                                  auto_recommend=(mode == 'api'), language=s.get('locale', 'zh-CN')):
                yield show(s, update['stage'], update.get('text') if update.get('busy') else None)
        except (ValueError, PermissionError, TypeError) as exc:
            yield show(s, str(exc))

    with gr.Blocks(title='独核通天') as app:
        session = gr.State({})
        browser = gr.BrowserState({}, storage_key='duhe-v2-game-session', secret=secret_path.read_text('ascii'))
        media_preferences = gr.BrowserState({'image': True, 'voice': False, 'play': True},
                                            storage_key='duhe-v2-media-preferences', secret=secret_path.read_text('ascii'))
        revision = gr.Number(value=0, visible=False)
        gr.HTML(banner_html())
        with gr.Accordion('世界观与玩法', open=False):
            gr.Markdown(WORLD_INTRO.replace('吸收、排污、锻造或突破', '吸收、锻造、研究或突破'))
            gr.Markdown('**主要术语 / Key terms**\n\n' + ' · '.join(f'{zh} / {en}' for zh, en in TERMS.items()))
        with gr.Accordion('角色与叙述偏好', open=False):
            gr.Markdown('固定扮演陆凌霄；下列偏好在创建冒险时保存，并影响叙述与风格。')
            with gr.Row():
                approach = gr.Dropdown(['谨慎观察', '利用环境', '正面突破'], value='谨慎观察', label='战斗倾向')
                style = gr.Dropdown(['克制细腻', '紧张爽快', '探索悬疑'], value='克制细腻', label='文风')
                perspective = gr.Dropdown([('第一人称', 'first'), ('第三人称', 'third')], value='first', label='叙述视角')
                content_level = gr.Dropdown([('克制战斗', 'restrained'), ('标准冒险', 'standard')], value='restrained', label='内容偏好')
        with gr.Row():
            start = gr.Button('创建冒险 / Create', variant='primary')
            refresh = gr.Button('刷新 / Refresh')
            stop_story = gr.Button('停止生成 / Stop')
            locale = gr.Dropdown([('中文', 'zh-CN'), ('English', 'en-US')], value='zh-CN', label='语言 / Language')
            checkpoint = gr.Dropdown([('正常冒险 · 从初遇开始', 'normal'), ('演示 · 初遇', 'opening'),
                                      ('演示 · 突破试炼', 'breakthrough'), ('演示 · 北墙', 'wall'),
                                      ('演示 · 第十层守卫', 'guardian'), ('演示 · 终焉决战', 'finale')],
                                     value='normal', label='冒险模式 / Adventure mode')
            mode = gr.Radio([('离线规则 / Offline', 'offline'), ('真实模型 / Live', 'api')], value='api', label='生成方式 / Generation')
        note = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=3, elem_id='reading-column'):
                picture = gr.Image(label='当前场景插图', type='filepath', interactive=False, height=400)
                story = gr.Markdown('选择模式并创建冒险，从废墟中的初遇开始。', elem_id='story')
                with gr.Tab('推进剧情 / Story'):
                    story_guide = gr.Markdown('普通续写保持故事连续；关键节点需要满足列出的条件。')
                    story_action = gr.Dropdown(label='普通续写 / 关键节点（计入剧情回合）')
                    story_go = gr.Button('继续所选剧情 / Continue', variant='primary')
                with gr.Tab('普通行动 / Actions'):
                    normal_action = gr.Dropdown(label='普通行动（不增加剧情回合） / Ordinary action')
                    normal_go = gr.Button('执行普通行动 / Perform action')
                with gr.Tab('准备战斗 / Battle'):
                    enemy = gr.Dropdown(label='遭遇或试炼（整场战斗计一个剧情回合） / Encounter')
                    battle_go = gr.Button('开始战斗 / Start battle')
                with gr.Tab('战斗交锋 / Combat'):
                    combat_action = gr.Dropdown(label='交锋行动 / Combat action')
                    combat_go = gr.Button('执行交锋 / Act')
                    skill = gr.Dropdown(label='指定能力 / Ability')
                    skill_go = gr.Button('使用所选能力 / Use ability')
                    ai_refresh = gr.Button('生成 AI 战术推荐')
                    ai_tactic = gr.Dropdown(label='AI生成推荐 · 含代价与效果')
                    ai_go = gr.Button('执行所选 AI 战术')
                    ai_note = gr.Markdown()
                    free = gr.Textbox(label='战术方案（数值交锋）', placeholder='描述攻击目标和具体做法；剧情自由行动请使用下方独立入口')
                    free_go = gr.Button('理解战术并预览伤害')
                with gr.Accordion('AI 情景行动推荐', open=False):
                    suggest_refresh = gr.Button('生成当前情景推荐')
                    suggest = gr.Dropdown(label='AI生成推荐 · 只执行对应行动')
                    suggest_go = gr.Button('执行所选情景推荐')
                    suggest_note = gr.Markdown('生成需要文本模型；战斗中请使用战术推荐。')
                with gr.Accordion('自由行动 · 直接生成剧情', open=True):
                    free_story = gr.Textbox(label='你想让陆凌霄做什么？', lines=2, placeholder='例如：沿着留下的冰霜痕迹追踪，去寻找沈霁月。')
                    free_story_go = gr.Button('执行自由行动',variant='primary')
                with gr.Accordion('故事分支', open=False):
                    branches = gr.Dropdown(label='已保存节点')
                    rewind = gr.Button('回到节点')
                    save = gr.Button('导出完整存档')
                    download = gr.File(label='下载存档', visible=False)
                    upload = gr.UploadButton('导入旧版或新版存档副本', file_types=['.zip'])
                    slot_name = gr.Textbox(value='我的冒险', label='存档槽名称')
                    with gr.Row():
                        slot_save = gr.Button('保存进度到槽位')
                        slot_refresh = gr.Button('列出存档槽')
                    slot_list = gr.Dropdown(label='已有存档槽')
                    slot_load = gr.Button('载入所选存档槽')
                    slot_note = gr.Markdown()
            with gr.Column(scale=2):
                with gr.Tab('⚙️ 系统 / System'):
                    system = gr.HTML()
                    with gr.Accordion('🤝 好感度',open=False):
                        affinity_panel=gr.HTML()
                    with gr.Accordion('✨ 能力', open=False):
                        abilities = gr.Markdown()
                        outside_skill = gr.Dropdown(label='选择战外能力')
                        heal_go = gr.Button('战外使用所选能力')
                        echoes = gr.Dropdown(label='尚未融合的残响')
                        fuse = gr.Button('融合所选残响')
                    with gr.Accordion('🛡️ 装备', open=False):
                        equipment = gr.Markdown()
                        instance = gr.Dropdown(label='装备实例')
                        slot = gr.Dropdown([('武器', 'weapon'), ('头部', 'head'), ('胸甲', 'chest'), ('手部', 'hands'), ('腿部', 'legs'), ('足部', 'feet'), ('饰品', 'accessory')], label='部位')
                        gear_preview = gr.Markdown('选择装备与部位后可预览属性变化。')
                        wear = gr.Button('穿戴'); remove = gr.Button('卸下')
                with gr.Tab('🎒 背包 / Inventory'):
                    inventory = gr.Markdown()
                    quantity = gr.Number(value=1, minimum=1, precision=0, label='核心数量')
                    core_action = gr.Radio([('净化原核', 'refine'), ('吸收净核', 'absorb_core')], value='refine', label='预览类型')
                    with gr.Row():
                        one = gr.Button('1'); five = gr.Button('5'); maximum = gr.Button('最大可操作量')
                    with gr.Row():
                        preview = gr.Button('预览结算'); refine = gr.Button('批量净化'); absorb = gr.Button('批量吸收')
                    preview_text = gr.Markdown(label='预览结果')
                    recipe = gr.Dropdown(choices=[], label='当前可打造的装备（已解锁且材料足够）')
                    craft_cost = gr.Markdown('当前没有可打造装备。')
                    craft = gr.Button('打造装备', interactive=False)
                with gr.Tab('📖 图鉴 / Codex'):
                    codex = gr.HTML()
                    codex_enemy = gr.Dropdown(label='已解锁普通魔物')
                    codex_fight = gr.Button('挑战所选魔物')
                with gr.Accordion('插图与配音设置', open=False):
                    image_status = gr.Markdown('尚无场景图。')
                    autoimage = gr.Checkbox(value=True, label='自动配图 / Auto image')
                    with gr.Row():
                        image_retry = gr.Button('生成或恢复配图')
                        image_stop = gr.Button('停止等待图片')
                    speech_player = gr.Audio(label='当前剧情配音', type='filepath', autoplay=True, interactive=False)
                    speech_note = gr.Markdown('自动配音默认关闭。')
                    autovoice = gr.Checkbox(value=False, label='自动配音 / Auto voice')
                    voice_autoplay = gr.Checkbox(value=True, label='配音完成后自动播放')
                    speech_retry = gr.Button('生成或重试当前配音')
                    played_node = gr.State('')
                with gr.Accordion('场景氛围音', open=False):
                    ambience = gr.Dropdown([('营地', 'camp'), ('废墟', 'ruins'), ('通天塔', 'tower')], value='camp', label='场景')
                    volume = gr.Slider(0, 1, value=.3, label='音量')
                    ambient_go = gr.Button('准备本地氛围音')
                    ambient_player = gr.Audio(label='氛围音（手动播放）', type='filepath', interactive=False, loop=True)
                with gr.Accordion('人物档案', open=False):
                    gr.Markdown('你操纵的角色是**陆凌霄**。人物参考图用于档案展示，场景图尚未使用参考图作为生成条件。')
                    for character_id, card in CHARACTERS.items():
                        with gr.Accordion(card['name'], open=False):
                            with gr.Row():
                                gr.Image(value=portrait_path(ROOT, character_id), label=card['name'] + ' · 人物参考', height=280, interactive=False)
                                gr.Markdown(profile_text(ROOT, character_id))
                with gr.Accordion('场景反馈与体验记录', open=False):
                    rating = gr.Slider(1, 5, value=4, step=1, label='图文质量')
                    tags = gr.CheckboxGroup(['外貌不一致', '装备错误', '体格超前', '人物性格不符', '图文不匹配'], label='问题')
                    observation = gr.Textbox(label='观察或建议', lines=2)
                    confirmed = gr.Checkbox(label='将没有问题标签的环境观察带入本分支后续叙述', value=False)
                    feedback_save = gr.Button('保存场景反馈')
                    feedback_note = gr.Markdown()
                    participant = gr.Textbox(label='体验者代号')
                    task = gr.Dropdown(['连续行动', '分支存档', '多人投票', '界面阅读'], label='体验任务')
                    completed = gr.Radio([('完成', 'yes'), ('未完成', 'no')], label='任务结果')
                    usability = gr.Radio([1, 2, 3, 4, 5], label='易用性评分')
                    play_note = gr.Textbox(label='卡住的位置和改进建议', lines=2)
                    play_save = gr.Button('保存体验反馈')
                    play_result = gr.Markdown()
        with gr.Accordion('多人共同决策', open=False):
            gr.Markdown('共同为陆凌霄投票；独行试炼和塔内战斗仍由主角独自完成。')
            with gr.Row():
                room_create = gr.Button('为当前冒险创建房间')
                invite = gr.Textbox(label='邀请口令', type='password')
                nickname = gr.Textbox(value='同行者', label='昵称')
                room_join = gr.Button('加入房间')
            room_info = gr.JSON(label='房间状态')
            vote_kind = gr.Dropdown(['剧情', '普通', '准备战斗', '战斗交锋', '能力', 'AI战术', 'AI情景',
                                     '净化', '吸收', '融合', '打造', '穿戴', '卸下', '战外能力', '图鉴挑战'],
                                    value='剧情', label='投票使用哪个区域的当前选择')
            with gr.Row():
                room_sync = gr.Button('同步房间')
                room_vote = gr.Button('投票')
                room_resolve = gr.Button('房主锁定并执行')
                room_stop = gr.Button('停止房间正文')
                room_leave = gr.Button('离开房间')
            room_note = gr.Markdown()
        outputs = [session, browser, revision, story, system, inventory, abilities, equipment, codex,
                   story_action, normal_action, enemy, combat_action, skill, outside_skill, instance, branches, echoes, codex_enemy, note, story_guide, recipe, craft_cost, craft, affinity_panel]
        def restore_media_preferences(saved):
            saved = saved if isinstance(saved, dict) else {}
            return (bool(saved.get('image', True)), bool(saved.get('voice', False)), bool(saved.get('play', True)))
        def save_media_preferences(image, voice, play):
            return {'image': bool(image), 'voice': bool(voice), 'play': bool(play)}
        app.load(restore_media_preferences, [media_preferences], [autoimage, autovoice, voice_autoplay])
        for switch in (autoimage, autovoice, voice_autoplay):
            switch.change(save_media_preferences, [autoimage, autovoice, voice_autoplay], [media_preferences], show_progress='hidden')
        start.click(new, [session, checkpoint, approach, style, perspective, content_level], outputs)
        def restore_browser(saved):
            try:
                return (*show(saved, '已恢复浏览器中的冒险。'), gr.update(value=(saved or {}).get('locale', 'zh-CN')))
            except (ValueError, PermissionError, KeyError):
                return (*show({}, '本地进度不可用，请导入完整存档。'), gr.update(value='zh-CN'))
        app.load(restore_browser, [browser], [*outputs, locale])
        def set_locale(s, language):
            s = dict(s or {}); s['locale'] = language
            return show(s, 'Language set; future stories use English.' if language == 'en-US' else '语言已切换；后续故事使用中文。')
        locale.change(set_locale, [session, locale], outputs)
        ambient_go.click(lambda kind, vol: ambient(ROOT, kind, vol), [ambience, volume], ambient_player)
        refresh.click(lambda s: show(s), [session], outputs, api_name='refresh_v2')
        async def direct(s, r, a, m, images, voice):
            async for value in act(s, r, a, mode=m, images=images, voice=voice): yield value
        async def battle(s, r, a, m, images, voice):
            async for value in act(s, r, 'start_encounter', a, mode=m, images=images, voice=voice): yield value
        async def codex_battle(s, r, a, m, images, voice):
            async for value in act(s, r, 'start_encounter', a, mode=m, images=images, voice=voice, source='codex'): yield value
        async def use_skill(s, r, a, m, images, voice):
            async for value in act(s, r, 'skill', a, mode=m, images=images, voice=voice): yield value
        async def use_tactic(s, r, a, m, images, voice):
            async for value in act(s, r, 'use_tactic', a, mode=m, images=images, voice=voice): yield value
        async def use_suggestion(s, r, a, m, images, voice):
            async for value in act(s, r, 'use_suggestion', a, mode=m, images=images, voice=voice): yield value
        async def heal(s, r, a, m, images, voice):
            async for value in act(s, r, 'use_ability', a, mode=m, images=images, voice=voice): yield value
        async def fuse_echo(s, r, a, m, images, voice):
            async for value in act(s, r, 'fuse', a, mode=m, images=images, voice=voice): yield value
        async def refine_cores(s, r, n, m, images, voice):
            async for value in act(s, r, 'refine', quantity=n, mode=m, images=images, voice=voice): yield value
        async def absorb_cores(s, r, n, m, images, voice):
            async for value in act(s, r, 'absorb_core', quantity=n, mode=m, images=images, voice=voice): yield value
        async def craft_item(s, r, a, m, images, voice):
            async for value in act(s, r, 'craft_equipment', a, mode=m, images=images, voice=voice): yield value
        async def wear_item(s, r, a, b, m, images, voice):
            async for value in act(s, r, 'equip', a, item=b, mode=m, images=images, voice=voice): yield value
        async def remove_item(s, r, b, m, images, voice):
            async for value in act(s, r, 'unequip', item=b, mode=m, images=images, voice=voice): yield value
        story_event = story_go.click(direct, [session, revision, story_action, mode, autoimage, autovoice], outputs)
        normal_go.click(direct, [session, revision, normal_action, mode, autoimage, autovoice], outputs)
        battle_event = battle_go.click(battle, [session, revision, enemy, mode, autoimage, autovoice], outputs)
        codex_event = codex_fight.click(codex_battle, [session, revision, codex_enemy, mode, autoimage, autovoice], outputs)
        combat_event = combat_go.click(direct, [session, revision, combat_action, mode, autoimage, autovoice], outputs)
        skill_event = skill_go.click(use_skill, [session, revision, skill, mode, autoimage, autovoice], outputs)
        ai_event = ai_go.click(use_tactic, [session, revision, ai_tactic, mode, autoimage, autovoice], outputs)
        async def recommend(s, generation_mode):
            from .tactics_v2 import tactic_token
            try:
                require_live_mode(generation_mode)
                node = controller.store.node(s['owner'], s['cid'])
                engine.cancel_recommendation(s['owner'], s['cid'], node['id'])
                await engine.recommend_tactics(s['owner'], s['cid'], node['id'], s.get('locale', 'zh-CN'))
                current = controller.store.node(s['owner'], s['cid'])
                if current['id'] != node['id']:
                    return gr.update(choices=[], value=None), '剧情节点已变化，请在当前节点重新生成。'
                choices = []
                for index, item in enumerate(current['meta']['tactics_v2']):
                    effect = '削弱' if item['effect'] == 'weaken' else '直接伤害'
                    label = f"AI生成推荐 · {item['label']} · {item['multiplier']:.1f}倍攻击 · {item['energy_cost']}能量 · {effect}"
                    choices.append((label, tactic_token(current, index)))
                return gr.update(choices=choices, value=None), '选择一项后执行；旧节点的推荐不能用于新节点。'
            except (ValueError, PermissionError, KeyError, RuntimeError, TimeoutError) as exc:
                return gr.update(choices=[], value=None), '推荐暂不可用：' + str(exc)
        ai_refresh.click(recommend, [session, mode], [ai_tactic, ai_note])
        async def recommend_scenario(s, generation_mode):
            from .suggestions_v2 import token as suggestion_token
            try:
                require_live_mode(generation_mode)
                node = controller.store.node(s['owner'], s['cid'])
                engine.cancel_recommendation(s['owner'], s['cid'], node['id'])
                await engine.recommend_suggestions(s['owner'], s['cid'], node['id'], s.get('locale', 'zh-CN'))
                current = controller.store.node(s['owner'], s['cid'])
                if current['id'] != node['id']:
                    return gr.update(choices=[], value=None), '剧情节点已变化，请重新生成。'
                choices = [('AI生成推荐 · ' + item['label'], suggestion_token(current, index))
                           for index, item in enumerate(current['meta']['suggestions_v2'])]
                return gr.update(choices=choices, value=None), '建议保留做法；实际资源与效果以对应行动规则为准。'
            except (ValueError, PermissionError, KeyError, RuntimeError, TimeoutError) as exc:
                return gr.update(choices=[], value=None), '推荐暂不可用：' + str(exc)
        suggest_refresh.click(recommend_scenario, [session, mode], [suggest, suggest_note])
        suggest_event = suggest_go.click(use_suggestion, [session, revision, suggest, mode, autoimage, autovoice], outputs)
        async def execute_free_story(s, rev, intent, m, images, voice):
            if m!='api':
                yield show(s,'自由行动需要真实文本模型；请切换到“真实模型”。');return
            async for value in act(s,rev,'free_story',mode=m,images=images,voice=voice,intent=intent):yield value
        free_story_event=free_story_go.click(execute_free_story,[session,revision,free_story,mode,autoimage,autovoice],outputs)
        stop_story.click(lambda s: show(s, '已停止等待；未完成的正文不会提交。'), [session], outputs,
                         cancels=[story_event, battle_event, codex_event, combat_event, skill_event, ai_event, suggest_event,free_story_event], queue=False)
        async def free_prepare(s, intent, m):
            if m != 'api':
                return gr.update(choices=[], value=None), '自由战术理解需要真实文本模型；离线模式请使用基础行动。'
            try:
                node = controller.store.node(s['owner'], s['cid'])
                engine.cancel_recommendation(s['owner'], s['cid'], node['id'])
                token, proposal = await engine.understand_free_tactic(s['owner'], s['cid'], node['id'], intent)
                if controller.store.node(s['owner'], s['cid'])['id'] != node['id']:
                    return gr.update(choices=[], value=None), '剧情节点已变化，本次自由行动未执行。'
                effect = '削弱' if proposal['effect'] == 'weaken' else '直接伤害'
                label = f"自由行动 · {proposal['label']} · {proposal['multiplier']:.1f}倍攻击 · {proposal['energy_cost']}能量 · {effect}"
                return gr.update(choices=[(label, token)], value=token), '请核对模型理解的结算，再点击“执行所选 AI 战术”；原始意图会保存在本次事件中。'
            except (ValueError, PermissionError, KeyError, RuntimeError, TimeoutError) as exc:
                return gr.update(choices=[], value=None), '自由行动未执行：' + str(exc)
        free_go.click(free_prepare, [session, free, mode], [ai_tactic, ai_note])
        heal_go.click(heal, [session, revision, outside_skill, mode, autoimage, autovoice], outputs)
        fuse.click(fuse_echo, [session, revision, echoes, mode, autoimage, autovoice], outputs)
        refine.click(refine_cores, [session, revision, quantity, mode, autoimage, autovoice], outputs)
        absorb.click(absorb_cores, [session, revision, quantity, mode, autoimage, autovoice], outputs)
        craft.click(craft_item, [session, revision, recipe, mode, autoimage, autovoice], outputs)
        wear.click(wear_item, [session, revision, instance, slot, mode, autoimage, autovoice], outputs)
        remove.click(remove_item, [session, revision, slot, mode, autoimage, autovoice], outputs)
        def save_feedback(s, score, issues, text, use_context):
            try:
                node = controller.store.node(s['owner'], s['cid'])
                text = str(text or '')[:1000]; issues = issues or []
                blocked = bool(re.search(r'升级|突破|装备|发色|白发|黑发|蓝瞳|紫瞳|小孩|儿童|成年|外貌|ULTRA|SSS', text, re.I))
                controller.store.feedback(s['owner'], s['cid'], node['id'],
                    {'rating': score, 'tags': issues, 'observation': text,
                     'confirmed': bool(use_context and not issues and not blocked)})
                return '反馈已保存。' + ('人物或规则问题只作反馈，不作为环境事实。' if use_context and (issues or blocked) else '')
            except (ValueError, PermissionError, KeyError) as exc:
                return '未保存：' + str(exc)
        feedback_save.click(save_feedback, [session, rating, tags, observation, confirmed], feedback_note)
        def save_playtest(s, alias, selected_task, outcome, score, text):
            try:
                if not str(alias or '').strip() or not selected_task or outcome not in ('yes','no') or score not in (1,2,3,4,5):
                    raise ValueError('请填写代号、任务、结果与评分。')
                node = controller.store.node(s['owner'], s['cid'])
                controller.store.feedback(s['owner'], s['cid'], node['id'],
                    {'source': 'peer_playtest', 'participant': str(alias).strip()[:60], 'task': selected_task,
                     'completed': outcome == 'yes', 'usability': score, 'note': str(text or '')[:1500], 'confirmed': False})
                return '体验反馈已保存。'
            except (ValueError, PermissionError, KeyError) as exc:
                return '未保存：' + str(exc)
        play_save.click(save_playtest, [session, participant, task, completed, usability, play_note], play_result)
        def show_gear_preview(s, item, part):
            if not s or not s.get('cid') or not item or not part:
                return '选择装备与部位后可预览属性变化。'
            try:
                return preview_equipment(controller.store.node(s['owner'], s['cid'])['state'], item, part)
            except (ValueError, PermissionError) as exc:
                return str(exc)
        instance.change(show_gear_preview, [session, instance, slot], gear_preview)
        slot.change(show_gear_preview, [session, instance, slot], gear_preview)
        def describe_craft(s, item_id):
            if not s or not s.get('cid') or item_id not in EQUIPMENT:return '请先选择可打造的装备。'
            try:
                state=controller.store.node(s['owner'],s['cid'])['state']
                return '**打造消耗：** '+format_recipe(EQUIPMENT[item_id]['recipe'],state['inventory'])
            except (KeyError,ValueError,PermissionError):return '请重新加载当前冒险。'
        recipe.change(describe_craft,[session,recipe],craft_cost)
        def current_image(s):
            if not s or not s.get('cid'):
                return None, '尚无场景图。'
            try:
                return displayed_image(controller.store, s['owner'], s['cid'])
            except (ValueError, PermissionError):
                return None, '无法读取当前节点配图。'
        timer = gr.Timer(2)
        timer.tick(current_image, [session], [picture, image_status], show_progress='hidden')
        shown_recommendations = gr.State('')
        def current_recommendations(s, shown):
            from .tactics_v2 import tactic_token
            from .suggestions_v2 import token as suggestion_token
            if not s or not s.get('cid'):
                return gr.update(), gr.update(), gr.update(), gr.update(), shown
            try:
                node = controller.store.node(s['owner'], s['cid'])
                key = (s['owner'], s['cid'], node['id'])
                job = engine.recommendation_jobs.get(key, {})
                pending = 'pending:' + node['id']
                if job.get('status') == 'succeeded' and shown != node['id']:
                    if job.get('kind') == 'tactics':
                        choices = []
                        for i, item in enumerate(node.get('meta', {}).get('tactics_v2', [])):
                            effect = '削弱' if item['effect'] == 'weaken' else '直接伤害'
                            choices.append((f"AI生成推荐 · {item['label']} · {item['multiplier']:.1f}倍攻击 · {item['energy_cost']}能量 · {effect}", tactic_token(node, i)))
                        return gr.update(choices=choices, value=None), '战术推荐已更新。', gr.update(choices=[], value=None), gr.update(), node['id']
                    choices = [('AI生成推荐 · '+item['label'], suggestion_token(node, i))
                               for i, item in enumerate(node.get('meta', {}).get('suggestions_v2', []))]
                    return gr.update(choices=[], value=None), gr.update(), gr.update(choices=choices, value=None), '情景推荐已更新。', node['id']
                if shown not in (node['id'], pending):
                    text = 'AI推荐正在后台生成。' if job.get('status') == 'running' else '可手动生成当前节点的AI推荐。'
                    return gr.update(choices=[], value=None), text, gr.update(choices=[], value=None), text, pending
                if job.get('status') == 'failed' and shown == pending:
                    return gr.update(), '推荐暂不可用，可手动重试。', gr.update(), '推荐暂不可用，可手动重试。', node['id']
                return gr.update(), gr.update(), gr.update(), gr.update(), shown
            except (ValueError, PermissionError, KeyError):
                return gr.update(), gr.update(), gr.update(), gr.update(), shown
        timer.tick(current_recommendations, [session, shown_recommendations],
                   [ai_tactic, ai_note, suggest, suggest_note, shown_recommendations], show_progress='hidden')
        async def resume_image(s, generation_mode):
            try:
                require_live_mode(generation_mode)
                node = reading_node(controller.store, s['owner'], s['cid'])
                if node['state'].get('schema') != 2 or not node.get('meta', {}).get('scene'):
                    raise ValueError('该节点缺少新版场景记录')
                engine._spawn_image(s['owner'], s['cid'], node['id'])
                return '正在后台生成或恢复当前节点配图。'
            except (ValueError, PermissionError, KeyError) as exc:
                return '配图未启动：' + str(exc)
        def cancel_image(s):
            try:
                node = reading_node(controller.store, s['owner'], s['cid'])
                stopped = engine.stop_image(s['owner'], s['cid'], node['id'])
                return '已停止等待，已提交任务可恢复。' if stopped else '当前节点没有运行中的配图任务。'
            except (ValueError, PermissionError, KeyError) as exc:
                return str(exc)
        image_retry.click(resume_image, [session, mode], image_status)
        image_stop.click(cancel_image, [session], image_status)
        async def resume_speech(s, generation_mode):
            try:
                require_live_mode(generation_mode)
                node = reading_node(controller.store, s['owner'], s['cid'])
                if not node.get('text'):
                    raise ValueError('当前没有可朗读的正文')
                engine._spawn_speech(s['owner'], s['cid'], node['id'])
                return '正在后台生成配音。'
            except (ValueError, PermissionError, KeyError) as exc:
                return '配音未启动：' + str(exc)
        speech_retry.click(resume_speech, [session, mode], speech_note)
        voice_autoplay.change(lambda enabled: gr.update(autoplay=bool(enabled)), [voice_autoplay], [speech_player])
        def current_speech(s, last, enabled):
            if not s or not s.get('cid'):
                return None, '创建冒险后可生成配音。', ''
            try:
                node = reading_node(controller.store, s['owner'], s['cid'])
                job = engine.speech_jobs.get((s['owner'], s['cid'], node['id']), {})
                if job.get('status') == 'succeeded' and node['id'] != last:
                    return job['path'], job.get('segmentation', '配音完成'), node['id']
                if job.get('status') == 'succeeded':
                    return gr.update(), job.get('segmentation', '配音完成'), last
                if job.get('status') == 'failed':
                    return None, job.get('message', '配音失败，可继续游玩并重试。'), 'pending:' + node['id']
                if last not in (node['id'], 'pending:' + node['id']):
                    return None, ('正在生成配音…' if job.get('status') == 'running' else '当前节点尚无配音，可手动生成。'), 'pending:' + node['id']
                return gr.update(), ('正在生成配音…' if job.get('status') == 'running' else '当前节点尚无配音，可手动生成。'), last
            except (ValueError, PermissionError, KeyError):
                return gr.update(), '当前配音不可用。', last
        timer.tick(current_speech, [session, played_node, autovoice], [speech_player, speech_note, played_node], show_progress='hidden')
        one.click(lambda: 1, None, quantity)
        five.click(lambda: 5, None, quantity)
        def maximum_cores(s, action):
            try:
                state = controller.store.node(s['owner'], s['cid'])['state']
                count = min(50, state['inventory'].get('raw_core' if action == 'refine' else 'clean_core', 0), state['energy'] // 8)
                while count:
                    try:
                        preview_resource_action(state, {'action': action, 'quantity': count})
                        return count
                    except ValueError:
                        count -= 1
                return 1
            except (ValueError, TypeError, KeyError, PermissionError):
                return 1
        maximum.click(maximum_cores, [session, core_action], quantity)
        def preview_refine(s, n, action):
            try:
                if not s or not s.get('owner') or not s.get('cid'):
                    return '请先创建或加载冒险，再操作核心。'
                state = controller.store.node(s['owner'], s['cid'])['state']
                result = preview_resource_action(state, {'action': action, 'quantity': int(n)})
                changes = format_stats(result['changes'])
                return f"预计操作 {result['quantity']} 颗；变化：{changes}；异能评级：{result['ability_rank']}。"
            except (ValueError, TypeError) as exc:
                return str(exc) if isinstance(exc, ValueError) else '请输入有效的核心数量。'
            except (KeyError, PermissionError):
                return '当前冒险不可用，请重新加载存档后再试。'
        preview.click(preview_refine, [session, quantity, core_action], preview_text)
        def select_branch(s, nid):
            try:
                if s.get('room_token'):
                    raise ValueError('请先离开协作房间再回溯分支')
                controller.store.select(s['owner'], s['cid'], nid)
                return show(s, '已回到选中节点；后续行动将建立新分支。')
            except (ValueError, TypeError, KeyError, PermissionError) as exc:
                return show(s, str(exc))
        rewind.click(select_branch, [session, branches], outputs)
        def export_save(s):
            if not s or not s.get('cid'):
                raise gr.Error('请先创建或导入冒险')
            path = controller.store.export_bundle(s['owner'], s['cid'], ROOT / 'output' / 'v2-exports')
            return gr.update(value=str(path), visible=True)
        save.click(export_save, [session], download)
        def import_save(s, uploaded):
            if not uploaded:
                return show(s, '请选择存档。')
            s = dict(s or {})
            if s.get('room_token'):
                return show(s, '请先离开协作房间，再导入个人存档。')
            s.setdefault('owner', uuid.uuid4().hex)
            try:
                s['cid'] = controller.store.import_bundle(s['owner'], Path(uploaded), migrate_v2=True)
                return show(s, '已导入为独立副本；原存档未更改。')
            except (ValueError, TypeError, PermissionError, OSError) as exc:
                return show(s, '导入失败：' + str(exc))
        upload.upload(import_save, [session, upload], outputs)
        def slots(s):
            try:
                entries = controller.store.slots(s['owner'])
                return gr.update(choices=[(x['label'] + ' · ' + x['mode'], x['id']) for x in entries], value=None), '存档槽已更新。'
            except (KeyError, PermissionError, ValueError) as exc:
                return gr.update(choices=[], value=None), str(exc)
        def save_slot(s, name):
            try:
                if s.get('room_token'):raise ValueError('请离开房间后保存个人进度')
                controller.store.save_slot(s['owner'], s['cid'], name)
                options, _ = slots(s)
                return options, '当前节点已保存到槽位。'
            except (KeyError, PermissionError, ValueError) as exc:
                return gr.update(), str(exc)
        def load_slot(s, slot_id):
            try:
                if s.get('room_token'):raise ValueError('请离开房间后载入个人进度')
                result = controller.store.load_slot(s['owner'], slot_id)
                s = dict(s, cid=result['campaign_id'])
                return show(s, '已载入存档槽。')
            except (KeyError, PermissionError, ValueError) as exc:
                return show(s, '载入失败：' + str(exc))
        slot_refresh.click(slots, [session], [slot_list, slot_note])
        slot_save.click(save_slot, [session, slot_name], [slot_list, slot_note])
        slot_load.click(load_slot, [session, slot_list], outputs)
        def create_room(s):
            try:
                if s.get('room_token'):
                    raise ValueError('请先离开当前房间')
                room = rooms.create(s['owner'], s['cid'])
                s = dict(s, room_token=room['host_token'], personal_owner=s['owner'], personal_cid=s['cid'])
                return (*show(s, '房间已创建；请妥善分享邀请口令。'), room['invite_token'], rooms.snapshot(room['host_token']), '房主已加入。')
            except (ValueError, KeyError, PermissionError) as exc:
                return (*show(s, str(exc)), gr.update(), {}, str(exc))
        room_create.click(create_room, [session], [*outputs, invite, room_info, room_note])

        def join_room(s, code, name):
            try:
                s = dict(s or {})
                if s.get('room_token'):
                    raise ValueError('请先离开当前房间')
                joined = rooms.join(code, name); token = joined['member_token']
                snapshot = rooms.snapshot(token)
                s = {'owner': snapshot['owner'], 'cid': snapshot['campaign_id'], 'room_token': token,
                     'personal_owner': s.get('owner'), 'personal_cid': s.get('cid'), 'locale': s.get('locale', 'zh-CN')}
                return (*show(s, '已加入房间，行动需投票。'), snapshot, '已加入。')
            except (ValueError, KeyError, PermissionError) as exc:
                return (*show(s, str(exc)), {}, str(exc))
        room_join.click(join_room, [session, invite, nickname], [*outputs, room_info, room_note])

        def sync_room(s):
            try:
                snapshot = rooms.snapshot(s['room_token'])
                return (*show(s, '房间已同步。'), snapshot, '已同步。')
            except (ValueError, KeyError, PermissionError) as exc:
                return (*show(s, str(exc)), {}, str(exc))
        room_sync.click(sync_room, [session], [*outputs, room_info, room_note])

        def selected_request(kind, story_value, normal_value, enemy_value, combat_value, skill_value, ai_value, suggestion_value,
                             quantity_value, recipe_value, instance_value, slot_value, echo_value, outside_value, codex_value):
            if kind == '剧情': return {'action': story_value}
            if kind == '普通': return {'action': normal_value}
            if kind == '准备战斗':
                return {'action': 'realm_trial'} if enemy_value == 'realm_trial' else {'action': 'start_encounter', 'monster_id': enemy_value}
            if kind == '战斗交锋': return {'action': combat_value}
            if kind == '能力': return {'action': 'skill', 'skill_id': skill_value}
            if kind == 'AI战术': return {'action': 'use_tactic', 'token': ai_value}
            if kind == 'AI情景': return {'action': 'use_suggestion', 'token': suggestion_value}
            if kind in ('净化', '吸收'):
                return {'action': 'refine' if kind == '净化' else 'absorb_core', 'quantity': int(quantity_value)}
            if kind == '融合': return {'action': 'fuse', 'target': echo_value}
            if kind == '打造': return {'action': 'craft_equipment', 'item_id': recipe_value}
            if kind == '穿戴': return {'action': 'equip', 'instance_id': instance_value, 'slot': slot_value}
            if kind == '卸下': return {'action': 'unequip', 'slot': slot_value}
            if kind == '战外能力': return {'action': 'use_ability', 'target': outside_value}
            if kind == '图鉴挑战': return {'action': 'start_encounter', 'monster_id': codex_value, 'source': 'codex'}
            raise ValueError('请选择投票类别')

        selections = [vote_kind, story_action, normal_action, enemy, combat_action, skill, ai_tactic, suggest,
                      quantity, recipe, instance, slot, echoes, outside_skill, codex_enemy]
        def vote(s, rev, *selected):
            try:
                node = controller.store.node(s['owner'], s['cid'])
                request = selected_request(*selected)
                token = room_choice(node, request)
                return rooms.vote(s['room_token'], int(rev), token), '已投票。'
            except (ValueError, KeyError, PermissionError, TypeError) as exc:
                return gr.update(), '投票失败：' + str(exc)
        room_vote.click(vote, [session, revision, *selections], [room_info, room_note])

        async def resolve_room(s, rev, m, images, voice, *selected):
            locked = None; saved = False
            try:
                node = controller.store.node(s['owner'], s['cid'])
                snapshot = rooms.snapshot(s['room_token'])
                tie = snapshot.get('retry_action_id') or room_choice(node, selected_request(*selected))
                locked = rooms.lock_round(s['room_token'], int(rev), tie)
                async for update in engine.execute_v2(s['owner'], s['cid'], locked['request'], locked['revision'],
                    operation_id=locked['operation_id'], offline=(m == 'offline'), with_image=bool(images), auto_voice=bool(voice),
                    auto_recommend=(m == 'api'), language=s.get('locale', 'zh-CN')):
                    saved = bool(update.get('node'))
                    yield (*show(s, update['stage'], update.get('text') if update.get('busy') else None), gr.update(), update['stage'])
                rooms.finish_round(s['room_token'], int(rev), saved)
                locked = None
                yield (*show(s, '投票行动已结算。' if saved else '生成未完成，可重试相同投票行动。'), rooms.snapshot(s['room_token']), '已更新房间。')
            except asyncio.CancelledError:
                if locked:
                    rooms.finish_round(s['room_token'], int(rev), saved)
                raise
            except (ValueError, KeyError, PermissionError, TypeError) as exc:
                if locked:
                    rooms.finish_round(s['room_token'], int(rev), False)
                yield (*show(s, str(exc)), gr.update(), str(exc))
        room_event = room_resolve.click(resolve_room, [session, revision, mode, autoimage, autovoice, *selections], [*outputs, room_info, room_note])
        room_stop.click(fn=None, cancels=[room_event], queue=False)

        def leave(s):
            personal = {'owner': s.get('personal_owner') or uuid.uuid4().hex, 'locale': s.get('locale', 'zh-CN')}
            if s.get('personal_cid'): personal['cid'] = s['personal_cid']
            return (*show(personal, '已离开协作房间。'), {}, '已离开。')
        room_leave.click(leave, [session], [*outputs, room_info, room_note])
    app.queue(default_concurrency_limit=3)
    app.duhe_controller = controller
    app.duhe_engine = engine
    return app


def main():
    css = (ROOT / 'duhe' / 'ui.css').read_text(encoding='utf-8') + artwork_css(ROOT)
    app = build_draft()
    app.launch(server_name='127.0.0.1', server_port=int(os.getenv('DUHE_V2_PORT', '7865')),
               favicon_path=str(ROOT / 'output' / 'brand' / 'game-emblem.svg'),
               head='<link rel="icon" type="image/svg+xml" href="/favicon.ico?v=duhe-core-20261112">',
               inbrowser=False, theme=gr.themes.Soft(primary_hue='blue', neutral_hue='slate'), css=css,
               allowed_paths=[str(ROOT / 'output'), str(ROOT / 'data' / 'v2-draft_media')],
               blocked_paths=[str(ROOT / '.env'), str(ROOT / 'data' / 'browser-state.key'),
                              str(ROOT / 'data' / 'stories.sqlite'), str(ROOT / 'data' / 'v2-draft.sqlite'),
                              str(ROOT / 'data' / 'api_budget.sqlite')],
               show_error=False, footer_links=[])


if __name__ == '__main__':
    main()
