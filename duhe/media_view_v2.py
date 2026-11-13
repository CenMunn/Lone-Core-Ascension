"""Select displayable images from the current branch only."""
from pathlib import Path

ORDINARY = {'rest', 'rest_full', 'train', 'forage', 'detox', 'fuse', 'use_ability', 'refine',
            'absorb_core', 'craft_equipment', 'equip', 'unequip', 'breakthrough','claim_legacy_boss_rewards'}


def displayed_image(store, owner, cid):
    history = store.history(owner, cid)
    node = history[-1]
    image = node.get('image') or {}
    path = image.get('path')
    if path and Path(path).is_file():
        return path, '当前剧情场景配图。'
    if node.get('event', {}).get('action_id') in ORDINARY:
        for ancestor in reversed(history[:-1]):
            old = ancestor.get('image') or {}
            path = old.get('path')
            if path and Path(path).is_file():
                return path, '上一剧情场景配图；普通操作不重新绘图。'
            if ancestor.get('event', {}).get('action_id') not in ORDINARY:
                break
    note='当前节点配图状态：' + str(image.get('status', '尚未生成'))
    if image.get('error'):
        note+='；'+str(image['error'])+'。可点击“生成或恢复配图”。'
    return None, note
