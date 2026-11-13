"""Open-ended narrative actions and evidence-based scene metadata."""
from copy import deepcopy
import json
from .world import CHARACTERS, appearance_for
from .catalog import MONSTERS
from .story_flow import continue_narrative

def prepare_free_story(state,intent,operation_id):
    if not isinstance(intent,str) or not intent.strip():raise ValueError('请先输入想做的自由行动。')
    if len(intent)>4000:raise ValueError('自由行动请控制在4000字以内，便于保留完整上下文。')
    result,event=continue_narrative(state,'continue_story',operation_id)
    event.update(action_id='free_story',player_intent=intent,free_story=True,
                 summary='陆凌霄尝试玩家输入的自由行动；具体过程与叙事结果由模型根据上下文生成。')
    return result,event

def scene_messages(text,previous,affinity_context=None):
    return [{'role':'system','content':'只提取已完成正文的最后一个场景，不编写后续。返回JSON：location、location_evidence、present（数组，每项id、evidence），可选monster_id、monster_evidence。证据必须逐字摘自正文。人物只记录结尾真实在场或直接面对面交流者；被寻找、回忆、提及、猜测去向或远程通信的人不算在场。主角始终为protagonist。没有确认的新地点就保留原地点。背景路人可以留在文字里，不要伪造固定角色ID。若输入有人物关系评估要求，按要求另外返回affinity_changes；没有关系变化返回空数组。'},
            {'role':'user','content':json.dumps({'正文':text,'原场景':previous,'人物关系评估':affinity_context,
                '固定人物ID与姓名':{key:value['name'] for key,value in CHARACTERS.items()},
                '魔物ID与名称':{key:value['name'] for key,value in MONSTERS.items()}},ensure_ascii=False)}]

def verified_scene(text,data,previous,state):
    if not isinstance(data,dict) or not isinstance(data.get('present'),list):raise ValueError('场景提取格式无效')
    cast=['protagonist']
    for item in data['present']:
        if not isinstance(item,dict):raise ValueError('场景人物格式无效')
        cid=item.get('id');evidence=item.get('evidence')
        if cid not in CHARACTERS:raise ValueError('场景人物ID无效')
        if cid=='protagonist':continue
        if not isinstance(evidence,str) or not evidence.strip() or evidence not in text:raise ValueError('场景人物缺少正文证据')
        if cid not in cast:cast.append(cid)
    frame=deepcopy(previous);frame['present_character_ids']=cast
    location=data.get('location');proof=data.get('location_evidence')
    if isinstance(location,str) and location.strip() and isinstance(proof,str) and proof.strip() and proof in text:
        frame['location']=location[:160]
    frame['chapter']=state['chapter'];frame['scene_verified']=True
    frame['main_action']=text[-600:]
    monster_id=data.get('monster_id');monster_proof=data.get('monster_evidence')
    if not state.get('combat'):
        frame.pop('monster',None)
        if monster_id in MONSTERS and isinstance(monster_proof,str) and monster_proof.strip() and monster_proof in text:
            monster=MONSTERS[monster_id]
            frame['monster']={key:monster[key] for key in ('id','name','description','length_m')}
            frame['monster'].update(rank=monster['rank'],kind='BOSS' if monster['boss'] else '精英' if monster.get('elite_material') else '普通')
    frame['appearance_snapshots']={cid:appearance_for(cid,state,frame) for cid in cast}
    return frame
