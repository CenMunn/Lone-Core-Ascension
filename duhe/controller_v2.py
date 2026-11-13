"""Version-two rule dispatch and optimistic, branch-local persistence."""
from .rules import new_game, apply_action
from .models_v2 import migrate_state, validate_state_v2
from .inventory import apply_resource_action
from .ordinary_v2 import perform_ordinary
from .equipment import craft_equipment, equip, unequip
from .combat import start_encounter, combat_step, auto_attack
from .progression_v2 import advance_stage, start_realm_trial
from .campaign import advance_tower_segment, purify_final_core, finish_epilogue, perform_milestone
from .scene_v2 import scene_for_v2


class ControllerV2:
    def __init__(self, store):
        self.store = store

    def create(self, owner, preferences=None, *, mode='normal', checkpoint='opening'):
        state = migrate_state(new_game(preferences, mode, checkpoint), story_turn=0, operation_seq=0)
        from .affinity import initialize
        initialize(state)
        if mode == 'demo' and checkpoint in ('guardian', 'finale'):
            guardian = f"tower_{state['tower_floor']}"
            state['flags'].setdefault('unlocked_bosses', []).append(guardian)
        if mode == 'demo' and checkpoint == 'wall':
            state['flags'].pop('wall_saved', None)
            state['flags'].setdefault('unlocked_bosses', []).append('wall_boss')
        return self.store.create(owner, state)

    def act(self, owner, cid, request, revision, operation_id):
        before, result, event, frame = self.prepare(owner, cid, request, revision, operation_id)
        text = event.get('description') or event.get('summary') or '操作已结算：' + request['action']
        return self.store.commit(owner, cid, before['id'], revision, operation_id,
                                 result, text, event, {'source': 'v2-rules', 'scene': frame})

    def prepare(self, owner, cid, request, revision, operation_id):
        if not isinstance(request, dict) or not isinstance(request.get('action'), str):
            raise ValueError('行动格式无效')
        camp = self.store.campaign(owner, cid)
        if camp['revision'] != revision:
            raise ValueError('页面进度已改变，请刷新后重试')
        before = self.store.node(owner, cid)
        state = validate_state_v2(before['state'])
        action = request['action']
        intent = None
        if action == 'use_suggestion':
            from .suggestions_v2 import resolve
            request, intent = resolve(before, request.get('token'))
            action = request['action']
        elif action == 'frozen_suggestion':
            from .suggestions_v2 import legal_requests
            from .content_guard import assert_private
            candidate = request.get('request')
            intent = request.get('intent')
            if not isinstance(candidate,dict) or not isinstance(intent,str):raise ValueError('冻结推荐无效')
            if candidate not in [x['request'] for x in legal_requests(state).values()]:raise ValueError('冻结行动当前不可执行')
            assert_private(intent);request=candidate;action=request['action']
        if action=='free_story':
            from .free_story import prepare_free_story
            result,event=prepare_free_story(state,request.get('intent'),operation_id)
        elif action in ('continue_story','story_investigate','story_converse'):
            from .story_flow import continue_narrative
            result,event=continue_narrative(state,action,operation_id)
        elif action == 'opening':
            if state['flags'].get('system_bound') or state['operation_seq']:
                raise ValueError('初遇已经发生')
            old, event = apply_action(new_game(state.get('preferences'), state.get('mode', 'normal'), 'opening'), 'opening', operation_id)
            result = migrate_state(old, story_turn=1, operation_seq=1)
        elif action in ('refine', 'absorb_core'):
            result, event = apply_resource_action(state, request, operation_id)
        elif action in ('rest', 'rest_full', 'train', 'forage', 'detox', 'fuse', 'use_ability', 'claim_legacy_boss_rewards'):
            result, event = perform_ordinary(state, action, operation_id, target=request.get('target'))
        elif action == 'craft_equipment':
            result, event = craft_equipment(state, request.get('item_id'), operation_id)
        elif action == 'equip':
            result, event = equip(state, request.get('instance_id'), request.get('slot'), operation_id)
        elif action == 'unequip':
            result, event = unequip(state, request.get('slot'), operation_id)
        elif action == 'start_encounter':
            result, event = start_encounter(state, request.get('monster_id'), operation_id,
                                            source=request.get('source', 'story'))
        elif action in ('attack', 'skill', 'guard', 'retreat', 'awaken'):
            result, event = combat_step(state, request, operation_id)
        elif action == 'auto_attack':
            result, event = auto_attack(state, operation_id)
        elif action == 'use_tactic':
            from .tactics_v2 import resolve_tactic
            proposal = resolve_tactic(before, request.get('token'))
            result, event = combat_step(state, {'action': 'tactic', 'proposal': proposal}, operation_id)
        elif action == 'frozen_tactic':
            result, event = combat_step(state, {'action': 'tactic', 'proposal': request.get('proposal')}, operation_id)
        elif action == 'breakthrough':
            result, event = advance_stage(state, operation_id)
        elif action == 'realm_trial':
            result, event = start_realm_trial(state, operation_id)
        elif action == 'tower_segment':
            result, event = advance_tower_segment(state, operation_id)
        elif action in ('first_hunt_report', 'rival_refuse', 'rival_trade', 'help_couriers', 'secure_samples',
                        'reject_harvest', 'heroine_sss', 'wall_prepare', 'heroine_ur'):
            result, event = perform_milestone(state, action, operation_id)
        elif action == 'final_purify':
            result, event = purify_final_core(state, operation_id)
        elif action == 'epilogue':
            result, event = finish_epilogue(state, operation_id)
        else:
            raise ValueError('不支持的行动')
        from .affinity import apply_scripted
        apply_scripted(before['state'],result,event)
        validate_state_v2(result)
        if intent:
            event['player_intent'] = intent
        frame = scene_for_v2(result, event, before.get('meta', {}).get('scene'))
        return before, result, event, frame
