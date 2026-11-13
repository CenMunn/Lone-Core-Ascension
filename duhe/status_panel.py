"""Player-facing, rule-backed status explanations and accessible gauges."""
import html
from .progression import info as growth_info
from .rules import RULES
from .world import REALMS

BODY={'underfed':'营养不足、瘦削','recovering':'精瘦恢复、线条初显','trained':'训练成型、强健匀称','hardened':'久经战斗、肌肉强健'}
PATHS={
    'hp':'M12 20s-8-4.6-8-10a4.5 4.5 0 0 1 8-3 4.5 4.5 0 0 1 8 3c0 5.4-8 10-8 10Z',
    'energy':'m13 2-8 12h6l-1 8 9-13h-6l1-7Z',
    'pollution':'M12 3c-2 4-7 8-7 12a7 7 0 0 0 14 0c0-4-5-8-7-12Z M12 11v4 M12 18h.01',
    'ability':'m12 3 8 5v8l-8 5-8-5V8l8-5Z M12 8v8 M8 12h8',
    'xp':'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z',
    'realm':'M4 19h16 M6 16V8l6-5 6 5v8 M9 16v-5h6v5'}


def icon(kind):
    return f'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{PATHS[kind]}"/></svg>'


def pollution_help(en=False):
    if en:return 'At 65+: no core/echo absorption or cultivation advancement. At 85+: core combat skills blocked. At 90+: exploration and solo trials blocked; each incoming hit, including guard, costs 8 additional HP. At 95+: raw-core refining blocked. 100 does not cause automatic death outside combat. Purify costs 1 clean core and removes 20 contamination (25 with Core Scan); detox costs 2 food and 20 energy, removing 15.'
    return '0–64：可正常选择符合其他条件的行动。65起：不能吸收净核、融合残响或突破境界；85起：不能施展核心战斗技能；90起：不能探索/进入独行试炼，每次承受攻击（含防御）额外扣8生命；95起：不能净化原核。污染100不等于立即死亡，战斗风险仍很高。消耗1净核可降20污染（解锁核心扫描后25）；隔离排毒消耗2食物、20能量，降低15污染。'


def render(state,event=None,en=False):
    esc=lambda x:html.escape(str(x));g=growth_info(state);stage=RULES['stages'][state['realm_index']*4+state['realm_stage']]
    rank='低于F-' if state['ability_rank']=='UNRANKED' else state['ability_rank']
    if en and rank=='低于F-':rank='Below F-'
    def card(kind,label,value,description,current=None,maximum=100,tone='normal'):
        bar='' if current is None else f'<progress value="{max(0,min(current,maximum))}" max="{maximum}" aria-label="{esc(label)}"></progress>'
        return f'<details class="status-card {tone}"><summary><span class="status-label">{icon(kind)}{esc(label)}</span><strong>{esc(value)}</strong>{bar}<span class="status-more">{"Details" if en else "点击查看说明"}</span></summary><p>{esc(description)}</p></details>'
    required=g['required'];ability_value=f"{g['current']}/{required}" if required else ('Final trial' if en else 'UR上限 · 终战解锁ULTRA')
    if state['ability_rank']=='ULTRA':ability_value='ULTRA · MAX'
    cards=[card('hp','生命 HP' if not en else 'HP',f"{state['hp']}/{state['max_hp']}",'生命归零结束当前分支，可读档重试。进食休整消耗1食物，最多恢复80生命；升级增加最大生命，不自动回满。' if not en else 'Zero HP ends this branch; saved nodes remain available. Rest costs 1 food and restores up to 80 HP. A larger HP cap does not heal current damage.',state['hp'],state['max_hp'],'danger' if state['hp']<state['max_hp']*.3 else 'normal'),
           card('energy','核心能量' if not en else 'Energy',f"{state['energy']}/100",'训练消耗20，探索/净化/吸收净核消耗8，核心技能消耗12。休整最多恢复70，防御恢复量受战术影响。' if not en else 'Training costs 20; exploration, refining and core absorption cost 8; combat skills cost 12. Rest restores up to 70; guard recovery depends on tactics.',state['energy']),
           card('pollution','污染' if not en else 'Contamination',f"{state['pollution']}/100",pollution_help(en),state['pollution'],100,'danger' if state['pollution']>=65 else 'warning'),
           card('ability',('异能EXP · ' if not en else 'Ability XP · ')+rank,ability_value,('异能经验独立累计；吸收1净核当前获得'+str(g['core_xp'])+'异能EXP，达到阈值自动升一级。每级最大生命+6、攻击+2；UR之后必须完成终战。原核须先净化，净核也可留作锻造、排污或突破材料。' if not en else f"Ability XP is separate from cultivation XP. One clean core currently gives {g['core_xp']} XP. Thresholds vary by rank. Each rank adds 6 maximum HP and 2 attack. ULTRA requires the final trial."),g['current'] if required else 100,required or 100),
           card('xp','修炼EXP' if not en else 'Cultivation XP',f"{state['xp']}/{stage['xp']}",('经验余额/当前阶段所需经验。突破还需要'+str(stage['clean_core'])+'净核、本阶段独行试炼且污染低于65。训练+18，胜战和吸收净核也会增加；不会仅因经验足够自动升境。' if not en else f"Available XP / stage cost. Advancement also requires {stage['clean_core']} clean cores, the stage solo trial, and contamination below 65. Training gives 18; victories and core absorption also contribute."),state['xp'],stage['xp']),
           card('realm','境界与体格' if not en else 'Cultivation & physique',REALMS[state['realm_index']]+'·'+stage['phase'],('当前体格：'+BODY[state['body_stage']]+'。训练、营养恢复和时间决定外在肌肉阶段；异能强化提升体能，不会一口核心变成成熟体魄。' if not en else 'Visible physique changes gradually through training, nutrition and recovery. Ability ranks strengthen the existing body; a single core does not replace months of conditioning.'))]
    heading='Lu Lingxiao · Status' if en else '陆凌霄 · 角色状态'
    meta=(f"Day {state['day']} · Training {state['training_days']} · Floor {state['tower_floor']} · Countdown {state['countdown']} turns · Clean cores {state['inventory']['clean_core']}" if en else f"第{state['day']}天 · 训练{state['training_days']}天 · 塔层{state['tower_floor']}/100 · 终焉倒计时{state['countdown']}回合 · 累计吸收{state.get('cores_absorbed',0)}枚净核 · 背包：原核{state['inventory']['raw_core']} / 净核{state['inventory']['clean_core']} / 口粮{state['inventory']['food']}")
    changes=(event or {}).get('changes',{});labels={'hp':'生命','max_hp':'最大生命','energy':'能量','pollution':'污染','xp':'修炼EXP','ability_xp':'异能EXP'}
    delta=' · '.join(f"{k if en else labels.get(k,k)} {v:+d}" for k,v in changes.items())
    if delta:meta+=' | '+('This turn: ' if en else '本轮结算：')+delta
    badge='<p class="mode-badge">章节演示存档 · 非正常通关 / Demonstration checkpoint</p>' if state.get('mode')=='demo' else ''
    return f'<section class="player-status" aria-label="{heading}"><h2>{heading}</h2>{badge}<div class="status-grid">'+''.join(cards)+f'</div><p class="status-meta">{esc(meta)}</p></section>'


WORLD_INTRO='''### 核心纪元 · 你需要知道的世界

末世第七年，天空黑环与地下城改变了世界。普通人退守要塞，觉醒者猎杀魔物，用会带来污染的核心换取能源、装备与力量；并非每个人都能觉醒。

**你扮演陆凌霄**：原地下维修工，黑发蓝瞳、天赋低于F-，从瘦弱的底层幸存者开始。初遇时，SS级的白发紫瞳研究员沈霁月救下你。她和其他伙伴各有目标，你仍将独自完成关键试炼。

**独行进化系统只属于你，也是你绝不透露的秘密。** 系统面板、熔炉与任务提示只在你的意识中出现；别人可以知道公开的异能、核心和污染知识，无法看到或识别你的系统。

**两条成长线**：异能评级为F-→E→D→C→B→A→S→SS→SSS→UR，吸收净核获得异能EXP并自动升级；ULTRA需终战解锁。修炼十境从淬体到神话，每境四阶段，突破另需修炼EXP、净核和独行试炼。

**核心循环**：探索与战斗取得原核→净化为净核→选择吸收、排污、锻造或突破。体格须通过训练、进食和恢复逐渐强健。通天塔有100层、每十层有守卫，关键挑战只允许陆凌霄一人进入，真相随剧情揭开。

点击每个状态即可查看规则说明。局部分支会汇合，伤势、物资与关系仍保留；随时保存进度，为下一次选择留下退路。'''
