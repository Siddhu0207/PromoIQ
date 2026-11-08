"""Objective structural QA and explicit editorial failure modes."""
from __future__ import annotations
import re
from .core import all_events, episode_bounds, seconds
from .promo_generator import cut_has_partial_dialogue, interval_iou

def check_promo(ep, promo):
    bounds = episode_bounds(ep)
    events = all_events(ep)
    issues = []
    segs = promo['segments']
    if not segs:
        issues.append('No segments')
    if len(segs) != 1:
        # Multi-segment support has a defined output schema but isn't auto-generated.
        issues.append('This runner only validates continuous single-episode clips')
    for s in segs:
        if s['episode'] != ep['_episode_id']:
            issues.append('Segment episode does not match source')
        if s['start_seconds'] < bounds[0] or s['end_seconds'] > bounds[1]:
            issues.append('Segment extends beyond episode')
        if s['start_seconds'] >= s['end_seconds']:
            issues.append('Invalid segment duration')
        start_speech, end_speech = cut_has_partial_dialogue(events, s['start_seconds'], s['end_seconds'])
        if start_speech or end_speech:
            issues.append('Cut intersects spoken dialogue')
    duration = sum(s['duration_seconds'] for s in segs)
    if not 20 <= duration <= 60:
        issues.append('Promo must be 20–60 seconds long')
    hook_source = promo['hook']['source']
    first = segs[0]
    if not first['start_seconds'] - .05 <= seconds(hook_source['start']) <= first['start_seconds'] + 3.0:
        issues.append('No evidence of a hook in the first 3 seconds')
    # Cliff evidence may start at the cut if it describes the next escalation being withheld.
    final = segs[-1]
    cliff_e = promo['cliffhanger']['source']
    if not final['start_seconds'] <= seconds(cliff_e['start']) <= final['end_seconds'] + .05:
        issues.append('Cliffhanger evidence is not adjacent to the promo end')
    return issues

def editorial_risks(ep, selected, all_candidates, stats):
    risks = [
        {'severity': 'important', 'issue': 'No video was provided',
         'explanation': 'The screenplay timestamp boundaries are not verified frame-accurate edits; video/image/audio may change hook strength.'},
        {'severity': 'important', 'issue': 'Rule-based scoring is not audience testing',
         'explanation': 'Heuristic values rank alternatives in this screenplay; they are not probabilities or predicted CTR.'},
        {'severity': 'important', 'issue': 'Context inference may be unreliable',
         'explanation': 'Character relations and backstory are approximated from lines; an editor should check each clip without the logline.'},
        {'severity': 'medium', 'issue': 'Open-ended dialogue may be a weak cliff',
         'explanation': 'An unanswered question is not always compelling. Prefer imminent danger or an unanswered shocking proposal.'},
        {'severity': 'medium', 'issue': 'Repeated scenes can dominate a series ranking',
         'explanation': 'Use overlap suppression and manually review top promos for genuinely different audiences and story beats.'},
    ]
    analyses = [s.get('analysis', {}).get('promotional_potential') for s in ep['scenes']]
    if len(analyses) >= 2 and all(x is not None for x in analyses) and len(set(map(str, analyses))) == 1:
        risks.append({'severity': 'important', 'issue': 'Scene-level scores cannot discriminate',
                      'explanation': f'All {len(analyses)} scenes have promotional_potential={analyses[0]}; do not use these scores for ranking.'})
    if any(x['hook']['type'] == 'violent_confrontation' and x['segments'][0]['start_seconds'] > 0 for x in selected):
        risks.append({'severity': 'medium', 'issue': 'Action-first opens without explicit backstory',
                      'explanation': 'An isolated punch can be visually arresting but the victim, rescuer and motive may become clear only later in the clip.'})
    for i, a in enumerate(selected):
        for b in selected[i+1:]:
            if interval_iou(a,b) >= .5 or (abs(a['segments'][0]['end_seconds']-b['segments'][0]['end_seconds']) < 1.0):
                risks.append({'severity': 'medium', 'issue': 'Shortlisted alternative shares story beats',
                              'explanation': f"Candidates {a.get('rank')} and {b.get('rank')} substantially overlap or share a cliffhanger; avoid posting both without a distinct creative test."})
                break
    if ep['_episode_id'] == '003':
        risks.append({'severity': 'medium', 'issue': 'Specific rejected Episode 003 opening',
                      'explanation': 'The initial “Look at you...” at 00:02.10 is a vague insult, while “You stole my wedding” at 00:08.80 immediately establishes the stakes.'})
    if any(x['hook']['source']['type'] == 'camera' for x in selected):
        risks.append({'severity': 'medium', 'issue': 'Visual-only hook requires footage check',
                      'explanation': 'A screenplay camera description can exaggerate the impact or hide motion timing.'})
    return risks

def analyze(ep, selected, all_candidates, rejection_stats):
    failures = []
    for c in selected:
        issues = check_promo(ep, c)
        weaknesses = []
        if c['hook']['type'] == 'violent_confrontation':
            weaknesses.append('The opening impact is strong, but the victim/motive may not be understood instantly.')
        if c['cliffhanger']['type'] == 'imminent_attack':
            weaknesses.append('The cut is just before an action beat; verify the anticipation is visible before the cut.')
        if c['duration_seconds'] >= 55:
            weaknesses.append('Near the 60-second maximum; check whether the middle drags in actual playback.')
        if c['hook']['type'] == 'humiliation':
            weaknesses.append('The insult alone may not tell a new viewer who the speaker and victim are.')
        failures.append({'promo_id': c['id'], 'rank': c.get('rank'), 'structurally_valid': not issues,
                         'errors': issues, 'review_flags': c['quality_flags'],
                         'specific_editorial_weaknesses': weaknesses})
    # No credible clip is an editorial coverage gap, NOT a timestamp validation failure.
    # Keep the episode in the dataset and report the gap rather than inventing a promo.
    return {'episode': ep['_episode_id'], 'structural_pass': not any(f['errors'] for f in failures),
            'has_editorial_candidate': bool(selected),
            'coverage_status': 'shortlisted' if selected else 'no_credible_candidate_review_needed',
            'selected_count': len(selected), 'candidate_pool_count': len(all_candidates),
            'rejection_statistics': rejection_stats,
            'selected_promos': failures,
            'where_tool_can_pick_badly': editorial_risks(ep, selected, all_candidates, rejection_stats),
            'manual_editor_checklist': [
                'Watch the first 3 seconds with the sound on AND off; is the hook immediate?',
                'Watch without knowing the preceding episodes; can you explain who wants what?',
                'Play the last 5 seconds; is the payoff withheld after a meaningful unresolved beat?',
                'Confirm start/end to the frame in final footage; avoid cutting mid-word.',
                'Reject repetitive variants and clips that reveal the full payoff.'
            ]}
