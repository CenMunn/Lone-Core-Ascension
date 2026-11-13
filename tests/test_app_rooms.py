import asyncio
import pytest
import gradio as gr

from duhe.app import build_app
from duhe.engine import Engine
from duhe.providers import Settings
from duhe.rooms import RoomService


def callbacks(engine):
    app=build_app(engine)
    return app,{f.fn.__name__:f.fn for f in app.fns.values() if f.fn}


def test_return_from_demo_to_normal_starts_at_opening(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        try:
            _,fn=callbacks(e)
            owner='c'*32
            demo=fn['begin']({'owner':owner},'demo','finale','谨慎观察','克制细腻','动画','中文')[0]
            # Dropdown retains its last demo value when user switches the mode.
            normal=fn['begin'](demo,'normal','finale','谨慎观察','克制细腻','动画','中文')[0]
            state=e.store.node(owner,normal['cid'])['state']
            assert state['mode']=='normal' and state['ability_rank']=='UNRANKED'
            assert state['tower_floor']==0 and state['turn']==0
        finally:await e.close()
    asyncio.run(run())


def test_invite_visibility_errors_and_room_restart(tmp_path):
    async def run():
        e=Engine(tmp_path,Settings())
        app,fn=callbacks(e)
        owner='a'*32;guest_owner='b'*32
        cid=e.create(owner);guest_cid=e.create(guest_owner)
        created=fn['create_room']({'owner':owner,'cid':cid},'中文')
        invite,host=created[12],created[13]
        host_session=created[0]
        invite_widget=next(x for x in app.blocks.values() if getattr(x,'label',None)=='邀请口令 / Invite token')
        assert invite_widget.type=='password'
        assert fn['toggle_invite'](True)['type']=='text'
        assert fn['toggle_invite'](False)['type']=='password'
        guest={'owner':guest_owner,'cid':guest_cid}
        with pytest.raises(gr.Error,match='邀请口令无效'):
            fn['join_room']('<redacted>','同行者',guest,'中文')
        with pytest.raises(gr.Error,match='昵称不能为空'):
            fn['join_room'](invite,'',guest,'中文')
        joined=fn['join_room'](' '+invite+' ','同行者',guest,'中文')
        guest_session=joined[0];guest_token=joined[12]
        assert guest_session['room_token']==guest_token
        assert guest_session['cid']==cid and guest_session['personal_cid']==guest_cid
        service=RoomService(e.store)
        service.join(invite,'成员3');service.join(invite,'成员4')
        with pytest.raises(gr.Error,match='房间已满'):
            fn['join_room'](invite,'成员5',guest,'中文')
        await e.close()

        restarted=Engine(tmp_path,Settings())
        try:
            _,fresh=callbacks(restarted)
            host_loaded=fresh['load_session'](host_session,'中文')
            guest_loaded=fresh['load_session'](guest_session,'中文')
            assert host_loaded[12:14]==(host,host)
            assert guest_loaded[12:14]==(guest_token,guest_token)
            service=RoomService(restarted.store)
            service.vote(guest_loaded[12],0,'opening')
            with pytest.raises(PermissionError):service.lock_round(guest_loaded[13],0)
            round_info=service.lock_round(host_loaded[13],0)
            assert round_info['action_id']=='opening'
            service.finish_round(host,0,False)
            invalid=dict(guest_session,room_token='expired')
            fallback=fresh['load_session'](invalid,'中文')
            assert fallback[0]=={'owner':guest_owner,'cid':guest_cid}
            assert fallback[12:14]==('','')
        finally:await restarted.close()
    asyncio.run(run())
