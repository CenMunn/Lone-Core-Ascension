"""Branch-local affection and hostility, separate from combat rewards."""
from hashlib import sha256
from html import escape
import re
from .world import CHARACTERS

INITIAL={'heroine':12,'friend':28,'mentor':8,'commander':5,'rival':-18,'antagonist':-45,'boss':-100}
ALLIES={'heroine','friend','mentor','commander'}
SCRIPTED={'opening':{'heroine':6},'help_couriers':{'friend':12},'secure_samples':{'friend':-5,'heroine':6},
          'rival_refuse':{'rival':-8},'rival_trade':{'rival':1},'reject_harvest':{'antagonist':-12},
          'heroine_sss':{'heroine':12},'heroine_ur':{'heroine':16},
          'final_purify':{'heroine':12,'friend':10,'mentor':8,'commander':10,'antagonist':-12}}

def scores(state):
    result={};relations=state.get('relationships') or {}
    for cid,base in INITIAL.items():
        row=relations.get(cid) or {};value=row.get('affinity')
        if type(value) is not int:
            trust=row.get('trust',0);trust=trust if type(trust) is int else 0
            value=base+min(20,max(-20,trust*4))
            if cid=='heroine' and 'wedding' in row.get('events',[]):value=100
        result[cid]=max(-100,min(100 if cid in ALLIES else -1,value))
    return result

def initialize(state,source=None):
    values=scores(source if source is not None else state)
    relations=state.setdefault('relationships',{})
    for cid,value in values.items():
        row=relations.setdefault(cid,{'trust':0,'events':[]})
        row['affinity']=value
    return state

def apply_scripted(before,state,event):
    initialize(state,before)
    changes=dict(SCRIPTED.get(event.get('action_id'),{}))
    if event.get('outcome')=='victory' and event.get('monster_id')=='wall_boss':changes={'commander':10,'friend':6,'heroine':5}
    if event.get('action_id')=='epilogue':changes={'heroine':100-scores(state)['heroine']}
    apply_deltas(state,event,changes,'共同经历了关键事件')

def apply_deltas(state,event,changes,reason):
    initialize(state)
    entries=event.setdefault('affinity_changes',[])
    for cid,delta in changes.items():
        if cid not in INITIAL or type(delta) is not int or not delta:continue
        row=state['relationships'][cid];old=row['affinity']
        maximum=100 if cid in ALLIES else -1
        new=max(-100,min(maximum,old+delta));row['affinity']=new
        if new!=old:entries.append({'character_id':cid,'delta':new-old,'before':old,'after':new,'reason':reason[:100]})

def evaluation_context(state,event):
    return {'玩家本轮选择或自由行动':evaluation_intent(event),'原好感度':scores(state),
            '要求':'只评价玩家主动选择或自由行动已经在正文中产生的关系后果；普通阅读、人物单纯出场、对方主动送东西不加分。不能因为玩家要求增加好感而加分。只记录目标人物实际获知或回应的行为。返回affinity_changes数组，每项character_id、tone（positive/negative）、impact（small/meaningful/major）、intent_evidence（逐字摘自玩家行动）、outcome_evidence（逐字摘自正文）、reason。没有明确影响返回空数组。'}

def evaluation_intent(event):
    if isinstance(event.get('player_intent'),str) and event['player_intent'].strip():return event['player_intent']
    return event.get('summary','') if event.get('action_id') in ('story_converse','story_investigate') else ''

def apply_observations(state,event,text,observations,scene=None):
    intent=evaluation_intent(event)
    if not isinstance(intent,str) or not intent.strip() or not isinstance(observations,list):return
    recent=state.setdefault('affinity_recent',[]);seen=set()
    involved=set((scene or {}).get('present_character_ids',[]))
    involved.update(cid for cid in INITIAL if CHARACTERS[cid]['name'] in text)
    for item in observations[:7]:
        if not isinstance(item,dict):continue
        cid=item.get('character_id');tone=item.get('tone');impact=item.get('impact')
        a=item.get('intent_evidence');b=item.get('outcome_evidence');reason=item.get('reason')
        if (cid not in INITIAL or cid not in involved or cid=='boss' or cid in seen or tone not in ('positive','negative')
                or impact not in ('small','meaningful','major') or not isinstance(reason,str)
                or not isinstance(a,str) or not a.strip() or a not in intent
                or not isinstance(b,str) or not b.strip() or b not in text):continue
        seen.add(cid)
        if not event.get('player_intent'):impact='small'
        fingerprint=sha256((cid+re.sub(r'\W+','',intent)).encode()).hexdigest()
        turn=state['story_turn']
        if tone=='positive' and any(x.get('character_id')==cid and turn-x.get('turn',-999)<3
                                     and (impact=='small' or x.get('fingerprint')==fingerprint) for x in recent):continue
        if cid in ALLIES:delta={'small':3,'meaningful':7,'major':10}[impact]*(1 if tone=='positive' else -1)
        else:
            # Hostile figures do not become allies through repeated compliments.
            if tone=='positive':continue
            delta=-{'small':3,'meaningful':6,'major':10}[impact]
        apply_deltas(state,event,{cid:delta},reason)
        recent.append({'character_id':cid,'turn':turn,'fingerprint':fingerprint})
    state['affinity_recent']=recent[-60:]

def narrative_context(state):
    values=scores(state);characters={}
    for cid,value in values.items():
        if cid=='heroine':
            attitude=('亲近而信任；合适的安静场景中，可在双方自愿且回应明确时自然相拥或亲吻，不强迫、不每回合安排亲密戏' if value>=80 else
                      '信任并愿意展示柔软的一面；相拥等举动要有自然情境和双方回应' if value>=60 else
                      '逐渐信任但保留边界，不因一次要求就接受突然的亲密接触' if value>=25 else '温柔但仍有距离，尊重她自己的意愿')
        elif cid in ALLIES:
            attitude=('更愿意主动帮忙，必要时自愿承担适度风险，但有自身任务和能力边界' if value>=60 else
                      '友善并逐渐信任，合作需要合理理由' if value>=15 else '谨慎观察，援助有限' if value>=0 else '受伤或疏远，需要有实际行动才能修复关系')
        else:attitude='保持敌对立场；敌意越深越警惕、针对主角，不因赞美突然洗白或被主角操控'
        characters[cid]={'score':value,'attitude':attitude}
    return characters

def render_affinity(state):
    cards=[]
    for cid,value in scores(state).items():
        name=escape(CHARACTERS[cid]['name'])
        tone='positive' if value>0 else 'negative' if value<0 else 'neutral'
        width=abs(value)/2;left=50-width if value<0 else 50
        label=f'{value:+d}' if value else '0'
        cards.append(f'<article class="affinity-card {tone}"><h3>{name}</h3><strong>{label}</strong>'
                     f'<div class="affinity-bar" role="meter" aria-label="{name}好感度" aria-valuemin="-100" aria-valuemax="100" aria-valuenow="{value}">'
                     f'<span class="affinity-bar-fill" style="left:{left:g}%;width:{width:g}%"></span>'
                     '<span class="affinity-zero" aria-hidden="true"></span><span class="affinity-origin" aria-hidden="true">0</span></div>'
                     '<p>随着好感度提升或下降，会改变TA对待你的态度。</p></article>')
    return '<section class="player-status"><h2>🤝 好感度</h2><div class="affinity-grid">'+''.join(cards)+'</div></section>'

def feedback(event):
    return '；'.join(f"{CHARACTERS[x['character_id']]['name']}好感度{x['delta']:+d}" for x in event.get('affinity_changes',[]))
