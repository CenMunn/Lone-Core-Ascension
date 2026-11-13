import pytest
from duhe.app_v2_draft import require_live_mode


def test_offline_mode_blocks_paid_model_actions():
    with pytest.raises(ValueError, match='离线'):
        require_live_mode('offline')
    with pytest.raises(ValueError, match='离线'):
        require_live_mode(None)
    require_live_mode('api')
