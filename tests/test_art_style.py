import asyncio
from types import SimpleNamespace
from duhe.art_style import STYLE_DETAIL,STYLE_COMPACT,STYLE_ID
from duhe.prompts import image_prompt
from duhe.rules import new_game,scene_for
from duhe.profiles import portrait_path
from duhe.portraits import generate_reference
from duhe.budget import Budget

def test_nonhuman_style_does_not_inject_human_face_instructions():
    from duhe.art_style import unify
    prompt=unify('球形核心，黑曜圆环',nonhuman=True)
    assert '赛璐璐' in prompt and '五官' not in prompt and '眼神' not in prompt

def test_old_save_style_cannot_override_unified_style():
    state=new_game({'art_style':'写实照片，国风厚涂'})
    scene=scene_for(state)
    data={'character_ids':['protagonist'],'description':'废墟里观察道路'}
    for limit,style in ((500,STYLE_COMPACT),(1900,STYLE_DETAIL)):
        prompt,negative=image_prompt(data,state,scene,limit=limit)
        assert prompt.startswith(style) and len(prompt)<=limit
        assert '写实照片' not in prompt and '写实照片' in negative

def test_reference_uses_shared_style_and_keeps_old_asset(tmp_path):
    class Images:
        prompt=None
        async def generate(self,prompt,negative,target,**kwargs):
            self.prompt=prompt
            target.write_bytes(b'test-only')
            yield {'status':'SUCCEEDED','path':str(target),'task_id':'test'}
    async def run():
        folder=tmp_path/'output/characters';folder.mkdir(parents=True)
        old=folder/'heroine-v2.png';old.write_bytes(b'old')
        images=Images()
        e=SimpleNamespace(root=tmp_path,settings=SimpleNamespace(image_model='test'),images=images,budget=Budget(tmp_path/'usage.sqlite'))
        path=await generate_reference(e,'heroine')
        assert images.prompt.startswith(STYLE_DETAIL)
        assert '动画电影' not in images.prompt and '白色长直发' in images.prompt
        assert old.read_bytes()==b'old'
        assert portrait_path(tmp_path,'heroine')==path and STYLE_ID in path
    asyncio.run(run())
