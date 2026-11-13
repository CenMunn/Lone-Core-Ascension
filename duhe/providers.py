"""Explicit configuration and OpenAI-compatible text transport; no import-time I/O."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from openai import AsyncOpenAI, APIError


class ProviderError(RuntimeError):
    """Safe user-facing error; task_id permits resuming an image job."""
    def __init__(self, message, *, task_id=None, metadata=None):
        super().__init__(message)
        self.task_id = task_id
        self.metadata = metadata or {}


def require_https(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderError('服务地址必须是无嵌入凭据的 HTTPS 地址')
    return url.rstrip('/')


@dataclass
class Settings:
    text_base_url: str = 'https://api.deepseek.com'
    text_key: str = field(default='', repr=False)
    text_model: str = 'deepseek-chat'
    image_base_url: str = 'https://dashscope.aliyuncs.com/api/v1'
    image_key: str = field(default='', repr=False)
    image_model: str = 'wanx2.1-t2i-turbo'
    image_size: str = ''
    timeout: float = 60.0

    def __post_init__(self):
        require_https(self.text_base_url)
        require_https(self.image_base_url)
        if self.timeout <= 0:
            raise ValueError('timeout 必须大于零')
        if not self.image_size:
            self.image_size = '1280*1280' if self.image_model.startswith('wan2.5-') else '1024*1024'

    @classmethod
    def from_env(cls, env_path: Path):
        # Read only the caller-supplied file, never auto-discover a parent .env.
        file_values = dotenv_values(env_path, interpolate=False) if Path(env_path).is_file() else {}
        def get(*names, default=''):
            for source in (os.environ, file_values):
                for name in names:
                    if source.get(name):
                        return source[name].strip()
            return default
        return cls(
            text_key=get('DEEPSEEK_API_KEY', 'BL_DEEPSEEK_API_KEY'),
            text_base_url=get('DEEPSEEK_BASE_URL','DEEPSEEK_API_BASE','DEEPSEEK_BASE','BL_DEEPSEEK_BASE_URL','BL_DEEPSEEK_API_BASE','BL_DEEPSEEK_BASE',default='https://api.deepseek.com'),
            text_model=get('DEEPSEEK_MODEL','BL_DEEPSEEK_MODEL',default='deepseek-chat'),
            image_key=get('DASHSCOPE_API_KEY'),
            image_base_url=get('DASHSCOPE_BASE_URL','DASHSCOPE_API_BASE','DASHSCOPE_BASE',default='https://dashscope.aliyuncs.com/api/v1'),
            image_model=get('DASHSCOPE_MODEL','DASHSCOPE_IMAGE_MODEL',default='wanx2.1-t2i-turbo'),
            image_size=get('DASHSCOPE_IMAGE_SIZE','DASHSCOPE_SIZE'),
            timeout=float(get('API_TIMEOUT',default='60')),
        )


class TextService:
    def __init__(self, settings: Settings, *, http_client=None):
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.text_key or 'unconfigured', base_url=settings.text_base_url,
                                  timeout=settings.timeout, max_retries=0, http_client=http_client)

    def _check(self):
        if not self.settings.text_key:
            raise ProviderError('请配置文本服务 API Key')

    def _thinking_options(self):
        # Official DeepSeek v4 defaults to thinking=enabled/high. Keep the
        # short interactive budget for visible prose, without sending this
        # provider-specific field to Bailian or other compatible gateways.
        if (urlsplit(self.settings.text_base_url).hostname == 'api.deepseek.com'
                and self.settings.text_model in ('deepseek-flash','deepseek-v4-pro')):
            return {'extra_body':{'thinking':{'type':'disabled'}}}
        return {}

    @staticmethod
    def _diagnostics(finish, usage):
        allowed_finish = {'stop','length','content_filter','tool_calls','insufficient_system_resource','aborted'}
        safe_finish = finish if finish in allowed_finish or finish is None else 'unknown'
        if not isinstance(usage,dict):
            usage = {}
        counters = {'prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'}
        safe_usage = {key:value for key,value in usage.items() if key in counters and type(value) is int and value>=0}
        for name in ('completion_tokens_details','prompt_tokens_details'):
            details = usage.get(name)
            if isinstance(details,dict):
                allowed = {'reasoning_tokens','cached_tokens','audio_tokens','image_tokens','accepted_prediction_tokens','rejected_prediction_tokens'}
                filtered = {key:value for key,value in details.items() if key in allowed and type(value) is int and value>=0}
                if filtered:
                    safe_usage[name] = filtered
        return {'finish_reason':safe_finish,'usage':safe_usage}

    @staticmethod
    def _error(exc, metadata=None):
        code = getattr(exc, 'status_code', None)
        if code in (401,403):
            return ProviderError(f'文本服务鉴权失败（HTTP {code}），请检查 Key、地域与权限',metadata=metadata)
        return ProviderError(f'文本服务请求失败（HTTP {code or "网络/协议异常"}）',metadata=metadata)

    async def stream(self, messages):
        self._check()
        stream = None
        finish = None
        usage = {}
        try:
            stream = await self.client.chat.completions.create(model=self.settings.text_model,messages=messages,
                          stream=True, max_tokens=1800, stream_options={'include_usage':True}, **self._thinking_options())
            has_content = False
            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage.model_dump(exclude_none=True)
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta.content:
                    has_content = True
                    yield {'type':'delta','text':choice.delta.content}
                if choice.finish_reason:
                    finish = choice.finish_reason
            if not has_content or finish is None:
                raise ProviderError('文本流为空或连接提前中断，请重新生成',metadata=self._diagnostics(finish,usage))
            if finish != 'stop':
                diagnostics=self._diagnostics(finish,usage)
                raise ProviderError(f'文本生成未正常完成（{diagnostics["finish_reason"]}），请重新生成',metadata=diagnostics)
            yield {'type':'done','finish_reason':finish,'usage':usage}
        except (APIError, httpx.HTTPError, ValueError) as exc:
            raise self._error(exc,self._diagnostics(finish,usage)) from None
        finally:
            if stream is not None:
                await stream.close()

    async def structured(self, messages):
        self._check()
        diagnostics=self._diagnostics(None,{})
        try:
            response = await self.client.chat.completions.create(model=self.settings.text_model,messages=messages,
                         response_format={'type':'json_object'}, stream=False,max_tokens=1200,**self._thinking_options())
            usage=response.usage.model_dump(exclude_none=True) if response.usage else {}
            if not response.choices:
                raise ProviderError('结构化响应没有候选结果',metadata=self._diagnostics(None,usage))
            choice = response.choices[0]
            diagnostics=self._diagnostics(choice.finish_reason,usage)
            if choice.finish_reason != 'stop':
                raise ProviderError('JSON 生成被截断或拒绝，未写入游戏状态',metadata=diagnostics)
            content = choice.message.content
            if not content or not content.strip():
                raise ProviderError('JSON 响应为空',metadata=diagnostics)
            def reject_constant(value):
                raise ValueError('nonfinite JSON')
            result = json.loads(content, parse_constant=reject_constant)
            if not isinstance(result, dict):
                raise ProviderError('JSON 顶层必须是对象',metadata=diagnostics)
            return result
        except (APIError, httpx.HTTPError) as exc:
            raise self._error(exc,diagnostics) from None
        except (ValueError, TypeError, AttributeError):
            raise ProviderError('JSON 响应格式无效或不完整',metadata=diagnostics) from None

    async def close(self):
        await self.client.close()
