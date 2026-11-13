import copy
import pytest
from duhe.rules import new_game, actions_for, apply_action, validate_state
from duhe.world import REALMS, ABILITY_RANKS


def act(s, key):
    return apply_action(s,key)[0]


def test_opening_rescue_has_no_kill_or_reward_and_normal_no_skip():
    s=new_game()
    assert s['ability_rank']=='UNRANKED' and not s['flags'].get('system_bound')
    assert s['body_stage']=='underfed'
    assert 'demo_jump' not in [a['id'] for a in actions_for(s)]
    s=act(s,'opening')
    assert s['flags']['system_bound'] and not s['claimed_rewards']
    assert s['heroine_rank']=='SS'


def test_reject_invalid_action_without_mutation_and_idempotent_operation():
    s=new_game(); old=copy.deepcopy(s)
    with pytest.raises(ValueError): apply_action(s,'breakthrough')
    assert s==old
    s,e=apply_action(s,'opening','one')
    with pytest.raises(ValueError): apply_action(s,'train','one')


def test_stage_and_floor_tables_are_complete():
    from duhe.rules import RULES
    assert len(REALMS)==10 and len(RULES['stages'])==40
    assert len(RULES['floors'])==100
    assert len([f for f in RULES['floors'] if f['guardian']])==10
    assert ABILITY_RANKS[-1]=='ULTRA'


def test_rest_does_not_grant_training_or_infinite_free_resources():
    s=act(new_game(),'opening'); s['energy']=0
    before=copy.deepcopy(s)
    s=act(s,'rest')
    assert s['training_days']==0 and s['xp']==0
    assert s['inventory']['food'] < before['inventory']['food']
    assert s['countdown'] < before['countdown']


def test_demo_checkpoints_are_valid_and_have_legal_play():
    for checkpoint in ('opening','breakthrough','wall','guardian','finale'):
        s=new_game(mode='demo',checkpoint=checkpoint)
        validate_state(s)
        assert actions_for(s) and s['mode']=='demo'
    with pytest.raises(ValueError): new_game(mode='normal',checkpoint='finale')


def test_absorption_requires_owned_unconsumed_echo():
    s=new_game(mode='demo',checkpoint='breakthrough')
    assert not any(a['id'].startswith('absorb:') for a in actions_for(s))
    with pytest.raises(ValueError): apply_action(s,'absorb:fake')


def test_body_requires_recorded_training_and_recovery():
    s=act(new_game(),'opening'); s=act(s,'train')
    assert s['body_stage']=='underfed'
    for _ in range(4):
        if s['energy']<25: s=act(s,'rest')
        if s['inventory']['food']<2: s=act(s,'forage')
        s=act(s,'train')
    assert s['body_stage'] in ('underfed','recovering')


def test_finale_cannot_be_completed_without_fighting():
    s=new_game(mode='demo',checkpoint='finale')
    with pytest.raises(ValueError): apply_action(s,'final_purify')
    s=act(s,'enter_floor')
    assert s['combat']['kind']=='tower'
    assert s['tower_floor']==100 and not s['flags'].get('victory')


def test_full_normal_campaign_reaches_all_40_stages_100_floors_and_ultra():
    s=new_game(); seen=set(); completed=[]
    for step in range(3500):
        seen.add(s['realm_index']*4+s['realm_stage'])
        if s['flags'].get('victory'): break
        ids={a['id'] for a in actions_for(s)}
        assert ids, f"deadlock at {step}: {s}"
        if s['combat']:
            c=s['combat']
            key='guard' if c['guardian'] and not c['broken'] else 'skill' if 'skill' in ids else 'attack'
        elif 'opening' in ids: key='opening'
        elif s['inventory']['food']<2: key='forage'
        elif (s['energy']<28 or s['hp']<min(s['max_hp'],110)) and 'rest' in ids: key='rest'
        elif s['pollution']>=40 and 'purify' in ids: key='purify'
        elif 'absorb_core' in ids and s['ability_rank'] != 'UR' and s['realm_index']*4+s['realm_stage']>=4: key='absorb_core'
        elif 'craft' in ids: key='craft'
        elif 'heroine_sss' in ids: key='heroine_sss'
        elif 'wall_defend' in ids: key='wall_defend'
        elif 'heroine_ur' in ids: key='heroine_ur'
        elif 'final_purify' in ids: key='final_purify'
        elif 'breakthrough' in ids: key='breakthrough'
        elif 'enter_floor' in ids: key='enter_floor'
        elif 'trial' in ids: key='trial'
        elif s['inventory']['clean_core']<8 and 'refine' in ids: key='refine'
        elif s['xp']<200 and 'train' in ids: key='train'
        elif 'explore' in ids: key='explore'
        else: key='forage'
        s=act(s,key); completed.append(key)
    assert s['flags'].get('victory'), (step,s)
    assert seen==set(range(40))
    assert s['cleared_floors']==list(range(1,101))
    assert s['ability_rank']=='ULTRA' and s['heroine_rank']=='UR'
    assert len(s['claimed_rewards'])==len(set(s['claimed_rewards']))
    assert s['training_days']>0 and s['recovery_days']>0
    assert s['countdown']>0


def test_real_defeat_echo_extraction_consumes_only_owned_drop():
    s=new_game(mode='demo',checkpoint='breakthrough'); s=act(s,'explore')
    while s['combat']: s=act(s,'skill' if s['energy']>=12 else 'attack')
    echo=s['echoes'][0]; key='absorb:'+echo['id']
    s=act(s,key)
    assert echo['id'] in s['consumed_echoes']
    assert any(skill['source']==echo['id'] for skill in s['skills'])
    with pytest.raises(ValueError): apply_action(s,key)


def test_rejected_forged_terminal_and_nonsequential_tower():
    s=new_game(); s['ability_rank']='ULTRA'
    with pytest.raises(ValueError): validate_state(s)
    s=new_game(); s['cleared_floors']=[2]
    with pytest.raises(ValueError): validate_state(s)


def test_each_demo_checkpoint_advances_its_advertised_event():
    for checkpoint,key in [('opening','opening'),('breakthrough','breakthrough'),('wall','wall_defend'),('guardian','enter_floor'),('finale','enter_floor')]:
        s=new_game(mode='demo',checkpoint=checkpoint)
        before=copy.deepcopy(s)
        s,e=apply_action(s,key,'demo:'+checkpoint)
        assert s['turn']==before['turn']+1 and e['summary']
        validate_state(s)


def test_unearned_body_is_rejected_and_canonical_preferences_do_not_override():
    s=new_game({'name':'无敌','ability_rank':'ULTRA','hair_color':'white'})
    assert s['ability_rank']=='UNRANKED'
    s['body_stage']='trained'
    with pytest.raises(ValueError): validate_state(s)


def test_rank_progression_unlocks_system_ability_and_effect_has_cost():
    s=new_game(mode='demo',checkpoint='breakthrough')
    s=act(s,'breakthrough')
    assert any(a['id']=='core_scan' for a in s['abilities'])
    s['pollution']=30; clean=s['inventory']['clean_core']
    s=act(s,'purify')
    assert s['pollution']==5 and s['inventory']['clean_core']==clean-1


def test_high_pollution_with_no_cores_has_costly_recovery_route():
    s=act(new_game(),'opening'); s['pollution']=100
    assert s['inventory']['raw_core']==s['inventory']['clean_core']==0
    assert 'detox' in {a['id'] for a in actions_for(s)}
    before=copy.deepcopy(s)
    s=act(s,'detox')
    assert s['pollution']<before['pollution']
    assert s['inventory']['food']<before['inventory']['food']
    assert s['energy']<before['energy'] and s['countdown']<before['countdown']


def test_low_energy_tower_entry_is_not_advertised_or_applied():
    s=new_game(mode='demo',checkpoint='guardian')
    for _ in range(5): s=act(s,'train')
    assert s['energy']==0
    assert 'enter_floor' not in {a['id'] for a in actions_for(s)}
    original=copy.deepcopy(s)
    with pytest.raises(ValueError): apply_action(s,'enter_floor','low-energy')
    assert s==original
    s=act(s,'rest')
    assert 'enter_floor' in {a['id'] for a in actions_for(s)}


@pytest.mark.parametrize('field', ['completed_operations','xp','echoes','consumed_echoes','defeated_enemies','recovery_days','encounter_serial','abilities','heroine_rank','combat','last_action','last_event','romance_event','skill_slots','demo_checkpoint','hunter_rank','world_version'])
def test_execution_fields_are_required_at_state_boundary(field):
    s=new_game(); del s[field]
    with pytest.raises(ValueError): validate_state(s)
    with pytest.raises(ValueError): apply_action(s,'opening','imported-operation')


@pytest.mark.parametrize('field,value', [
    ('flags',[]),('flags',{'system_bound':'false'}),('flags',{'system_bound':1}),
    ('ability_rank',[]),('ability_rank',1),('ability_rank','ULTRA'),
    ('heroine_rank',None),('heroine_rank',[]),('heroine_rank','ULTRA'),
    ('inventory',[]),('inventory',{'food':True}),('equipment',[]),
    ('skills',{}),('skills',[{}]),('abilities',[None]),
    ('relationships',[]),('relationships',{'heroine':{'trust':'high','events':[]}}),
    ('echoes',[{}]),('echoes','bad'),('completed_operations',[{}]),
    ('consumed_echoes',[[]]),('defeated_enemies',[None]),('known_facts',{}),
    ('wounds','none'),('combat',{}),('combat',[]),
    ('xp',-1),('xp','10'),('recovery_days',None),('training_days',True),
    ('max_hp','100'),('day',0),('preferences',[]),('romance_event',1),
    ('skill_slots',0),('encounter_serial',-1),('last_action',None),
    ('last_event',{}),('hunter_rank',[]),('schema',True),('world_version',False),
])
def test_malformed_imported_field_is_rejected_with_value_error(field,value):
    s=new_game(); s[field]=value
    with pytest.raises(ValueError): validate_state(s)


def _tactical_combat(approach):
    s=new_game({'approach':approach},mode='demo',checkpoint='breakthrough')
    s=act(s,'explore'); s['combat']['hp']=s['combat']['max_hp']=300
    s['energy']=40
    return s


def test_preferences_produce_small_real_tactical_differences():
    base=_tactical_combat('默认')
    cautious=_tactical_combat('谨慎观察')
    b=act(base,'guard'); c=act(cautious,'guard')
    assert c['energy']==b['energy']+2
    assert c['combat']['hp']==b['combat']['hp'] and c['hp']==b['hp']
    front=_tactical_combat('正面突破')
    b=act(base,'attack'); f=act(front,'attack')
    assert f['combat']['hp']==b['combat']['hp']-2
    assert f['hp']==b['hp']-1
    environment=_tactical_combat('利用环境')
    e=act(environment,'attack')
    assert e['combat']['hp']==b['combat']['hp']-2
    b=act(b,'attack'); e=act(e,'attack')
    assert e['combat']['hp']==b['combat']['hp']-2


def test_tactical_bonus_is_disclosed_in_action_hints():
    s=_tactical_combat('谨慎观察')
    assert '12' in next(a['hint'] for a in actions_for(s) if a['id']=='guard')
    s=_tactical_combat('正面突破')
    assert '+2' in next(a['hint'] for a in actions_for(s) if a['id']=='attack')
    assert '+1' in next(a['hint'] for a in actions_for(s) if a['id']=='attack')


def test_wall_before_heroine_research_still_allows_sss_then_ur():
    s=new_game(mode='demo',checkpoint='guardian')
    s['heroine_rank']='SS'; s['flags']['wall_saved']=False
    for flag in ('heroine_sss','heroine_ur'): s['flags'].pop(flag,None)
    assert 'heroine_ur' not in {a['id'] for a in actions_for(s)}
    s=act(s,'wall_defend')
    while s['combat']:
        s=act(s,'guard' if not s['combat']['broken'] else 'skill' if s['energy']>=12 else 'attack')
    assert s['flags']['wall_saved'] and s['heroine_rank']=='SS'
    s=act(s,'heroine_sss')
    assert s['heroine_rank']=='SSS' and 'heroine_ur' in {a['id'] for a in actions_for(s)}
    s=act(s,'heroine_ur')
    assert s['heroine_rank']=='UR'
    assert s['relationships']['heroine']['events'][-2:]==['为她守住研究阵地','共同守护逆向净化实验']


def test_tactical_preference_from_import_must_be_text():
    s=new_game(); s['preferences']['approach']={}
    with pytest.raises(ValueError): validate_state(s)


def test_rival_choices_are_mutually_exclusive_costly_and_branch_local():
    s=new_game(mode='demo',checkpoint='wall')
    ids={a['id'] for a in actions_for(s)}
    assert {'rival_refuse','rival_trade'}<=ids
    refused,event=apply_action(s,'rival_refuse')
    traded,other=apply_action(s,'rival_trade')
    assert refused['energy']==s['energy']-5
    assert traded['inventory']['material']==s['inventory']['material']-3
    assert traded['inventory']['food']==s['inventory']['food']+4
    assert refused['countdown']==traded['countdown']==s['countdown']-1
    assert refused['realm_index']==traded['realm_index']==s['realm_index']
    assert refused['flags']['rival_refused'] and not refused['flags'].get('rival_traded')
    assert traded['flags']['rival_traded'] and not traded['flags'].get('rival_refused')
    assert refused['relationships']['rival']['events']!=traded['relationships']['rival']['events']
    assert not s['relationships']['rival']['events']
    for resolved in (refused,traded):
        assert not {'rival_refuse','rival_trade'} & {a['id'] for a in actions_for(resolved)}
        for action in ('rival_refuse','rival_trade'):
            with pytest.raises(ValueError): apply_action(resolved,action)
    from duhe.rules import scene_for
    scene=scene_for(refused,event)
    assert scene['present_character_ids']==['protagonist','rival']
    assert '黑金' in scene['appearance_snapshots']['rival']['outfit']


def test_human_antagonist_reveals_only_high_stage_research_route_with_cost():
    early=act(new_game(),'opening')
    assert 'reject_harvest' not in {a['id'] for a in actions_for(early)}
    assert not any('谢玄策' in fact or '牺牲' in fact for fact in early['known_facts'])
    s=new_game(mode='demo',checkpoint='wall')
    assert 'reject_harvest' not in {a['id'] for a in actions_for(s)}
    s['realm_index']=6; s['realm_stage']=0; s['ability_rank']='S'; s['ability_xp']=__import__('duhe.progression',fromlist=['START']).START['S']
    result,event=apply_action(s,'reject_harvest')
    assert result['energy']==s['energy']-8
    assert result['inventory']['clean_core']==s['inventory']['clean_core']-2
    assert result['flags']['civilian_research_route'] and result['flags']['harvest_rejected']
    assert any('谢玄策' in fact for fact in result['known_facts'])
    assert not result['flags'].get('boss_defeated') and not result['flags'].get('victory')
    assert 'reject_harvest' not in {a['id'] for a in actions_for(result)}
    from duhe.rules import scene_for
    scene=scene_for(result,event)
    assert scene['present_character_ids']==['protagonist','antagonist']
    assert '石墨' in scene['appearance_snapshots']['antagonist']['outfit']
    assert scene['romance_budget']==0 and not scene['combat_active']


def test_story_negotiation_requires_real_resources_and_stays_outside_tower():
    s=new_game(mode='demo',checkpoint='wall'); s['inventory']['material']=0
    assert 'rival_trade' not in {a['id'] for a in actions_for(s)}
    with pytest.raises(ValueError): apply_action(s,'rival_trade')
    s=new_game(mode='demo',checkpoint='guardian')
    assert not {'rival_refuse','rival_trade','reject_harvest'} & {a['id'] for a in actions_for(s)}


def test_optional_antagonist_relationship_is_validated_without_requiring_old_saves_to_have_it():
    s=new_game(mode='demo',checkpoint='wall')
    validate_state(s)
    assert 'antagonist' not in s['relationships']
    s['relationships']['antagonist']=[]
    with pytest.raises(ValueError): validate_state(s)
