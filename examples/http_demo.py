"""Explicit-run HTTP lesson: python -m examples.http_demo text|image [--task-id ID]."""
import argparse
import asyncio
import os
from pathlib import Path
import httpx
from duhe.providers import Settings, ProviderError, require_https
from duhe.image_jobs import ImageService
from .common import PROMPTS, text_body


async def main(kind,task_id=None):
    if kind=='text':
        key=os.environ['DEEPSEEK_API_KEY']
        base=require_https(os.environ.get('DEEPSEEK_BASE_URL','https://api.deepseek.com'))
        async with httpx.AsyncClient(timeout=60) as client:
            response=await client.post(base+'/chat/completions',headers={'Authorization':'Bearer '+key},json=text_body())
            if response.status_code!=200:
                raise ProviderError(f'HTTP {response.status_code}（详细响应不输出，避免泄密）')
            print(response.json()['choices'][0]['message']['content'])
    else:
        # Read process environment only: the supplied nonexistent path prevents .env discovery.
        settings=Settings.from_env(Path(__file__).with_name('not-used.env'))
        service=ImageService(settings)
        try:
            async for event in service.generate(PROMPTS['image'],PROMPTS['negative'],Path('outputs/http-scene.png'),seed=42,prompt_extend=False,task_id=task_id):
                print(event)  # contains task ID and local output path, never a signed URL
        finally:
            await service.close()


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('kind',choices=['text','image'])
    p.add_argument('--task-id')
    args=p.parse_args()
    asyncio.run(main(args.kind,args.task_id))
