"""OpenAI 2.x / DashScope 2.x lesson. Importing performs no requests."""
import argparse
import os
import time
from openai import OpenAI
import dashscope
from duhe.providers import require_https, ProviderError
from .common import text_body, image_body


def main(kind,task_id=None):
    if kind=='text':
        with OpenAI(api_key=os.environ['DEEPSEEK_API_KEY'],
                    base_url=require_https(os.environ.get('DEEPSEEK_BASE_URL','https://api.deepseek.com')),
                    timeout=60,max_retries=0) as client:
            response=client.chat.completions.create(**text_body())
            print(response.choices[0].message.content)
        return
    body=image_body()
    client=dashscope.Client(api_key=os.environ['DASHSCOPE_API_KEY'],
             base_url=require_https(os.environ.get('DASHSCOPE_BASE_URL','https://dashscope.aliyuncs.com/api/v1')),
             timeout=60,max_retries=0)
    try:
        if not task_id:
            job=client.images.jobs.create(model=body['model'],prompt=body['input']['prompt'],
                negative_prompt=body['input']['negative_prompt'],**body['parameters'])
            task_id=job.task_id
            print('已提交任务，请保存 task_id:',task_id,flush=True)
        # Explicit bounded polling; the same task ID resumes without another POST.
        deadline=time.monotonic()+300
        while time.monotonic()<deadline:
            job=client.images.jobs.fetch(task_id)
            print('task_id:',task_id,'status:',job.status,flush=True)
            if job.succeeded:
                print('成功；图片链接24小时有效。请通过 ImageService.generate(task_id=...) 校验并下载图片。')
                return
            if job.status in ('FAILED','CANCELED','UNKNOWN'):
                return
            time.sleep(3)
        print('轮询超时，保留task_id并通过 --task-id 恢复。')
    finally:
        client.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('kind',choices=['text','image'])
    p.add_argument('--task-id')
    args=p.parse_args()
    try:
        main(args.kind,args.task_id)
    except Exception:
        # SDK exceptions may embed server messages/URLs; never echo a raw exception.
        raise SystemExit('SDK请求未完成；如已显示task_id请保留并恢复，提交状态不明时先查询控制台，勿盲目重发。') from None
