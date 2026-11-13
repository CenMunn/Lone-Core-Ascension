from duhe.controller_v2 import ControllerV2
from duhe.storage import Store
from duhe.viewmodel_v2 import available_actions, render_inventory, render_system, render_abilities, render_codex


def test_initial_actions_and_management_panels(tmp_path):
    c = ControllerV2(Store(tmp_path / 'save.sqlite'))
    cid = c.create('owner')
    state = c.store.node('owner', cid)['state']
    actions = available_actions(state)
    assert [x['id'] for x in actions['story']] == ['opening']
    node = c.act('owner', cid, {'action': 'opening'}, 0, 'opening')
    state = node['state']
    assert '生命' in render_system(state) and '能量' in render_system(state)
    assert '食物' in render_inventory(state)
    assert any(x['id'] == 'rest' for x in available_actions(state)['ordinary'])
    assert any(x['id'] == 'polluted_beetle' for x in available_actions(state)['battle'])


def test_unknown_legacy_ability_does_not_break_the_panel(tmp_path):
    c = ControllerV2(Store(tmp_path / 'save.sqlite'))
    cid = c.create('owner')
    state = c.store.node('owner', cid)['state']
    state['skills'].append({'id': 'old-unknown', 'name': '旧能力'})
    assert '微弱能量辨识' in render_abilities(state)


def test_codex_hidden_monsters_have_sensed_description_but_no_stats(tmp_path):
    c = ControllerV2(Store(tmp_path / 'save.sqlite'))
    state = c.store.node('owner', c.create('owner'))['state']
    content = render_codex(state)
    assert '污染甲虫' in content and '尚未解锁' in content
    assert '生命 140' not in content


def test_system_and_inventory_support_english(tmp_path):
    c = ControllerV2(Store(tmp_path / 'save.sqlite'))
    state = c.store.node('owner', c.create('owner'))['state']
    assert 'Health' in render_system(state, en=True)
    assert 'Core energy' in render_system(state, en=True)
    assert 'Food' in render_inventory(state, en=True)
