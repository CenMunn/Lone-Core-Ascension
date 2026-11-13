import asyncio
import io
import json
import httpx
import pytest
from PIL import Image
from duhe.providers import Settings, ProviderError
from duhe.image_jobs import ImageService


def test_oss_download_recovers_dns_without_resubmitting(tmp_path):
    image=io.BytesIO();Image.new('RGB',(3,3),'blue').save(image,format='PNG')
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.method=='GET'
        if request.url.host=='images.oss-accelerate.aliyuncs.com':
            raise httpx.ConnectError('DNS route unavailable')
        if request.url.host=='dns.alidns.com':
            assert 'signature' not in str(request.url)
            return httpx.Response(200,json={'Answer':[{'type':1,'data':'8.131.131.236'}]})
        if request.url.host=='8.131.131.236':
            assert request.headers['Host']=='images.oss-accelerate.aliyuncs.com'
            assert request.extensions['sni_hostname']=='images.oss-accelerate.aliyuncs.com'
            assert request.url.query==b'signature=secret'
            return httpx.Response(200,content=image.getvalue())
        return httpx.Response(200,json={'output':{'task_status':'SUCCEEDED','results':[{'url':'https://images.oss-accelerate.aliyuncs.com/x?signature=secret'}]}})
    async def check():
        service=ImageService(Settings(image_key='test'),http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            events=[e async for e in service.generate('','',tmp_path/'recovered.png',task_id='existing')]
            assert events[-1]['status']=='SUCCEEDED'
            assert len(calls)==4
        finally:await service.close()
    asyncio.run(check())


def test_create_poll_download_and_protocol(tmp_path):
    image = io.BytesIO()
    Image.new('RGB',(3,3),'blue').save(image,format='PNG')
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'POST':
            assert request.url.path.endswith('/services/aigc/text2image/image-synthesis')
            assert request.headers['X-DashScope-Async'] == 'enable'
            assert json.loads(request.content) == {'model':'wanx2.1-t2i-turbo','input':{'prompt':'scene','negative_prompt':'bad'},'parameters':{'n':1,'size':'1024*1024','seed':42,'prompt_extend':False}}
            return httpx.Response(200,json={'output':{'task_id':'task-1','task_status':'PENDING'}})
        if request.url.host == 'images.example':
            assert 'authorization' not in request.headers
            return httpx.Response(200,content=image.getvalue(),headers={'content-type':'image/png'})
        return httpx.Response(200,json={'output':{'task_status':'SUCCEEDED','results':[{'url':'https://images.example/1.png?signature=secret'}]}})
    async def check():
        s = ImageService(Settings(image_key='test'), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), poll_interval=0)
        path = tmp_path/'result.png'
        try:
            stream = s.generate('scene','bad',path,seed=42,prompt_extend=False)
            first = await anext(stream)
            assert first['task_id'] == 'task-1'
            assert len(calls) == 1
            events = [event async for event in stream]
            assert events[-1]['status'] == 'SUCCEEDED'
            assert events[-1]['path'] == str(path)
            assert path.read_bytes() == image.getvalue()
        finally:
            await s.close()
    asyncio.run(check())


@pytest.mark.parametrize('state', ['FAILED','CANCELED','UNKNOWN'])
def test_resume_terminal_without_submit(tmp_path,state):
    def handler(request):
        assert request.method == 'GET'
        return httpx.Response(200,json={'output':{'task_status':state}})
    async def check():
        s = ImageService(Settings(image_key='test'),http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),poll_interval=0)
        try:
            events = [e async for e in s.generate('','',tmp_path/'x.png',task_id='existing')]
            assert events[-1]['status'] == state
            assert events[-1]['task_id'] == 'existing'
        finally:
            await s.close()
    asyncio.run(check())


def test_submit_disconnect_does_not_retry(tmp_path):
    calls=[]
    def handler(request):
        calls.append(request)
        raise httpx.ReadError('connection lost')
    async def check():
        s=ImageService(Settings(image_key='test'), http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            with pytest.raises(ProviderError,match='未知'):
                _ = [e async for e in s.generate('scene','',tmp_path/'x.png')]
            assert len(calls)==1
        finally:
            await s.close()
    asyncio.run(check())


def test_invalid_image_does_not_create_output(tmp_path):
    def handler(request):
        if request.url.host == 'images.example':
            return httpx.Response(200,content=b'<html>not image</html>')
        return httpx.Response(200,json={'output':{'task_status':'SUCCEEDED','results':[{'url':'https://images.example/x'}]}})
    async def check():
        s=ImageService(Settings(image_key='test'),http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        path=tmp_path/'invalid.png'
        try:
            with pytest.raises(ProviderError):
                _=[e async for e in s.generate('','',path,task_id='old')]
            assert not path.exists()
        finally:
            await s.close()
    asyncio.run(check())


def test_timeout_retains_task_id_without_resubmit(tmp_path):
    async def check():
        s=ImageService(Settings(image_key='test'),poll_timeout=0,http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:pytest.fail('must not submit or poll'))))
        try:
            events=[e async for e in s.generate('','',tmp_path/'x.png',task_id='recover-me')]
            assert events[-1]['status']=='TIMEOUT'
            assert events[-1]['task_id']=='recover-me'
        finally:
            await s.close()
    asyncio.run(check())


@pytest.mark.parametrize('url,body,headers',[
    ('http://images.example/x',b'bad',{}),
    ('https://images.example/x',b'abcd',{'content-length':'100'}),
    ('https://images.example/x',b'abcd',{}),
])
def test_download_https_and_size_limits(tmp_path,url,body,headers):
    def handler(request):
        if request.url.host=='images.example':
            return httpx.Response(200,content=body,headers=headers)
        return httpx.Response(200,json={'output':{'task_status':'SUCCEEDED','results':[{'url':url}]}})
    async def check():
        s=ImageService(Settings(image_key='test'),max_download_bytes=3,http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            with pytest.raises(ProviderError):
                _=[e async for e in s.generate('','',tmp_path/'x.png',task_id='old')]
            assert not (tmp_path/'x.png').exists()
        finally:
            await s.close()
    asyncio.run(check())


@pytest.mark.parametrize('model,size',[('wan2.6-t2i','1280*1280'),('wanx2.1-t2i-turbo','256*256'),('wan2.5-t2i-preview','1024*1024')])
def test_invalid_model_or_size_never_submits(tmp_path,model,size):
    async def check():
        s=ImageService(Settings(image_key='test',image_model=model),http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:pytest.fail('invalid request must not reach network'))))
        try:
            with pytest.raises(ProviderError):
                _=[e async for e in s.generate('test','',tmp_path/'x.png',size=size)]
        finally:
            await s.close()
    asyncio.run(check())


def test_sdk_2x_image_jobs_example_uses_real_sdk_with_mock_transport(monkeypatch):
    import dashscope
    from examples import sdk_demo
    from examples.common import PROMPTS
    requests=[]
    def handler(request):
        requests.append(request)
        if request.method=='POST':
            payload=json.loads(request.content)
            assert payload['input']['prompt']==PROMPTS['image']
            assert payload['input']['negative_prompt']==PROMPTS['negative']
            assert payload['parameters']['seed']==42
            assert request.headers['X-DashScope-Async']=='enable'
            return httpx.Response(200,json={'output':{'task_id':'sdk-task','task_status':'PENDING'}})
        assert request.url.path=='/api/v1/tasks/sdk-task'
        return httpx.Response(200,json={'output':{'task_id':'sdk-task','task_status':'SUCCEEDED','results':[{'url':'https://images.example/x'}]}})
    actual_client=dashscope.Client
    monkeypatch.setenv('DASHSCOPE_API_KEY','test-only')
    monkeypatch.setenv('DASHSCOPE_BASE_URL','https://dashscope.aliyuncs.com/api/v1')
    monkeypatch.setenv('DASHSCOPE_MODEL','wanx2.1-t2i-turbo')
    monkeypatch.setattr(sdk_demo.dashscope,'Client',lambda **kwargs:actual_client(**kwargs,http_client=httpx.Client(transport=httpx.MockTransport(handler))))
    sdk_demo.main('image')
    assert len(requests)==2
