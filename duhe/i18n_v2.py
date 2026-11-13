"""Stable labels for primary v2 actions and world terms."""
ACTION_EN = {
    'opening': 'First encounter: accept rescue', 'rest': 'Eat and recover',
    'rest_full': 'Rest until recovered', 'train': 'Train and review', 'forage': 'Scavenge for food',
    'detox': 'Detoxify', 'breakthrough': 'Advance cultivation', 'realm_trial': 'Solo realm trial',
    'rival_refuse': 'Reject the exclusive contract', 'heroine_sss': 'Support Shen Jiyue’s research · SSS',
    'first_hunt_report': 'Register the first solo hunt', 'rival_trade': 'Make a limited trade',
    'help_couriers': 'Support Zhou Ye’s supply route', 'secure_samples': 'Secure the contamination samples',
    'reject_harvest': 'Reject the proposal to sacrifice civilians',
    'heroine_ur': 'Support Shen Jiyue’s research · UR', 'wall_prepare': 'Prepare to defend the north wall',
    'tower_segment': 'Clear ordinary tower floors', 'final_purify': 'Purify the Final Core',
    'epilogue': 'Witness the ending', 'attack': 'Basic attack', 'auto_attack': 'Repeat basic attacks until danger',
    'guard': 'Guard', 'retreat': 'Retreat', 'awaken': 'Awaken ULTRA',
    'polluted_beetle': 'Contaminated beetle', 'rotted_hound': 'Corroded hound',
    'claw_beast': 'Rending beast', 'energy_hunter': 'Energy hunter',
    'plague_parasite': 'Plague parasite', 'ash_wolf': 'Ash wolf',
    'thunder_lizard': 'Thunderback lizard', 'life_deer': 'Life deer',
    'core_eater': 'Core-eating drake', 'void_stalker': 'Void stalker',
    'star_beast': 'Star-crowned beast', 'reverse_time_beast': 'Time-reversal beast',
    'forbidden_prism': 'Forbidden prism sovereign',
    'wall_boss': 'North-wall siege beast', 'tower_100': 'Final Core guardian',
}
REALMS_EN = ['Body Tempering', 'Meridian Opening', 'Core Formation', 'Aura Manifestation',
             'Veil Perception', 'Avatar Manifestation', 'Rebirth', 'Heavenly Trial',
             'Transcendence', 'Mythic Unity']
TERMS_EN = {'food': ('Food', 'Used for rest, training and detoxification.'),
            'raw_core': ('Raw cores', 'Purify before absorption.'),
            'clean_core': ('Clean cores', 'Used for absorption, advancement, crafting and research.'),
            'material': ('Materials', 'Used to craft equipment.')}
ABILITY_EN = {'residual_sense': 'Faint energy sense', 'core_pulse': 'Solo core pulse',
              'rending_charge': 'Rending charge', 'shell_guard': 'Shell guard',
              'corrosion_bite': 'Corrosive bite', 'burning_core': 'Burning core',
              'life_return': 'Life return', 'energy_reflow': 'Energy reflow',
              'lightning_strike': 'Thunder strike', 'gravity_fold': 'Gravity fold',
              'time_gap': 'Time gap', 'causal_anchor': 'Causal anchor'}
GEAR_EN = {'repair_knife': 'Repair knife', 'repair_jacket': 'Repair jacket',
           'black_iron_armor': 'Black-iron core armor', 'iron_king_chest': 'Iron King cuirass',
           'gravity_boots': 'Gravity-fold boots', 'time_amulet': 'Time anchor'}
SPECIAL_EN = {'iron_king_chest': 'Reduces incoming attack damage by 10%.',
              'gravity_boots': 'Negates enemy slowing effects.',
              'time_amulet': 'Survive one lethal hit per battle with 1 HP.'}
DUNGEON_EN = {'ruins': 'Outer ruins dungeon', 'ash_den': 'Ashen den',
              'thunder_crack': 'Thunder rift', 'void_nest': 'Void nest', 'sky_tower': 'Skyreach Tower'}
EFFECT_EN = {'passive': 'Passive sensing', 'damage': 'Direct damage', 'bleed': 'Damage and bleeding',
             'poison': 'Damage and poison', 'burn': 'Damage and burning', 'shield': 'Temporary damage reduction',
             'heal': 'Restore health', 'energy_heal': 'Spend health to restore energy',
             'weaken': 'Weaken the enemy', 'control': 'Hinder the enemy; bosses resist',
             'survival': 'Survive one lethal hit per battle'}


def action_label(action):
    key = action['id']
    from .catalog import MONSTERS
    if key in MONSTERS:
        monster=MONSTERS[key]
        kind='BOSS' if monster['boss'] else 'Elite' if monster.get('elite_material') else 'Normal'
        name=('Tower guardian · floor '+str(monster['floor'])) if monster.get('floor') and key!='tower_100' else ACTION_EN.get(key,monster['name'])
        return '['+kind+'] '+name+' · '+monster['rank']
    if key.startswith('tower_') and key != 'tower_100':
        return 'Tower guardian · floor ' + key.split('_', 1)[1]
    return ACTION_EN.get(key, action.get('label', key))
