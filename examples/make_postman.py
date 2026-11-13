"""Rebuild the importable Postman lesson from common.py; no requests."""
import json
from pathlib import Path
from .common import PROMPTS


def build():
    def request(name,method,url,key,body=None,async_header=False,events=None):
        headers=[{'key':'Authorization','value':'Bearer {{'+key+'}}'}]
        if body:
            headers.append({'key':'Content-Type','value':'application/json'})
        if async_header:
            headers.append({'key':'X-DashScope-Async','value':'enable'})
        item={'name':name,'request':{'method':method,'header':headers,'url':url}}
        if body:
            item['request']['body']={'mode':'raw','raw':json.dumps(body,ensure_ascii=False,indent=2),'options':{'raw':{'language':'json'}}}
        if events:
            item['event']=[{'listen':'test','script':{'type':'text/javascript','exec':events}}]
        return item
    text={'model':'{{text_model}}','messages':[{'role':'user','content':PROMPTS['text']}],'stream':False}
    image={'model':'{{image_model}}','input':{'prompt':PROMPTS['image'],'negative_prompt':PROMPTS['negative']},'parameters':{'size':'{{image_size}}','n':1,'seed':42,'prompt_extend':False}}
    variables={'text_base':'https://api.deepseek.com','text_model':'deepseek-chat','text_key':'',
               'image_base':'https://dashscope.aliyuncs.com/api/v1','image_model':'wanx2.1-t2i-turbo','image_size':'1024*1024','image_key':'','task_id':''}
    return {'info':{'name':'渡河 · 同提示词API教学（手动执行会计费）','schema':'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
                   'description':'密钥请放本地secret环境变量。2.5需同时改image_model和image_size=1280*1280。创建只执行一次；断线先查控制台。不要批量反复Run集合。'},
            'variable':[{'key':k,'value':v} for k,v in variables.items()],
            'item':[request('1 文本HTTP','POST','{{text_base}}/chat/completions','text_key',text),
                    request('2 图片异步提交（仅一次）','POST','{{image_base}}/services/aigc/text2image/image-synthesis','image_key',image,True,
                            ['const body=pm.response.json();','if(body.output && body.output.task_id) pm.collectionVariables.set("task_id",body.output.task_id);']),
                    request('3 图片任务查询（可重复，间隔至少3秒）','GET','{{image_base}}/tasks/{{task_id}}','image_key')]}


if __name__=='__main__':
    Path(__file__).with_name('postman_collection.json').write_text(json.dumps(build(),ensure_ascii=False,indent=2),encoding='utf-8')
