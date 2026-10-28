#!/usr/bin/env python3
"""Render scripts, dashboard and voice helper for one remote entity; never writes HA."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def render(entity, output):
    if not re.fullmatch(r'remote\.[a-z0-9_]+', entity):
        raise ValueError('Expected a remote.entity_id')
    names = ('scripts.yaml', 'dashboard.yaml', 'voice-helper.json')
    if any((output / name).exists() for name in names):
        raise FileExistsError('Output already exists; refusing to overwrite')
    output.mkdir(parents=True, exist_ok=True)
    for name in names:
        template = (ROOT / 'home-assistant' / name).read_text()
        (output / name).write_text(template.replace('remote.projector', entity))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--entity', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    render(args.entity, args.output)
    print('Rendered scripts/dashboard/voice helper. Follow docs/home-assistant.md.')
