"""Shared story secrecy and text integrity checks, including legacy choices."""
import re

SECRET_RULE='独行进化系统全世界仅陆凌霄一人拥有，是他绝不对任何人透露的秘密。只有系统本身独有，其他觉醒者仍能按公开技术使用和炼化核心，不得写成只有男主能处理核心。沈霁月、周野、导师、军方和反派均不知道系统存在，也看不到提示、面板或熔炉。系统提示和指令只在主角意识中出现，激活时也在心中默念，不发出声音。主角可询问公开的异能、污染和核心知识，但不得向他人询问系统、讲解系统、展示面板或分享系统能力来源；旁人只能观察外在行动和力量，不能因此认出系统。历史中违背这条的叙述或选项不是事实，应忽略。'


def leaks_secret(text):
    text=str(text or '')
    text=re.sub(r'(?:没有|不会|绝不|从不|不能|未曾|并未)[^，。；\n]{0,50}(?:系统|进化面板|核心熔炉|任务面板)','',text)
    text=re.sub(r"\b(?:never|do not|does not|did not|won't|wouldn't)\s+(?:tell|show|explain|reveal|discuss|share)[^.?!\n]{0,100}\bsystem\b",'',text,flags=re.I)
    text=re.sub(r'供电系统|排水系统|通风系统|电力系统|防御系统|core energy system','',text,flags=re.I)
    secret=r'(?:系统|进化面板|核心熔炉|任务面板|独行进化)'
    patterns=[rf'(?:向|与|和|对|给|请).{{0,20}}(?:询问|请教|解释|透露|坦白|展示|分享|讨论|谈论|告诉|告知|介绍|研究).{{0,25}}{secret}',
              rf'(?:沈霁月|周野|顾砺山|闻峥|裴景珩|谢玄策|同伴|她|他).{{0,10}}(?:知道|发现|看见|读取|研究|问起|询问).{{0,18}}{secret}',
              rf'(?:告诉|告知|透露|展示|分享).{{0,12}}{secret}.{{0,12}}(?:沈霁月|周野|她|他|同伴)']
    if any(re.search(p,text) for p in patterns):return True
    english=re.sub(r'ask (?:the|my|his) system to','',text.lower())
    return bool(re.search(r'\b(?:tell|show|explain|reveal|discuss|share|ask)\b.{0,65}\b(?:system|solo evolution|core furnace)\b',english))


def assert_private(text):
    if leaks_secret(text):raise ValueError('系统是陆凌霄独有的秘密，不能向他人询问或透露；请改为私下复盘，或询问公开的异能与污染知识。')


def normalize_text(text,strict=True):
    text=str(text or '')
    for pattern,word in [(r'维\ufffd+刀','维修刀'),(r'陆\ufffd+霄','陆凌霄'),(r'沈\ufffd+月','沈霁月')]:text=re.sub(pattern,word,text)
    text=re.sub(r'[?？]{3,}','……',text)
    blocks=text.split('\n\n');settlements=[i for i,b in enumerate(blocks) if '系统结算' in b or 'Private system settlement' in b]
    if len(settlements)>1:text='\n\n'.join(b for i,b in enumerate(blocks) if i not in settlements[:-1])
    if '\ufffd' in text:
        if strict:raise ValueError('正文存在无法确定的缺字，本轮未提交；请重新生成，资源未结算。')
        text=re.sub('\ufffd+','〔文字缺失〕',text)
    return text


def safe_history(text):
    return '\n\n'.join(p for p in normalize_text(text,False).split('\n\n') if not leaks_secret(p) and '系统结算' not in p and 'Private system settlement' not in p)


def strip_model_settlement(text):
    return '\n\n'.join(p for p in text.split('\n\n') if '系统结算' not in p and 'Private system settlement' not in p)
