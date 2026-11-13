import base64
import io
import pytest
from PIL import Image
from duhe.reference_images_v2 import encode_reference


def test_reference_encoder_checks_format_size_and_dimensions(tmp_path):
    path = tmp_path / 'portrait.png'
    Image.new('RGB', (400, 400), 'white').save(path)
    encoded = encode_reference(path)
    assert encoded.startswith('data:image/png;base64,')
    assert base64.b64decode(encoded.split(',', 1)[1]) == path.read_bytes()
    small = tmp_path / 'small.png'; Image.new('RGB', (30, 30), 'white').save(small)
    with pytest.raises(ValueError, match='尺寸'):
        encode_reference(small)
    alpha = tmp_path / 'transparent.png'; Image.new('RGBA', (400, 400)).save(alpha)
    with pytest.raises(ValueError, match='透明'):
        encode_reference(alpha)
