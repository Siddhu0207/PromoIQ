"""Shared parsing/validation helpers for PromoIQ. Standard library only."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

VERSION = 'promoiq-v2.2.0-editorial-audit'

def seconds(value):
    if isinstance(value, (int, float)):
        return round(float(value), 3)
    parts = str(value).strip().split(':')
    if not 2 <= len(parts) <= 3:
        raise ValueError(f'Invalid timestamp: {value!r}')
    if any(not re.fullmatch(r'\d+(?:\.\d+)?', p) for p in parts):
        raise ValueError(f'Invalid timestamp: {value!r}')
    nums = [float(p) for p in parts]
    if nums[-1] >= 60 or (len(nums) == 3 and nums[-2] >= 60):
        raise ValueError(f'Invalid timestamp: {value!r}')
    return round(sum(v * 60 ** (len(nums) - i - 1) for i, v in enumerate(nums)), 3)

def timestamp(value):
    centis = int(round(float(value) * 100))
    mm, rem = divmod(centis, 6000)
    ss, cs = divmod(rem, 100)
    return f'{mm:02d}:{ss:02d}.{cs:02d}'

def ep_id(v):
    found = re.search(r'\d+', str(v))
    if not found:
        raise ValueError(f'Episode number missing from {v!r}')
    return f'{int(found.group()):03d}'

def read_episode(path):
    with Path(path).open(encoding='utf-8-sig') as f:
        obj = json.load(f)
    if not isinstance(obj, dict) or not isinstance(obj.get('scenes'), list):
        raise ValueError(f'{path} is not an analyzed episode JSON with scenes')
    if not obj['scenes']:
        raise ValueError(f'{path}: no scenes')
    obj['_episode_id'] = ep_id(obj.get('episode_number', Path(path).stem))
    return obj

def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, obj):
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(dest.suffix + '.tmp')
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(dest)

def all_events(episode):
    out = []
    for scene in episode['scenes']:
        for idx, e in enumerate(scene.get('events', [])):
            d = {**e, 'scene_id': scene['scene_id'], 'event_index': idx, 'episode': episode['_episode_id']}
            d['t0'] = seconds(e.get('start_seconds', e['start']))
            d['t1'] = seconds(e.get('end_seconds', e['end']))
            out.append(d)
    return sorted(out, key=lambda z: (z['t0'], z['t1'], z['scene_id'], z['event_index']))

def episode_bounds(ep):
    return min(seconds(s['start']) for s in ep['scenes']), max(seconds(s['end']) for s in ep['scenes'])

def validate_episode(ep):
    errors, warnings = [], []
    scenes = sorted(ep['scenes'], key=lambda s: seconds(s['start']))
    prev = None
    for s in scenes:
        start, end = seconds(s['start']), seconds(s['end'])
        sid = s.get('scene_id')
        if start >= end:
            errors.append(f'Scene {sid}: invalid interval')
        if prev is not None and start < prev - .06:
            warnings.append(f'Scene {sid}: overlaps preceding scene')
        prev = max(prev or 0, end)
        if not s.get('events'):
            warnings.append(f'Scene {sid}: no events')
        for i, e in enumerate(s.get('events', [])):
            try:
                a, b = seconds(e['start_seconds']), seconds(e['end_seconds'])
                ta, tb = seconds(e['start']), seconds(e['end'])
                if a >= b:
                    errors.append(f'Scene {sid}, event {i}: nonpositive duration')
                if abs(a - ta) > .06 or abs(b - tb) > .06:
                    warnings.append(f'Scene {sid}, event {i}: numeric and string timestamps differ')
                if a < start - .1 or b > end + .1:
                    warnings.append(f'Scene {sid}, event {i}: event outside scene interval')
            except (KeyError, ValueError, TypeError) as exc:
                errors.append(f'Scene {sid}, event {i}: {exc}')
    return {'passed': not errors, 'errors': errors, 'warnings': warnings,
            'scene_count': len(scenes), 'event_count': sum(len(s.get('events', [])) for s in scenes),
            'duration_seconds': round(episode_bounds(ep)[1] - episode_bounds(ep)[0], 2)}

def evidence(e):
    return {'episode': e['episode'], 'scene_id': e['scene_id'], 'event_index': e['event_index'],
            'type': e['type'], 'start': timestamp(e['t0']), 'end': timestamp(e['t1']),
            'content': e.get('content', '')}

def meaningful_events(events):
    return [e for e in events if e['type'] in {'dialogue', 'action', 'sound'}]

def input_files(input_dir, episode=None):
    paths = sorted(Path(input_dir).glob('*.json'))
    if episode:
        eid = ep_id(episode)
        matches = []
        for p in paths:
            m = re.search(r'episode[-_\s]*0*(\d+)(?:[-_\s.]|$)', p.stem, re.I)
            if m and ep_id(m.group(1)) == eid:
                matches.append(p)
            elif not m:
                # Also support filenames such as 003.json or screenplay_003_analysis.json.
                try:
                    if read_episode(p)['_episode_id'] == eid:
                        matches.append(p)
                except (ValueError, OSError, KeyError, TypeError):
                    pass
        return matches
    return paths
