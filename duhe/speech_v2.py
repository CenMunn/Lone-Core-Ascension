"""Speaker-aware voice generation from verified, complete story segments."""
import asyncio
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

VOICES_V2 = {'narrator': 'zh-CN-XiaoxiaoNeural', 'protagonist': 'zh-CN-YunxiNeural',
             'heroine': 'zh-CN-XiaoxiaoNeural', 'friend': 'zh-CN-YunyangNeural',
             'mentor': 'zh-CN-YunjianNeural', 'commander': 'zh-CN-XiaoyiNeural',
             'rival': 'zh-CN-YunxiNeural', 'antagonist': 'zh-CN-YunjianNeural',
             'boss': 'zh-CN-XiaoxiaoNeural'}
VOICES_EN = {key: ('en-US-AriaNeural' if key in ('narrator', 'heroine', 'boss', 'commander') else 'en-US-GuyNeural')
             for key in VOICES_V2}

def describe_speech_error(exc):
    children=getattr(exc, 'exceptions', ())
    if children:
        return describe_speech_error(children[0])
    if isinstance(exc, (OSError, TimeoutError)):
        return '连接在线语音服务失败，请检查网络并重试。'
    if isinstance(exc, ModuleNotFoundError):
        return '缺少语音依赖，请安装项目依赖后重试。'
    if isinstance(exc, RuntimeError) and 'ffmpeg' in str(exc).lower():
        return '找不到音频合成工具 ffmpeg，请检查安装和系统路径。'
    return '配音生成或合成失败，请稍后重试。'


def validate_segments(text, segments, present):
    if not isinstance(text, str) or not text.strip() or len(text) > 10000:
        raise ValueError('正文为空或过长')
    if not isinstance(segments, list) or not 1 <= len(segments) <= 30:
        raise ValueError('语音分段数量无效')
    allowed = set(present) & set(VOICES_V2)
    result = []
    for item in segments:
        if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not item['text']:
            raise ValueError('语音分段格式无效')
        speaker, kind = item.get('speaker_id'), item.get('kind')
        if kind == 'narration' and speaker != 'narrator':
            raise ValueError('旁白必须使用旁白音色')
        if kind == 'dialogue':
            if speaker not in allowed or not item['text'].strip().startswith(('“', '「', '『', '"')) or not item['text'].strip().endswith(('”', '」', '』', '"')):
                raise ValueError('对白说话人或引号不明确')
        elif kind != 'narration':
            raise ValueError('语音类型无效')
        result.append({'speaker_id': speaker, 'kind': kind, 'text': item['text']})
    if ''.join(x['text'] for x in result) != text:
        raise ValueError('分段未完整保留原正文')
    return result


def segment_messages(node):
    scene = node.get('meta', {}).get('scene') or {}
    return [{'role': 'system', 'content': '将正文逐字切成旁白和明确说话人的引号对白，返回JSON对象segments数组，每项含speaker_id、kind、text。旁白用narrator与narration。对白用场景中明确的角色ID及dialogue，只标记能从上下文确定说话人的完整引号文本；不能确认的引号也作为narrator旁白，不可猜测。所有text原样拼接必须与输入正文完全相同，不得增删字符。'},
            {'role': 'user', 'content': json.dumps({'正文': node['text'], '场景人物ID': scene.get('present_character_ids', [])}, ensure_ascii=False)}]


async def render_segments(root, text, segments, present, language='zh-CN'):
    import edge_tts
    segments = validate_segments(text, segments, present)
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('未找到音频合成工具 ffmpeg')
    if language not in ('zh-CN', 'en-US'):
        raise ValueError('不支持的配音语言')
    voices = VOICES_EN if language == 'en-US' else VOICES_V2
    fingerprint = hashlib.sha256((language + json.dumps(segments, ensure_ascii=False, sort_keys=True)).encode()).hexdigest()
    directory = Path(root) / 'output' / 'speech_v2'
    directory.mkdir(parents=True, exist_ok=True)
    cache = directory / 'segments'
    cache.mkdir(parents=True, exist_ok=True)
    target = directory / (fingerprint + '.mp3')
    if target.is_file() and target.stat().st_size > 1000:
        return str(target)
    with tempfile.TemporaryDirectory(prefix='voice-', dir=directory) as temp:
        semaphore = asyncio.Semaphore(1)
        async def make_segment(index, segment):
            path = Path(temp) / f'{index:02d}.mp3'
            key = hashlib.sha256((voices[segment['speaker_id']] + '\0' + segment['text']).encode()).hexdigest()
            cached = cache / (key + '.mp3')
            if cached.is_file() and cached.stat().st_size > 1000:
                return cached
            async with semaphore:
                for attempt in range(3):
                    try:
                        async with asyncio.timeout(60):
                            await edge_tts.Communicate(segment['text'], voices[segment['speaker_id']],
                                                       connect_timeout=10, receive_timeout=30).save(str(path))
                        break
                    except (OSError, TimeoutError):
                        if attempt == 2: raise
                        await asyncio.sleep(attempt + 1)
            if not path.is_file() or not path.stat().st_size:
                raise RuntimeError('在线语音服务没有返回音频')
            path.replace(cached)
            return cached
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(make_segment(index, segment)) for index, segment in enumerate(segments)
                     if segment['text'].strip()]
        paths = [task.result() for task in tasks]
        merged = Path(temp) / 'merged.mp3'
        args = [ffmpeg, '-v', 'error', '-y']
        for path in paths:
            args += ['-i', str(path)]
        args += ['-filter_complex', f'concat=n={len(paths)}:v=0:a=1[out]', '-map', '[out]',
                 '-codec:a', 'libmp3lame', str(merged)]
        process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL,
                                                       stderr=asyncio.subprocess.PIPE)
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        except (TimeoutError, asyncio.CancelledError):
            process.kill(); await process.wait(); raise
        if process.returncode or not merged.is_file() or merged.stat().st_size < 1000:
            raise RuntimeError('语音片段合成失败')
        merged.replace(target)
    return str(target)
