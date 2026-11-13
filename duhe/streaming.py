"""Bound a whole stream, including providers that keep connections alive."""
import asyncio


async def timed_events(stream, timeout, heartbeat=5):
    loop=asyncio.get_running_loop();started=loop.time();pending=None
    try:
        pending=asyncio.create_task(anext(stream))
        while True:
            remaining=timeout-(loop.time()-started)
            if remaining<=0:
                raise TimeoutError(f'文本生成超过{timeout:g}秒，已停止等待；本轮未提交，可稍后重试。')
            done,_=await asyncio.wait({pending},timeout=min(heartbeat,remaining))
            if not done:
                yield {'type':'waiting','seconds':int(loop.time()-started)}
                continue
            try:part=pending.result()
            except StopAsyncIteration:return
            yield part
            pending=asyncio.create_task(anext(stream))
    finally:
        if pending is not None:
            if not pending.done():pending.cancel()
            await asyncio.gather(pending,return_exceptions=True)
        await stream.aclose()
