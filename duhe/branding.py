"""Local artwork and an accessible, scalable emblem for the game header."""
from pathlib import Path
from urllib.parse import quote


EMBLEM = '''<svg viewBox="0 0 120 132" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="独核通天徽标：通天塔、核心与深渊之环">
<g fill="none" stroke="#bceafa" stroke-width="2" stroke-linejoin="round">
<ellipse cx="60" cy="39" rx="45" ry="18" transform="rotate(-18 60 39)"/>
<path d="M21 54 13 66 21 78M99 54 107 66 99 78" opacity=".55"/>
<path d="M38 103 44 66 52 66 52 41 60 12 68 41 68 66 76 66 82 103Z" fill="#102a40"/>
<path d="M48 103 53 83M72 103 67 83M60 12V55M30 111H90M42 119H78"/>
<path d="m60 56 13 15-13 18-13-18Z" fill="#83d9ef" stroke="#b6efff"/>
<path d="m60 63 6 8-6 9-6-9Z" fill="#effbff" stroke="none"/>
</g></svg>'''


def banner_html():
    return ('<header id="banner" class="game-banner">'
            '<div class="game-title"><h1>独核通天</h1>'
            '<p>核心纪元 · 你将扮演陆凌霄，<br class="banner-break">在废墟中成长并守护人类文明。</p></div>'
            '<div class="game-emblem">' + EMBLEM + '</div></header>')


def artwork_css(root: Path):
    """Serve a project-owned asset through Gradio's existing allowed output path."""
    image = root / 'output' / 'brand' / 'tower-background-gpt.png'
    if not image.is_file():
        return ''
    url = '/gradio_api/file=' + quote(image.resolve().as_posix(), safe='/:')
    return ':root{--duhe-world-image:url("' + url + '")}'
