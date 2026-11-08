"""Convert the supplied 50 timecoded text screenplays into validated episode JSON.
No inference about missing text or AI-generated scene analysis is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from .core import seconds, timestamp, validate_episode, write_json

SCENE = re.compile(r'^SCENE\s+0*(\d+)\s*$',re.M|re.I)
EVENT_HEADER = re.compile(r'^\*\*(.+?):\*\*\s*$',re.I)
EVENT_TIME = re.compile(r'^Start:\s*\(([^)]+)\)\s*\|\s*End:\s*\(([^)]+)\)\s*$',re.I)


def field(text, name):
    m = re.search(r'^' + re.escape(name) + r':\s*(.*)$', text, re.I|re.M)
    if not m:
        raise ValueError('Missing metadata field ' + name)
    return m.group(1).strip()


def parse_scene(text, scene_number, ep, file):
    sid=int(scene_number)
    heading=field(text,'Scene heading')
    st=field(text,'Scene start'); en=field(text,'Scene end')
    lines=text.splitlines()
    events=[]
    index=0
    while index < len(lines):
        m=EVENT_HEADER.match(lines[index].strip())
        if not m:
            index+=1
            continue
        label=m.group(1).strip()
        j=index+1
        while j<len(lines) and not lines[j].strip(): j+=1
        if j>=len(lines) or not EVENT_TIME.match(lines[j].strip()):
            raise ValueError(f'{file}: scene {sid}, label {label}, missing event times')
        tm=EVENT_TIME.match(lines[j].strip())
        parts=[]
        k=j+1
        while k<len(lines):
            if EVENT_HEADER.match(lines[k].strip()): break
            if lines[k].strip() and not lines[k].strip().startswith('--- SCRIPT'):
                parts.append(lines[k].strip())
            k+=1
        content=' '.join(parts).strip()
        if not content: raise ValueError(f'{file}: scene {sid}, missing content for {label}')
        low=label.upper()
        typ=('camera' if low=='CAMERA' else 'action' if low=='ACTION' else
             'sound' if low in {'SOUND FX','SOUND','SFX','MUSIC'} else 'dialogue')
        a,b=seconds(tm.group(1)),seconds(tm.group(2))
        events.append({'type':typ, 'label':label,'start':timestamp(a),'end':timestamp(b),
                       'start_seconds':a,'end_seconds':b,'content':content})
        index=k
    if not events: raise ValueError(f'{file}: scene {sid} has no events')
    return {'scene_id':sid,'heading':heading, 'start':st,'end':en,'events':events}


def parse_file(path):
    path=Path(path)
    raw=path.read_text(encoding='utf-8-sig')
    ep=field(raw,'Episode number')
    num_match=re.search(r'\bEpisode\s+(\d+)\b',ep,re.I)
    if not num_match: raise ValueError('Episode label missing numeric ID')
    eid=f'{int(num_match.group(1)):03d}'
    file_match=re.search(r'episode-(\d+)',path.name,re.I)
    if file_match and f'{int(file_match.group(1)):03d}' != eid:
        raise ValueError(f'Episode mismatch filename={file_match.group(1)} internal={eid}')
    scenes=list(SCENE.finditer(raw))
    if not scenes: raise ValueError(f'No SCENE headings in {path}')
    parsed=[parse_scene(raw[m.end():scenes[i+1].start() if i+1<len(scenes) else len(raw)],m.group(1),eid,path.name) for i,m in enumerate(scenes)]
    result={'episode_number':ep,'logline':field(raw,'Episode logline'),
            'continuity_notes':field(raw,'Continuity notes'), 'scenes':parsed,
            'source_file':path.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source_format':'user-supplied timecoded screenplay text',
            'analysis_metadata':{'stage_2_llm_scene_analysis':'not_provided',
                                 'note':'No invented LLM scene metadata; event-level evidence drives promo selection.'}}
    result['_episode_id']=eid
    val=validate_episode(result)
    if not val['passed']:
        raise ValueError(f'{path.name}: invalid parsed timings: {val["errors"]}')
    return result,val



def incorporate_preserved_analysis(ep, prior_path):
    """Use prior Episode 003 LLM annotations only if all event text/times agree."""
    prior_path = Path(prior_path)
    if not prior_path.is_file():
        return ep
    previous = json.loads(prior_path.read_text(encoding='utf-8'))
    matches = len(previous.get('scenes', [])) == len(ep['scenes']) and all(
        len(old['events']) == len(new['events']) and all(
            x['content'] == y['content'] and
            abs(x['start_seconds'] - y['start_seconds']) < .01 and
            abs(x['end_seconds'] - y['end_seconds']) < .01
            for x, y in zip(old['events'], new['events']))
        for new, old in zip(ep['scenes'], previous['scenes']))
    if not matches:
        raise ValueError(f'Prior scene analysis disagrees with original screenplay: {prior_path}')
    for scene, old in zip(ep['scenes'], previous['scenes']):
        if 'analysis' in old:
            scene['analysis'] = old['analysis']
    ep['analysis_metadata'] = {
        **previous.get('analysis_metadata', {}),
        'provenance': 'previous Episode 003 analysis, event/timecode matched to source',
        'editorial_accuracy_reviewed': False,
    }
    return ep

def parse_sources(source_dir, out_dir, episode=None, overwrite=True, legacy_dir=None):
    source_dir, out_dir = Path(source_dir), Path(out_dir)
    files = sorted(source_dir.glob('episode-*.txt'))
    if episode:
        wanted = f'{int(re.search(r"\d+", str(episode)).group()):03d}'
        files = [p for p in files if re.search(r'episode-0*' + str(int(wanted)) + r'(?=-)', p.name)]
    if not files:
        raise FileNotFoundError(f'No screenplay .txt files matched in {source_dir}')
    prior_dir = Path(legacy_dir) if legacy_dir else source_dir.parent / 'legacy'
    summary = []
    for path in files:
        ep, validation = parse_file(path)
        ep = incorporate_preserved_analysis(ep, prior_dir/f'episode_{ep["_episode_id"]}_prior_analysis.json')
        target = out_dir/f'episode_{ep["_episode_id"]}.json'
        if target.exists() and not overwrite:
            raise FileExistsError(f'{target} exists; pass --overwrite')
        ep.pop('_episode_id', None)
        write_json(target, ep)
        summary.append({'episode':int(re.search(r'\d+',ep['episode_number']).group()),
                        'file':path.name, 'scenes':validation['scene_count'],
                        'events':validation['event_count'],
                        'duration_seconds':validation['duration_seconds'],
                        'warnings':validation['warnings'], 'validated':validation['passed']})
    return {'episodes':summary,'count':len(summary),
            'total_events':sum(e['events'] for e in summary),
            'all_valid':all(e['validated'] for e in summary),
            'note':'Source warnings retained; no fabricated timing fixes.'}

def main():
    p = argparse.ArgumentParser(description='Parse timestamped episode screenplays')
    p.add_argument('--source-dir', default='data/raw')
    p.add_argument('--out-dir', default='data/processed')
    p.add_argument('--episode', default=None)
    p.add_argument('--overwrite', action='store_true')
    a = p.parse_args()
    report = parse_sources(a.source_dir, a.out_dir, a.episode, a.overwrite)
    write_json(Path('outputs')/'source_parsing_report.json', report)
    print(f"Parsed {report['count']} episodes, {report['total_events']} source events")

if __name__=='__main__': main()
