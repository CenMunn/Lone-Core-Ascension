"""本地合成氛围音，无外部素材版权依赖。"""
import math
import struct
import wave
from pathlib import Path


def ambient(root:Path, kind='camp', volume=0.3):
    target=Path(root)/'output/audio'/f'{kind}-{int(volume*100)}.wav'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():return str(target)
    rate=16000;freq={'camp':110,'ruins':82.4,'tower':65.4}.get(kind,110)
    frames=bytearray()
    for i in range(rate*8):
        t=i/rate;fade=min(1,t,8-t)
        value=(math.sin(2*math.pi*freq*t)+.35*math.sin(2*math.pi*freq*1.5*t))*.14*volume*fade
        frames.extend(struct.pack('<h',int(value*32767)))
    with wave.open(str(target),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(frames)
    return str(target)
