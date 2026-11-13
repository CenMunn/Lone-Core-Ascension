"""Reusable Wan image pipeline for the application's character references."""
import json
from pathlib import Path
from .profiles import CARDS
from .world import CHARACTERS
from .art_style import unify,STYLE_NEGATIVE,STYLE_ID

async def generate_reference(engine,character_id,version='-anime-v1'):
    folder=engine.root/'output/characters';folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{character_id}{version}.png';record=folder/f'{character_id}{version}.json'
    if target.is_file():return str(target)
    data=json.loads(record.read_text('utf-8')) if record.is_file() else {}
    card=CHARACTERS[character_id]
    prompt=('统一系列人物设定参考图，精细末世动画电影概念插画，单个主体，简洁灰色废墟背景，完整展示发型和服饰，中景至膝上，清楚的自然面貌，不画文字。'
            +CARDS[character_id]['portrait']+'。'+card['appearance']+'。'+card['outfit'])
    if character_id=='heroine':prompt='成年女性沈霁月人物参考，单人。白色长直发全部自然散开至腰际，头发像瀑布一样均匀披在双肩和背后，没有任何编织缠绕，没有束发，没有头绳。轻薄碎刘海，紫瞳，右眼下一颗浅痣。灰白防护外套深紫高领内衬石墨行动长裤，左腰样本匣。温柔沉稳，末世动画电影插画，灰色废墟背景，中景，完整展示长直发，无文字。'
    if character_id=='mentor':prompt='52岁男性锻造师顾砺山，铁灰短寸发，深褐眼，严肃的成熟面孔与稀疏灰胡茬，左前臂为钢制作业义肢，右手为普通人类手臂，皮肤只有愈合的浅褐旧疤。黑色卷袖衬衣，深棕皮围裙，作业靴。安静站在灰色废墟，冷色自然光，无任何火焰，无发光皮肤，无魔法，末世动画电影角色参考插画。'
    if character_id=='boss':prompt='单个巨大的悬浮核心巢穴，正中心是一颗圆球形惨白发光能量核心，外围有三重破碎黑曜石同心圆环，圆环甲壳分节，表面紫黑能量裂隙，不对称金属管线与几何碎核向四周扩散，类似一颗结构复杂的异星机械行星，没有任何人或人形站在中央，纯粹球形环状聚合生物构造，黑色背景，末世动画电影概念插画，无文字。'
    prompt=unify(prompt,nonhuman=character_id=='boss')
    if character_id=='mentor':prompt+='。人物自己的左前臂是机械义肢，位于画面右侧；画面左侧是普通右手臂，肤色自然。'
    task=data.get('task_id') if data.get('status') not in ('FAILED','CANCELED') else None
    if not task:engine.budget.charge('image','人物参考图:'+character_id)
    negative='文字，水印，发色瞳色错乱，马尾，扎发，辫子，编发，发绳，火焰，燃烧，色情'
    if character_id=='boss':negative+='，人形，人类，人物，脸，头，躯干，手，脚，双足怪物'
    negative+='，'+STYLE_NEGATIVE
    async for event in engine.images.generate(prompt,negative,target,task_id=task,prompt_extend=False):
        data.update(event);data.update(prompt=prompt,character_id=character_id,model=engine.settings.image_model,style_id=STYLE_ID)
        record.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(target)
