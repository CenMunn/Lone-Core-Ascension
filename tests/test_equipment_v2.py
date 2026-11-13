import copy
import pytest
from duhe.equipment import craft_equipment, equip, unequip, equipment_stats
from duhe.models_v2 import migrate_state
from duhe.rules import new_game,apply_action

def ready():
    old,_=apply_action(new_game(),'opening');old['inventory'].update(material=8,clean_core=3)
    return migrate_state(old,story_turn=1,operation_seq=1)

def test_craft_and_equip_swaps_items_without_free_healing_or_story_turn():
    state=ready();old=copy.deepcopy(state)
    crafted,event=craft_equipment(state,'black_iron_armor','craft')
    assert state==old and crafted['story_turn']==1
    assert crafted['inventory']['material']==5 and crafted['inventory']['clean_core']==1
    assert sum(crafted['clean_core_grades'].values())==1
    instance=event['instance_id'];before_hp=crafted['hp']
    dressed,_=equip(crafted,instance,'chest','equip')
    assert dressed['equipment_slots']['chest']==instance and dressed['hp']==before_hp
    assert equipment_stats(dressed)['defense']>=8
    assert len(dressed['equipment_items'])==len(crafted['equipment_items'])
    assert any(v['item_id']=='repair_jacket' for v in dressed['equipment_items'].values())
    removed,_=unequip(dressed,'chest','remove')
    assert removed['equipment_slots']['chest'] is None and instance in removed['equipment_items']
    redressed,_=equip(removed,instance,'chest','reequip')
    assert redressed['hp']==before_hp and redressed['story_turn']==1

def test_wrong_slot_missing_material_and_duplicate_operation_are_atomic():
    state=ready();before=copy.deepcopy(state)
    with pytest.raises(ValueError):craft_equipment(state,'iron_king_chest','bad')
    with pytest.raises(ValueError):equip(state,state['equipment_slots']['weapon'],'feet','bad')
    assert state==before
    crafted,_=craft_equipment(state,'black_iron_armor','once')
    with pytest.raises(ValueError):craft_equipment(crafted,'black_iron_armor','once')


def test_time_amulet_saves_once_per_encounter():
    from duhe.combat import start_encounter, combat_step
    state = ready()
    state['equipment_items']['time-one'] = {'instance_id': 'time-one', 'item_id': 'time_amulet'}
    worn, _ = equip(state, 'time-one', 'accessory', 'equip-time')
    started, _ = start_encounter(worn, 'rotted_hound', 'fight')
    started['hp'] = 1
    survived, event = combat_step(started, {'action': 'guard'}, 'first')
    assert survived['hp'] == 1 and survived['combat']['time_amulet_used']
    defeated, event = combat_step(survived, {'action': 'guard'}, 'second')
    assert event['outcome'] == 'defeat' and defeated['hp'] == 0
