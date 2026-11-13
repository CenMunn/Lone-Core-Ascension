import pytest
from duhe.controller_v2 import ControllerV2
from duhe.storage import Store
from duhe.suggestions_v2 import validate, token


def test_suggestion_preserves_intent_and_cannot_cross_nodes(tmp_path):
    store = Store(tmp_path / 'suggestions.sqlite'); c = ControllerV2(store)
    cid = c.create('owner')
    opening = c.act('owner', cid, {'action': 'opening'}, 0, 'opening')
    proposals = validate({'choices': [{'key': 'ordinary:rest', 'label': '在掩体恢复',
                                       'intent': '回到掩体进食休整'}]}, opening['state'])
    store.set_suggestions_v2('owner', cid, opening['id'], proposals)
    selected = token(store.node('owner', cid), 0)
    result = c.act('owner', cid, {'action': 'use_suggestion', 'token': selected}, 1, 'choose')
    assert result['event']['player_intent'] == '回到掩体进食休整'
    assert result['state']['story_turn'] == 1
    with pytest.raises(ValueError):
        c.act('owner', cid, {'action': 'use_suggestion', 'token': selected}, 2, 'stale')


def test_unknown_action_suggestion_is_rejected(tmp_path):
    store = Store(tmp_path / 'suggestions.sqlite'); c = ControllerV2(store)
    cid = c.create('owner'); state = store.node('owner', cid)['state']
    with pytest.raises(ValueError):
        validate({'choices': [{'key': 'story:win', 'label': '直接通关', 'intent': '打败母皇'}]}, state)
