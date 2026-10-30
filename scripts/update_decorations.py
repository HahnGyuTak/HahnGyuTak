#!/usr/bin/env python3
"""Validate generated assets before replacing the last successful decoration set."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import struct
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def validate(path):
    data = path.read_bytes()
    if path.suffix == '.svg':
        root = ET.fromstring(data)
        if root.tag.rsplit('}', 1)[-1] != 'svg':
            raise ValueError(f'{path.name}: not an SVG')
        if any(e.tag.rsplit('}', 1)[-1] in ('script', 'foreignObject') for e in root.iter()):
            raise ValueError(f'{path.name}: unexpected active content')
    elif path.suffix == '.gif':
        if len(data) < 10 or data[:6] not in (b'GIF87a', b'GIF89a'):
            raise ValueError(f'{path.name}: invalid GIF')
        if not all(struct.unpack('<HH', data[6:10])):
            raise ValueError(f'{path.name}: empty GIF')
    elif path.suffix == '.png':
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError(f'{path.name}: invalid PNG')
    return data

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snake-status', required=True)
    p.add_argument('--bonsai-status', required=True)
    args = p.parse_args()
    assets = ROOT / 'assets'
    manifest_path = assets / 'decorations.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    updates = []
    groups = (
        ('snake', args.snake_status, [('snake-light.svg', 'snake-light.svg'), ('snake-dark.svg', 'snake-dark.svg')],
         'https://github.com/Platane/snk/tree/d8f6715049803e982ee5ff501b6b9b7d5deeb09b'),
        ('bonsai', args.bonsai_status, [(f'bonsai/{name}', f'bonsai/{name}') for name in ('bonsai.svg', 'bonsai.png', 'bonsai.gif', 'bonsai-growth.gif')],
         'https://github.com/egorthinks/git-bonsai/tree/665258cab3f304cfb33a96fc7bf108cec1f452f3'),
    )
    for group, status, files, source in groups:
        if status != 'success':
            print(f'::warning::{group} generation did not succeed; keeping previous assets')
            continue
        # Validate the whole group before replacing any file.
        pending = [(ROOT / '.generated' / src, assets / dst) for src, dst in files]
        for src, _ in pending:
            validate(src)
        updates.extend(pending)
        manifest[group] = {'source': source, 'updated_utc': datetime.now(timezone.utc).isoformat(), 'data': 'Real GitHub contribution history for HahnGyuTak'}
    if not updates:
        raise RuntimeError('No generated decorations were available; existing assets were retained')
    for src, dst in updates:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Validated and updated {len(updates)} decoration assets')

if __name__ == '__main__':
    main()
