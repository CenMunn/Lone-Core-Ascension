import asyncio
import json
import zipfile
from pathlib import Path

import gradio as gr
from duhe.app import build_app
from duhe.engine import Engine
from duhe.providers import Settings


def test_download_is_outside_collapsed_run_details(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            app=build_app(e)
            download=next(b for b in app.blocks.values() if isinstance(b,gr.File))
            details=next(b for b in app.blocks.values() if isinstance(b,gr.Accordion) and 'Run details' in b.label)
            def ancestors(node,target,path=()):
                if node.get('id')==target:return path
                for child in node.get('children',[]):
                    result=ancestors(child,target,path+(node.get('id'),))
                    if result is not None:return result
            assert details._id not in ancestors(app.config['layout'],download._id)
        finally:await e.close()
    asyncio.run(run())


def test_export_recovers_browser_session_and_preserves_game_and_images(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings());owner='a'*32
        try:
            app=build_app(e);fn={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
            cid=e.create(owner);n=e.store.node(owner,cid)
            image=tmp_path/'scene.png';image.write_bytes(b'image-fixture')
            e.store.set_image(owner,cid,n['id'],{'status':'SUCCEEDED','path':str(image)})
            before=e.store.node(owner,cid);revision=e.store.campaign(owner,cid)['revision']
            frames=list(fn['export_save']({}, {'owner':owner,'cid':cid},'中文'))
            session,browser,file,status=frames[-1]
            assert session==browser=={'owner':owner,'cid':cid}
            assert '正在打包' in frames[0][-1] and '点击' in status and '下载' in status
            assert file['visible'] is True
            with zipfile.ZipFile(file['value']) as z:
                manifest=json.loads(z.read('manifest.json'))
                assert manifest['campaign']['id']==cid
                assert any(name.startswith('images/') for name in z.namelist())
            assert e.store.node(owner,cid)==before and e.store.campaign(owner,cid)['revision']==revision
        finally:await e.close()
    asyncio.run(run())


def test_export_empty_or_wrong_owner_reports_error_without_old_download(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings());owner='a'*32
        try:
            app=build_app(e);fn={f.fn.__name__:f.fn for f in app.fns.values() if f.fn}
            cid=e.create(owner)
            empty=list(fn['export_save']({}, {},'中文'))[-1]
            assert '请先创建或载入冒险' in empty[-1]
            wrong=list(fn['export_save']({'owner':'b'*32,'cid':cid},{'owner':owner,'cid':cid},'中文'))[-1]
            assert '不可用' in wrong[-1] and wrong[2]['value'] is None and wrong[2]['visible'] is False
            assert not list((tmp_path/'output/saves').glob('*.zip'))
        finally:await e.close()
    asyncio.run(run())
