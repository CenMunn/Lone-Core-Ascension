"""Optional Wan 2.5 image-edit adapter for controlled reference experiments."""
import asyncio
import base64
from dataclasses import replace
from pathlib import Path
import re
import time
from PIL import Image, UnidentifiedImageError
from .image_jobs import ImageService
from .providers import ProviderError


def encode_reference(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('参考图不存在或超过10MB')
    try:
        with Image.open(path) as image:
            if image.format not in ('PNG', 'JPEG', 'BMP', 'WEBP'):
                raise ValueError('参考图格式不支持')
            if not 384 <= image.width <= 5000 or not 384 <= image.height <= 5000:
                raise ValueError('参考图尺寸不在384至5000像素范围')
            if 'A' in image.getbands() or 'transparency' in image.info:
                raise ValueError('参考图不能含透明通道')
            mime = {'PNG':'image/png', 'JPEG':'image/jpeg', 'BMP':'image/bmp', 'WEBP':'image/webp'}[image.format]
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise ValueError('参考图无法读取') from None
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode('ascii')


class ReferenceImageService(ImageService):
    def __init__(self, settings, **kwargs):
        super().__init__(replace(settings, image_model='wan2.5-i2i-preview'), **kwargs)

    async def generate_reference(self, prompt, negative, references, output_path, *, task_id=None):
        if not self.settings.image_key:
            raise ProviderError('请配置图片服务 API Key', task_id=task_id)
        if task_id is None:
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>2000 or len(negative)>500:
                raise ValueError('参考图编辑提示词无效')
            if not isinstance(references,list) or not 1 <= len(references) <= 3:
                raise ValueError('需要1至3张参考图')
            images = [encode_reference(path) for path in references]
            data = await self._request('POST','/services/aigc/image2image/image-synthesis',json={
                'model':'wan2.5-i2i-preview', 'input':{'prompt':prompt,'negative_prompt':negative,'images':images},
                'parameters':{'n':1,'size':'1280*1280','prompt_extend':False}})
            output=data.get('output',{});task_id=output.get('task_id')
            if not task_id:raise ProviderError('提交响应没有任务ID，任务状态未知')
            yield {'status':output.get('task_status','PENDING'),'task_id':task_id}
        else:
            yield {'status':'RESUMING','task_id':task_id}
        if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',task_id):
            raise ProviderError('任务ID格式无效')
        started=time.monotonic()
        while True:
            if time.monotonic()-started >= self.poll_timeout:
                yield {'status':'TIMEOUT','task_id':task_id};return
            data=await self._request('GET','/tasks/'+task_id,task_id=task_id)
            output=data.get('output',{});status=output.get('task_status','UNKNOWN')
            if status=='SUCCEEDED':
                url=next((x.get('url') for x in output.get('results',[]) if x.get('url')),None)
                if not url:raise ProviderError('成功任务没有图片链接',task_id=task_id)
                size=await self._download(url,output_path,task_id)
                yield {'status':status,'task_id':task_id,'path':str(output_path),'size':f'{size[0]}*{size[1]}'};return
            if status in ('FAILED','CANCELED','UNKNOWN'):
                yield {'status':status,'task_id':task_id};return
            if status not in ('PENDING','RUNNING'):
                yield {'status':'UNKNOWN','task_id':task_id};return
            yield {'status':status,'task_id':task_id}
            await asyncio.sleep(self.poll_interval)
