"""Inspect the quality of user-provided stage-1 event structure and stage-2 metadata.

Flags suspicious metadata for editor review; never silently rewrites source facts.
"""
from __future__ import annotations
import re
from .core import validate_episode

def audit(ep):
    structure = validate_episode(ep)
    findings = []
    scene_scores = [(s.get('scene_id'),s.get('analysis',{}).get('promotional_potential')) for s in ep['scenes']]
    if len(scene_scores)>1 and all(v is not None for _,v in scene_scores) and len({str(n) for _,n in scene_scores})==1:
        findings.append({'severity':'important', 'kind':'uniform_scene_scores',
                        'observation':f'Each scene shares promotional_potential={scene_scores[0][1]}.',
                        'action':'Do not use identical scene-wide numbers for clip ranking; use grounded event-level evidence.'})
    if not any(s.get('analysis') for s in ep['scenes']):
        findings.append({'severity':'informational','kind':'stage_2_scene_analysis_not_supplied',
                         'observation':'This episode was supplied as timecoded screenplay text, without LLM scene-analysis metadata.',
                         'action':'Run optional LLM audit locally if required; event-grounded hook selection works without it.'})
    for scene in ep['scenes']:
        a = scene.get('analysis',{})
        scene_contents = ' '.join(e.get('content','') for e in scene.get('events',[])).lower()
        summary = str(a.get('scene_summary',''))
        if 'banish' in summary.lower() and not re.search(r'banish|remove her|you leave|leave where|discarded', scene_contents):
            findings.append({'severity':'review', 'kind':'possible_scene_summary_leakage',
                             'scene_id':scene.get('scene_id'),
                             'observation':'Scene summary claims banishment although its own annotated events do not contain a removal order.',
                             'action':'Check the source screenplay; avoid treating story-wide context as an event in this scene.'})
        for rel in a.get('relationships',[]):
            desc = str(rel.get('description',''))
            if re.search(r'mother.daughter|father.daughter|sisterly|siblings?',desc,re.I):
                char1,char2 = rel.get('character_1',''),rel.get('character_2','')
                if not re.search(r'\b(mother|daughter|sister|father)\b',scene_contents,re.I):
                    findings.append({'severity':'review', 'kind':'relationship_not_explicit_in_scene',
                                     'scene_id':scene.get('scene_id'),
                                     'observation':f'Relationship for {char1} / {char2} is labeled "{desc}" but not explicitly established in these scene events.',
                                     'action':'Verify from earlier episodes or character bible; do not assert this relation from current scene alone.'})
    return {'episode':ep['_episode_id'], 'stage_1_event_timing':structure,
            'stage_2_provenance':ep.get('analysis_metadata',{}),
            'findings':findings,
            'assessment':'Event-level input is usable for the promo pipeline' if structure['passed'] else 'Fix structural errors before using input',
            'note':'A successful Ollama scene-analysis job is not evidence that every narrative annotation is accurate.'}
