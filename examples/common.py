"""One prompt source for HTTP, SDK, curl and Postman lessons."""
import json
import os
from pathlib import Path

PROMPTS=json.loads(Path(__file__).with_name('lesson_prompt.json').read_text(encoding='utf-8'))


def image_body():
    model=os.environ.get('DASHSCOPE_MODEL','wanx2.1-t2i-turbo')
    return {'model':model,'input':{'prompt':PROMPTS['image'],'negative_prompt':PROMPTS['negative']},
            'parameters':{'size':'1280*1280' if model.startswith('wan2.5-') else '1024*1024','n':1,'seed':42,'prompt_extend':False}}


def text_body():
    return {'model':os.environ.get('DEEPSEEK_MODEL','deepseek-chat'),
            'messages':[{'role':'user','content':PROMPTS['text']}],'stream':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('kind',choices=['text','image'])
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    body=json.dumps(text_body() if a.kind=='text' else image_body(),ensure_ascii=False,indent=2)
    if a.output:
        a.output.write_text(body,encoding='utf-8')
    else:
        print(body)
