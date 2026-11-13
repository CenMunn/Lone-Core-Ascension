"""Classification for version-two action requests."""
from dataclasses import dataclass

@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    category: str
    advances_story: bool

STORY={'opening','heroine_sss','heroine_ur','rival_refuse','rival_trade','reject_harvest','final_purify'}
PREPARE={'explore','trial','wall_defend','enter_floor'}
ORDINARY={'rest','train','forage','refine','absorb_core','scan','detox','purify','craft','forge','breakthrough'}
COMBAT={'attack','guard','skill','dodge','retreat','purify'}

def describe_action(state,request):
    if not isinstance(request,dict) or not isinstance(request.get('action'),str):
        raise ValueError('行动格式无效')
    action=request['action']
    if state.get('combat'):
        if action not in COMBAT:raise ValueError('当前战斗中不能执行该行动')
        return ActionSpec(action,'combat',False)
    if action in STORY:return ActionSpec(action,'story',True)
    if action in PREPARE:return ActionSpec(action,'prepare_battle',True)
    if action in ORDINARY or action.startswith('absorb:'):return ActionSpec(action,'ordinary',False)
    raise ValueError('未知行动')
