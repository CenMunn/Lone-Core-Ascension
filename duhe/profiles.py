"""Full character cards shared by the dossier and portrait generator."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CARDS=json.loads((ROOT/'config/profile_cards.json').read_text('utf-8'))

def profile_text(root,character_id):return CARDS[character_id]['text']

def portrait_path(root,character_id):
    revised_unified=Path(root)/'output/characters'/f'{character_id}-anime-v2.png'
    if revised_unified.is_file():return str(revised_unified)
    unified=Path(root)/'output/characters'/f'{character_id}-anime-v1.png'
    if unified.is_file():return str(unified)
    revised=Path(root)/'output/characters'/f'{character_id}-v2.png'
    if revised.is_file():return str(revised)
    path=Path(root)/'output/characters'/f'{character_id}.png'
    return str(path) if path.is_file() else None
