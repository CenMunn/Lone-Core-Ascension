"""Independent ability experience; cultivation still has its own trials and XP."""
import json
from pathlib import Path

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/progression.json').read_text('utf-8'))
LEVELS=CONFIG['levels'];START={};total=0
for level in LEVELS:
    START[level['rank']]=total
    total+=level['next_xp'] or 0


def rank_for(total_xp):
    return next(level['rank'] for level in reversed(LEVELS) if total_xp>=START[level['rank']])


def migrate(state):
    if 'growth_version' not in state:
        state.update(growth_version=1,ability_xp=START.get(state['ability_rank'],START['UR'] if state['ability_rank']=='ULTRA' else 0),cores_absorbed=0)
        state['flags']['growth_migrated']=True
    return state


def info(state):
    rank=state.get('ability_rank','UNRANKED')
    rank='UR' if rank=='ULTRA' else rank
    level=next((x for x in LEVELS if x['rank']==rank),LEVELS[0])
    total=state.get('ability_xp',START.get(rank,0));start=START.get(rank,0)
    return dict(rank=rank,current=max(0,total-start),required=level['next_xp'],total=total,
                core_xp=level['core_xp'],cultivation_xp=max(4,level['core_xp']//4),
                hp_bonus=max(0,list(START).index(rank))*CONFIG['hp_per_rank'] if rank in START else 0,
                attack_bonus=max(0,list(START).index(rank))*CONFIG['attack_per_rank'] if rank in START else 0)
