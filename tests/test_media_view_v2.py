from duhe.media_view_v2 import displayed_image
from duhe.controller_v2 import ControllerV2
from duhe.storage import Store


def test_ordinary_action_can_display_only_ancestor_image(tmp_path):
    store = Store(tmp_path / 'state.sqlite'); c = ControllerV2(store)
    cid = c.create('owner')
    first = c.act('owner', cid, {'action': 'opening'}, 0, 'opening')
    file = tmp_path / 'scene.png'; file.write_bytes(b'placeholder')
    store.set_image('owner', cid, first['id'], {'status': 'SUCCEEDED', 'path': str(file)})
    c.act('owner', cid, {'action': 'rest'}, 1, 'rest')
    path, note = displayed_image(store, 'owner', cid)
    assert path == str(file) and '上一剧情场景' in note


def test_narrative_node_does_not_show_previous_scene_as_current(tmp_path):
    store = Store(tmp_path / 'state.sqlite'); c = ControllerV2(store)
    cid = c.create('owner'); first = c.act('owner', cid, {'action': 'opening'}, 0, 'opening')
    file = tmp_path / 'scene.png'; file.write_bytes(b'placeholder')
    store.set_image('owner', cid, first['id'], {'status': 'SUCCEEDED', 'path': str(file)})
    c.act('owner', cid, {'action': 'start_encounter', 'monster_id': 'polluted_beetle'}, 1, 'fight')
    assert displayed_image(store, 'owner', cid)[0] is None
