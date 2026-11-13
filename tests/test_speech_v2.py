import pytest
from duhe.speech_v2 import validate_segments, VOICES_V2


def test_speaker_segments_preserve_the_exact_story_and_cast():
    text = '我抬起头。沈霁月说：“快走。”我没有犹豫。'
    segments = [
        {'speaker_id': 'narrator', 'kind': 'narration', 'text': '我抬起头。沈霁月说：'},
        {'speaker_id': 'heroine', 'kind': 'dialogue', 'text': '“快走。”'},
        {'speaker_id': 'narrator', 'kind': 'narration', 'text': '我没有犹豫。'}]
    valid = validate_segments(text, segments, ['protagonist', 'heroine'])
    assert ''.join(x['text'] for x in valid) == text
    assert VOICES_V2['heroine'] != VOICES_V2['protagonist']
    with pytest.raises(ValueError):
        validate_segments(text, segments[:-1], ['protagonist', 'heroine'])
    segments[1]['speaker_id'] = 'friend'
    with pytest.raises(ValueError):
        validate_segments(text, segments, ['protagonist', 'heroine'])


def test_unquoted_text_cannot_be_assigned_as_dialogue():
    with pytest.raises(ValueError):
        validate_segments('走吧', [{'speaker_id': 'heroine', 'kind': 'dialogue', 'text': '走吧'}], ['heroine'])
