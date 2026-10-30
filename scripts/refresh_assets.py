#!/usr/bin/env python3
"""Refresh public profile cards and a real 31-day contribution graph. Python stdlib only."""
from __future__ import annotations
import argparse
from datetime import date, datetime, time, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
USER = 'HahnGyuTak'
COLORS = {
    'light': {'bg': 'ffffff', 'text': '334155', 'title': '1d4ed8', 'grid': 'e2e8f0'},
    'dark': {'bg': '0d1117', 'text': 'c9d1d9', 'title': '7dd3fc', 'grid': '30363d'},
}

def get_svg(url: str) -> bytes:
    request = Request(url, headers={'User-Agent': 'HahnGyuTak-profile-assets'})
    with urlopen(request, timeout=60) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    if root.tag.rsplit('}', 1)[-1] != 'svg':
        raise ValueError('Response is not SVG')
    visible_text = ' '.join(root.itertext()).lower()
    if any(s in visible_text for s in ('something went wrong', 'rate limit exceeded', 'could not fetch', 'maximum retries')):
        raise ValueError('Widget returned an error card')
    return payload


def calendar_from_github(today: date) -> dict:
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('GITHUB_TOKEN is required unless --audit-data is supplied')
    start = datetime.combine(today - timedelta(days=30), time.min, ZoneInfo('Asia/Seoul'))
    # Do not ask for future hours on the current day.
    end = datetime.now(timezone.utc)
    query = '''query($user:String!,$from:DateTime!,$to:DateTime!){user(login:$user){contributionsCollection(from:$from,to:$to){contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}'''
    body = json.dumps({'query': query, 'variables': {'user': USER, 'from': start.isoformat(), 'to': end.isoformat()}}).encode()
    request = Request('https://api.github.com/graphql', data=body, headers={
        'Authorization': f'Bearer {token}', 'Content-Type': 'application/json',
        'User-Agent': 'HahnGyuTak-profile-assets',
    })
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get('errors'):
        raise RuntimeError('GitHub contribution query failed')
    return result['data']['user']['contributionsCollection']['contributionCalendar']


def graph(calendar: dict, today: date, scheme: str, mobile: bool = False) -> bytes:
    lookup = {d['date']: d['contributionCount'] for w in calendar['weeks'] for d in w['contributionDays']}
    dates = [today - timedelta(days=30-i) for i in range(31)]
    if any(d.isoformat() not in lookup for d in dates):
        raise ValueError('Contribution calendar does not cover the full requested interval')
    values = [lookup[d.isoformat()] for d in dates]
    c = COLORS[scheme]
    maximum = max(5, ((max(values) + 4) // 5) * 5)
    svg_width, svg_height = (420, 254) if mobile else (900, 270)
    x0, y0, width, height = (40, 96, 350, 100) if mobile else (54, 86, 792, 126)
    coords = [(x0+i*width/30, y0+height-v/maximum*height) for i,v in enumerate(values)]
    points = ' '.join(f'{x:.1f},{y:.1f}' for x,y in coords)
    period = f'{dates[0].isoformat()} – {today.isoformat()}'
    total, days = sum(values), sum(v>0 for v in values)
    summary = escape(period) if mobile else f'{escape(period)} · {total} contributions · {days} active days'
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" role="img" aria-labelledby="title desc">
<title id="title">{USER}: contribution activity, last 31 days</title>
<desc id="desc">{escape(period)}. {total} contributions on {days} active days. Snapshot from GitHub; contributions are not a skill rating.</desc>
<rect width="{svg_width}" height="{svg_height}" rx="8" fill="#{c['bg']}"/>
<g font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif">
<text x="28" y="31" font-size="17" font-weight="600" fill="#{c['title']}">Contribution activity · last 31 days</text>
<text x="28" y="56" font-size="12" fill="#{c['text']}">{summary}</text>''']
    if mobile:
        parts.append(f'<text x="28" y="76" font-size="12" fill="#{c["text"]}">{total} contributions · {days} active days</text>')
    for i in range(3):
        value = round(maximum*i/2)
        y = y0+height-value/maximum*height
        parts.append(f'<line x1="{x0}" x2="{x0+width}" y1="{y}" y2="{y}" stroke="#{c["grid"]}"/><text x="{x0-12}" y="{y+4}" text-anchor="end" font-size="11" fill="#{c["text"]}">{value}</text>')
    parts.append(f'<polyline points="{points}" fill="none" stroke="#{c["title"]}" stroke-width="2"/>')
    for i, (x,y) in enumerate(coords):
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.7" fill="#{c["title"]}"><title>{dates[i].isoformat()}: {values[i]} contributions</title></circle>')
    for i in ((0, 10, 20, 30) if mobile else (0, 6, 12, 18, 24, 30)):
        parts.append(f'<text x="{coords[i][0]:.1f}" y="{svg_height-34}" text-anchor="middle" font-size="11" fill="#{c["text"]}">{dates[i].strftime("%b %d")}</text>')
    footer = f'GitHub · updated {today.isoformat()}' if mobile else f'Source: GitHub contribution calendar · updated {today.isoformat()}'
    parts.append(f'<text x="28" y="{svg_height-12}" font-size="10" fill="#{c["text"]}">{footer}</text></g></svg>')
    return ''.join(parts).encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-data', type=Path)
    parser.add_argument('--today', type=date.fromisoformat)
    parser.add_argument('--include-header', action='store_true')
    args = parser.parse_args()
    today = args.today or datetime.now(ZoneInfo('Asia/Seoul')).date()
    calendar = (json.loads(args.audit_data.read_text())['data']['user']['contributionsCollection']['contributionCalendar']
                if args.audit_data else calendar_from_github(today))
    outputs, sources = {}, {}
    for scheme,c in COLORS.items():
        common = {'username': USER, 'hide_border': 'true', 'bg_color': c['bg'],
                  'text_color': c['text'], 'title_color': c['title'], 'icon_color': c['title'],
                  'disable_animations': 'true', 'card_width': '420'}
        for kind, path, extra in (
            ('stats','api',{'show_icons':'true','hide_rank':'true','custom_title':'GitHub Activity'}),
            ('languages','api/top-langs/',{'layout':'compact','langs_count':'6','custom_title':'Public Repository Languages'}),
        ):
            url = 'https://github-stats-extended.vercel.app/' + path + '?' + urlencode(common | extra)
            filename = f'{kind}-{scheme}.svg'
            outputs[filename] = get_svg(url)
            sources[filename] = url
        for mobile in (False, True):
            filename = f'activity-{scheme}{"-mobile" if mobile else ""}.svg'
            outputs[filename] = graph(calendar, today, scheme, mobile)
            sources[filename] = 'https://api.github.com/graphql (public contribution calendar)'
    if args.include_header:
        outputs['header.svg'] = (ROOT/'assets/header.svg').read_bytes()
        sources['header.svg'] = 'Original repository-owned SVG; no external font or image dependencies'
    for name,payload in outputs.items():
        ET.fromstring(payload)
    assets = ROOT/'assets'
    assets.mkdir(exist_ok=True)
    manifest = assets/'sources.json'
    if manifest.exists():
        sources = json.loads(manifest.read_text()).get('sources', {}) | sources
    # Validate every image before replacing any last-good copy.
    for name,payload in outputs.items():
        pending = assets/(name+'.tmp')
        pending.write_bytes(payload)
        pending.replace(assets/name)
    manifest.write_text(json.dumps({'updated':today.isoformat(),'scope':'public repository cards and contribution calendar','sources':sources},indent=2)+'\n')
    print(f'Refreshed {len(outputs)} valid SVG assets for {USER} ({today})')

if __name__ == '__main__':
    main()
