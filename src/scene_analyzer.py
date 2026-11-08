"""Grounded scene summaries and narrative signals from timestamped screenplay events.

Deterministic stage 2: no claim that an external LLM reviewed these files.
Episode 003 includes a separately marked legacy LLM result for comparison.
"""
from __future__ import annotations
from collections import Counter
import re
from .core import ep_id, seconds, timestamp, write_json
from .hook_detector import classify_hook

TOPICS = {
    'betrayal_and_humiliation': r'\b(?:stol\w*|betray\w*|shame|humiliat\w*|disown\w*|abandon\w*|worthless)\b',
    'danger_and_threat': r'\b(?:arrest\w*|kill\w*|burn\w*|attac\w*|bleed\w*|chok\w*|execution|prison\w*|gallows|guard\w*)\b',
    'love_and_commitment': r'\b(?:marry|marriage|bride|wedding|wife|husband|kiss\w*|lov\w*|propos\w*)\b',
    'identity_and_power': r'\b(?:duke|duchess|heir|crown|king|lord|royal|title|identity|imposter|impostor)\b',
    'medical_mystery': r'\b(?:poison\w*|arsenic|herb\w*|remed\w*|fever|heal\w*|antidote|sick\w*)\b',
    'secret_and_deception': r'\b(?:secret\w*|spy|hidden|conspir\w*|lie|lying|deceiv\w*|framed|forg\w*)\b',
}

def analyze_scene(scene):
    events = scene.get('events', [])
    participants = []
    for e in events:
        if e.get('type') == 'dialogue':
            name = re.sub(r'\s*\([^)]*\)', '', e.get('label','')).strip().upper()
            if name and name not in participants:
                participants.append(name)
    all_text = ' '.join(e.get('content','') for e in events)
    topics = [name for name, pattern in TOPICS.items() if re.search(pattern, all_text, re.I)]
    meaningful = [(i,e) for i,e in enumerate(events) if e.get('type') in ('dialogue','action')]
    evidence = []
    for idx,e in meaningful:
        classification = classify_hook(e)
        if not classification or classification['score'] < 65:
            continue
        evidence.append({'event_index':idx,'start':e['start'],'end':e['end'],
                         'event_type':e['type'],'text':e['content'],
                         'hook_type':classification['category'], 'initial_hook_score':classification['score']})
    evidence.sort(key=lambda x:(-x['initial_hook_score'],seconds(x['start'])))
    first = meaningful[0][1]['content'] if meaningful else ''
    last = meaningful[-1][1]['content'] if meaningful else ''
    record = {
        'scene_id':scene['scene_id'], 'heading':scene.get('heading',''),
        'start':scene['start'],'end':scene['end'],
        'duration_seconds':round(seconds(scene['end'])-seconds(scene['start']),2),
        'event_counts':dict(Counter(e['type'] for e in events)),
        'speakers_in_dialogue':participants,
        'detected_themes':topics,
        'scene_progression_evidence':{'opening_event':first,'closing_event':last},
        'possible_hook_events':evidence[:5],
        'interpretation_status':'deterministic screenplay signals, not independent story comprehension',
    }
    if 'analysis' in scene:
        record['prior_llm_scene_analysis'] = scene['analysis']
        record['prior_llm_analysis_status'] = 'preserved from previously supplied Episode 003; requires editorial checking'
    return record

def analyze_episode(ep, out_file=None):
    number = ep.get('_episode_id') or ep_id(ep['episode_number'])
    scenes = [analyze_scene(scene) for scene in ep['scenes']]
    result = {'episode':number,'logline_from_source':ep.get('logline',''),
              'continuity_notes_from_source':ep.get('continuity_notes',''),
              'method':'deterministic evidence indexing; prior LLM analysis included only when supplied',
              'source_sha256':ep.get('source_sha256'),
              'scenes':scenes,
              'metadata':{'scene_count':len(scenes),
                          'prior_llm_analysis_scenes':sum('prior_llm_scene_analysis' in s for s in scenes),
                          'timestamps':'source screenplay, not video verified'}}
    if out_file is not None:write_json(out_file,result)
    return result
