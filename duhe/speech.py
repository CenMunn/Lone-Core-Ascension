"""Optional keyless online neural narration. Never called automatically."""
import asyncio,hashlib,re
from pathlib import Path

VOICES={'中文女声':'zh-CN-XiaoxiaoNeural','中文男声':'zh-CN-YunxiNeural','English':'en-US-AriaNeural'}

async def narrate(root,text,voice='中文女声'):
    import edge_tts
    text=re.sub(r'[#*_`>]+','',text).strip()
    if not text:raise ValueError('请先生成故事正文。')
    if len(text)>10000:raise ValueError('本次正文过长，请分段朗读。')
    if voice not in VOICES:raise ValueError('无效音色')
    key=hashlib.sha256((VOICES[voice]+text).encode()).hexdigest()
    target=Path(root)/'output/speech'/f'{key}.mp3';target.parent.mkdir(parents=True,exist_ok=True)
    if target.is_file() and target.stat().st_size>1000:return str(target)
    temporary=target.with_suffix('.part')
    try:
        async with asyncio.timeout(60):
            await edge_tts.Communicate(text,VOICES[voice],connect_timeout=10,receive_timeout=30).save(str(temporary))
        if temporary.stat().st_size<1000:raise ValueError('没有收到有效音频')
        temporary.replace(target);return str(target)
    except Exception as exc:
        raise RuntimeError(f'在线配音未完成（{type(exc).__name__}）。请稍后重试，正文和本地氛围音仍可使用。') from None
    finally:temporary.unlink(missing_ok=True)
