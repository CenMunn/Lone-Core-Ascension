import asyncio
import json
import httpx
import pytest
from duhe.providers import Settings, TextService, ProviderError


def settings():
    return Settings(text_key='secret-test', image_key='image-test')


def run(coro):
    return asyncio.run(coro)


def service(handler):
    return TextService(settings(), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_env_process_overrides_aliases(tmp_path, monkeypatch):
    path = tmp_path / 'config.env'
    path.write_text('DEEPSEEK_API_KEY=file-key\nDEEPSEEK_BASE_URL=https://api.deepseek.com\n', encoding='utf-8')
    monkeypatch.setenv('BL_DEEPSEEK_API_KEY', 'process-key')
    assert Settings.from_env(path).text_key == 'process-key'
    assert 'process-key' not in repr(Settings.from_env(path))


def test_api_base_aliases_override_file(tmp_path, monkeypatch):
    path=tmp_path/'alias.env'
    path.write_text('DEEPSEEK_BASE_URL=https://file.example\nDASHSCOPE_BASE_URL=https://file.example/api/v1\n',encoding='utf-8')
    monkeypatch.setenv('BL_DEEPSEEK_API_BASE','https://text.example/v1')
    monkeypatch.setenv('DASHSCOPE_API_BASE','https://image.example/api/v1')
    s=Settings.from_env(path)
    assert s.text_base_url=='https://text.example/v1'
    assert s.image_base_url=='https://image.example/api/v1'


def test_stream_content_only_and_usage():
    def handler(request):
        payload = json.loads(request.content)
        assert payload['stream'] is True
        frames = [
            {'choices':[{'delta':{'reasoning_content':'private', 'content':'你好'}, 'finish_reason':None}]},
            {'choices':[{'delta':{}, 'finish_reason':'stop'}]},
            {'choices':[], 'usage':{'total_tokens':12}},
        ]
        return httpx.Response(200, text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n', headers={'content-type':'text/event-stream'})
    async def check():
        s = service(handler)
        try:
            events = [event async for event in s.stream([{'role':'user','content':'测试'}])]
            assert events == [{'type':'delta','text':'你好'}, {'type':'done','finish_reason':'stop','usage':{'total_tokens':12}}]
        finally:
            await s.close()
    run(check())


@pytest.mark.parametrize('content,finish', [('', 'stop'), ('{"x":', 'stop'), ('{"x":1}', 'length'), ('[]', 'stop')])
def test_structured_rejects_empty_truncated_or_nonobject(content, finish):
    s = service(lambda r: httpx.Response(200,json={'choices':[{'message':{'content':content},'finish_reason':finish}]}))
    async def check():
        try:
            with pytest.raises(ProviderError):
                await s.structured([{'role':'user','content':'JSON'}])
        finally:
            await s.close()
    run(check())


def test_auth_error_redacted_and_never_retried():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={'error':{'message':'secret-test', 'type':'invalid_api_key'}})
    async def check():
        s = service(handler)
        try:
            with pytest.raises(ProviderError) as exc:
                await s.structured([{'role':'user','content':'JSON'}])
            assert 'secret-test' not in str(exc.value)
            assert len(calls) == 1
        finally:
            await s.close()
    run(check())


def test_closing_generator_closes_underlying_http_stream():
    class Body(httpx.AsyncByteStream):
        closed=False
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"first"},"finish_reason":null}]}\n\n'
            yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        async def aclose(self):
            self.closed=True
    body=Body()
    async def check():
        s=service(lambda r:httpx.Response(200,stream=body,headers={'content-type':'text/event-stream'}))
        try:
            stream=s.stream([{'role':'user','content':'hi'}])
            assert (await anext(stream))['text']=='first'
            await stream.aclose()
            assert body.closed
        finally:
            await s.close()
    run(check())


def test_examples_import_without_network(monkeypatch):
    import importlib
    def fail(*args,**kwargs):
        raise AssertionError('network on import')
    monkeypatch.setattr(httpx.Client,'send',fail)
    monkeypatch.setattr(httpx.AsyncClient,'send',fail)
    for name in ['examples.common','examples.http_demo','examples.sdk_demo','examples.make_postman']:
        importlib.import_module(name)


def test_postman_has_same_prompts_and_empty_keys():
    from examples.make_postman import build
    from examples.common import PROMPTS
    result=build()
    assert json.loads(result['item'][0]['request']['body']['raw'])['messages'][0]['content']==PROMPTS['text']
    image=json.loads(result['item'][1]['request']['body']['raw'])
    assert image['input']['prompt']==PROMPTS['image']
    assert image['parameters']['n']==1
    assert all(not v['value'] for v in result['variable'] if v['key'].endswith('_key'))


@pytest.mark.parametrize('model',['deepseek-flash','deepseek-v4-pro'])
@pytest.mark.parametrize('streaming',[True,False])
def test_official_new_models_explicitly_disable_thinking(model,streaming):
    def handler(request):
        body=json.loads(request.content)
        assert body['thinking']=={'type':'disabled'}
        if streaming:
            frames=[{'choices':[{'delta':{'content':'正文'},'finish_reason':None}]}, {'choices':[{'delta':{},'finish_reason':'stop'}]}]
            return httpx.Response(200,text=''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n',headers={'content-type':'text/event-stream'})
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}]})
    async def check():
        s=TextService(Settings(text_key='test',text_model=model,text_base_url='https://api.deepseek.com/v1'),http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            if streaming:
                assert [e async for e in s.stream([{'role':'user','content':'test'}])][-1]['type']=='done'
            else:
                assert await s.structured([{'role':'user','content':'json'}])=={'ok':True}
        finally:
            await s.close()
    run(check())


@pytest.mark.parametrize('base,model',[
    ('https://dashscope.aliyuncs.com/compatible-mode/v1','deepseek-flash'),
    ('https://api.deepseek.com.proxy.example/v1','deepseek-v4-pro'),
    ('https://api.deepseek.com','deepseek-chat'),
])
@pytest.mark.parametrize('streaming',[True,False])
def test_other_endpoints_or_models_do_not_receive_thinking(base,model,streaming):
    def handler(request):
        assert 'thinking' not in json.loads(request.content)
        if streaming:
            return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',headers={'content-type':'text/event-stream'})
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}]})
    async def check():
        s=TextService(Settings(text_key='test',text_model=model,text_base_url=base),http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            if streaming:
                _=[e async for e in s.stream([{'role':'user','content':'test'}])]
            else:
                await s.structured([{'role':'user','content':'json'}])
        finally:
            await s.close()
    run(check())


@pytest.mark.parametrize('streaming',[True,False])
def test_incomplete_generation_exposes_safe_diagnostics(streaming):
    usage={'completion_tokens':1800,'total_tokens':2000,'completion_tokens_details':{'reasoning_tokens':1800,'private':'secret-test'},'private':'secret-test'}
    def handler(request):
        if streaming:
            frame={'choices':[{'delta':{'reasoning_content':'PRIVATE REASONING'},'finish_reason':'length'}],'usage':usage}
            return httpx.Response(200,text='data: '+json.dumps(frame)+'\n\ndata: [DONE]\n\n',headers={'content-type':'text/event-stream'})
        return httpx.Response(200,json={'choices':[{'message':{'content':'','reasoning_content':'PRIVATE REASONING'},'finish_reason':'length'}],'usage':usage})
    async def check():
        s=service(handler)
        try:
            with pytest.raises(ProviderError) as exc:
                if streaming:
                    _=[e async for e in s.stream([{'role':'user','content':'hi'}])]
                else:
                    await s.structured([{'role':'user','content':'json'}])
            assert exc.value.metadata=={'finish_reason':'length','usage':{'completion_tokens':1800,'total_tokens':2000,'completion_tokens_details':{'reasoning_tokens':1800}}}
            assert 'secret-test' not in repr(exc.value.metadata)
            assert 'PRIVATE REASONING' not in repr(exc.value.metadata)
        finally:
            await s.close()
    run(check())
