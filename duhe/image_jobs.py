"""Wan 2.1/2.5 asynchronous HTTP protocol. Never resubmit an ambiguous POST."""
import asyncio
import io
import ipaddress
from pathlib import Path
import re
import time
import warnings

import httpx
from PIL import Image, UnidentifiedImageError
from .providers import Settings, ProviderError, require_https


class ImageService:
    MODELS = {'wanx2.1-t2i-turbo','wanx2.1-t2i-plus','wan2.5-t2i-preview'}

    def __init__(self, settings: Settings, *, http_client=None, poll_interval=3.0, poll_timeout=300.0, max_download_bytes=20*1024*1024):
        self.settings = settings
        self.client = http_client or httpx.AsyncClient(timeout=settings.timeout, follow_redirects=False)
        # CDN fallback must bypass a system proxy that resolves/rewrites fake IPs.
        # Keep API transport unchanged and preserve injected clients for protocol tests.
        self.download_client = http_client or httpx.AsyncClient(timeout=settings.timeout,follow_redirects=False,trust_env=False)
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.max_download_bytes = max_download_bytes
        base = require_https(settings.image_base_url)
        # Also accept the gateway root, but never compatible-mode/v1.
        if base.endswith('/compatible-mode/v1'):
            raise ProviderError('图片地址需要 DashScope 原生 /api/v1 地址')
        self.base = base if base.endswith('/api/v1') else base+'/api/v1'

    async def _request(self, method, path, *, task_id=None, **kwargs):
        headers = {'Authorization':f'Bearer {self.settings.image_key}'}
        if method == 'POST':
            headers['X-DashScope-Async']='enable'
        try:
            response = await self.client.request(method,self.base+path,headers=headers,timeout=self.settings.timeout,**kwargs)
            if response.status_code >= 400:
                label = '鉴权失败' if response.status_code in (401,403) else '请求失败'
                raise ProviderError(f'图片服务{label}（HTTP {response.status_code}）',task_id=task_id)
            data = response.json()
            if not isinstance(data,dict) or data.get('code'):
                raise ProviderError('图片服务返回错误，请检查模型权限与参数',task_id=task_id)
            return data
        except httpx.HTTPError:
            if method == 'POST':
                raise ProviderError('提交后连接中断，任务状态未知；请先在控制台查任务ID，勿直接重复提交') from None
            raise ProviderError('图片查询网络异常；保留任务ID后可恢复查询',task_id=task_id) from None
        except ValueError:
            raise ProviderError('图片服务响应格式无效',task_id=task_id) from None

    def _parameters(self,size,seed,prompt_extend):
        if self.settings.image_model not in self.MODELS:
            raise ProviderError('本实现仅支持万相2.1/2.5文生图模型，不能混用2.6协议')
        actual_size = size or self.settings.image_size
        if not re.fullmatch(r'[0-9]+\*[0-9]+',actual_size):
            raise ProviderError('图片尺寸应为宽*高')
        w,h=map(int,actual_size.split('*'))
        if self.settings.image_model.startswith('wan2.5-'):
            valid = 1280**2 <= w*h <= 1440**2 and .25 <= w/h <= 4 if h else False
        else:
            valid = 512<=w<=1440 and 512<=h<=1440
        if not valid:
            raise ProviderError('图片尺寸超出当前模型范围')
        if seed is not None and (type(seed) is not int or not 0<=seed<=2147483647):
            raise ProviderError('seed 必须为0至2147483647的整数')
        if not isinstance(prompt_extend,bool):
            raise ProviderError('prompt_extend 必须是布尔值')
        result={'n':1,'size':actual_size,'prompt_extend':prompt_extend}
        if seed is not None:
            result['seed']=seed
        return result

    async def _download(self,url,path,task_id):
        try:
            async with asyncio.timeout(min(15,self.settings.timeout)):
                return await self._download_once(url,path,task_id)
        except (httpx.TransportError,TimeoutError):
            original=httpx.URL(url)
            if not original.host.endswith('.oss-accelerate.aliyuncs.com'):
                raise ProviderError('图片下载连接失败；请检查网络后恢复配图，无需重新生成',task_id=task_id) from None
            try:
                # Resolve only the public OSS hostname, never send signed URLs to DNS.
                response=await self.download_client.get('https://dns.alidns.com/resolve',
                    params={'name':original.host,'type':'A'},timeout=15)
                response.raise_for_status()
                addresses=[x['data'] for x in response.json().get('Answer',[])
                           if x.get('type')==1 and ipaddress.ip_address(x['data']).is_global]
                if not addresses:raise ValueError('No public address')
                # Preserve HTTP Host and TLS server name, including certificate verification.
                return await self._download_once(original.copy_with(host=addresses[0]),path,task_id,
                    headers={'Host':original.host},extensions={'sni_hostname':original.host})
            except (httpx.HTTPError,ValueError,KeyError):
                raise ProviderError('图片已生成，但下载连接失败；请检查代理或网络后恢复配图，无需重新生成',task_id=task_id) from None

    async def _download_once(self,url,path,task_id,**connection):
        require_https(str(url))
        try:
            # Signed query strings stay on the wire; never log URLs or exceptions.
            async with self.download_client.stream('GET',url,timeout=self.settings.timeout,follow_redirects=False,**connection) as response:
                if response.status_code != 200:
                    raise ProviderError(f'图片下载失败（HTTP {response.status_code}）',task_id=task_id)
                content_length=response.headers.get('content-length','')
                if content_length.isdigit() and int(content_length)>self.max_download_bytes:
                    raise ProviderError('图片下载超过大小限制',task_id=task_id)
                body=bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body)>self.max_download_bytes:
                        raise ProviderError('图片下载超过大小限制',task_id=task_id)
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(body)) as picture:
                    picture.verify()
                with Image.open(io.BytesIO(body)) as picture:
                    picture.load()
                    image_format=picture.format
                    dimensions=picture.size
            if image_format not in ('PNG','JPEG','WEBP'):
                raise ProviderError('返回结果不是支持的图片格式',task_id=task_id)
            path=Path(path)
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_name(path.name+'.part')
            try:
                temporary.write_bytes(body)
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
            return dimensions
        except httpx.TransportError:
            raise
        except (httpx.HTTPError,UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise ProviderError('图片下载或真实图像校验失败，可用任务ID重试下载',task_id=task_id) from None

    async def generate(self,prompt,negative_prompt,output_path,size=None,seed=None,prompt_extend=True,task_id=None):
        if not self.settings.image_key:
            raise ProviderError('请配置图片服务 API Key',task_id=task_id)
        if task_id is None:
            parameters=self._parameters(size,seed,prompt_extend)
            limit=2000 if self.settings.image_model.startswith('wan2.5-') else 500
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>limit or len(negative_prompt)>500:
                raise ProviderError('提示词为空或超过模型长度限制')
            data=await self._request('POST','/services/aigc/text2image/image-synthesis',json={
                'model':self.settings.image_model,'input':{'prompt':prompt,'negative_prompt':negative_prompt},'parameters':parameters})
            output=data.get('output',{})
            task_id=output.get('task_id')
            if not task_id:
                raise ProviderError('提交响应没有任务ID，任务状态未知；请在控制台核实后再操作')
            yield {'status':output.get('task_status','PENDING'),'task_id':task_id}
        else:
            yield {'status':'RESUMING','task_id':task_id}
        if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',task_id):
            raise ProviderError('任务ID格式无效')
        started=time.monotonic()
        while True:
            if time.monotonic()-started >= self.poll_timeout:
                yield {'status':'TIMEOUT','task_id':task_id,'message':'轮询超时，可用同一任务ID继续查询'}
                return
            data=await self._request('GET','/tasks/'+task_id,task_id=task_id)
            output=data.get('output',{})
            status=output.get('task_status','UNKNOWN')
            if status == 'SUCCEEDED':
                results=output.get('results') or []
                url=next((r.get('url') for r in results if r.get('url')),None)
                if not url:
                    raise ProviderError('成功任务没有图片链接',task_id=task_id)
                dimensions=await self._download(url,output_path,task_id)
                yield {'status':status,'task_id':task_id,'path':str(output_path),'model':self.settings.image_model,'size':f'{dimensions[0]}*{dimensions[1]}'}
                return
            if status in ('FAILED','CANCELED','UNKNOWN'):
                yield {'status':status,'task_id':task_id,'message':'任务未生成图片，请在控制台核查'}
                return
            if status not in ('PENDING','RUNNING'):
                yield {'status':'UNKNOWN','task_id':task_id,'message':'服务返回未识别任务状态'}
                return
            yield {'status':status,'task_id':task_id}
            await asyncio.sleep(self.poll_interval)

    async def close(self):
        await self.client.aclose()
        if self.download_client is not self.client:
            await self.download_client.aclose()
