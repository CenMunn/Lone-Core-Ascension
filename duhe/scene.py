"""Create a branch-local scene frame from the prior committed scene."""
from .world import appearance_for
from .rules import scene_for

CONTINUOUS_ACTIONS={'rest','train','scan','refine','absorb_core','detox','forage','purify'}

def build_scene(state,event,ancestor_scene=None):
    frame=scene_for(state,event)
    if (ancestor_scene and event.get('action_id') in CONTINUOUS_ACTIONS
            and ancestor_scene.get('location')==frame.get('location')
            and not ancestor_scene.get('combat_active') and not frame.get('combat_active')):
        cast=list(ancestor_scene.get('present_character_ids') or ['protagonist'])
        frame['present_character_ids']=cast
        frame['romance_budget']=int(bool(state.get('romance_event') and 'heroine' in cast))
        frame['appearance_snapshots']={cid:appearance_for(cid,state,frame) for cid in cast}
    return frame
