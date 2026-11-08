"""Auditable script-grounded creative-quality gate (not a human or LLM verdict).

This module separates structural validation from likely creative failure. It never
claims to predict engagement and never invents events, footage or approvals.
"""
from __future__ import annotations
import re
from collections import Counter
from .core import all_events

IMMEDIATE_DANGER = re.compile(
    r'\b(?:attack\w*|strik\w*|punch\w*|slap\w*|shoot\w*|flames|fire|burn\w*|'
    r'explos\w*|grab\w*|drag\w*|seiz\w*|yank\w*|snatch\w*|rip\w*|tear\w*.*away|restrain\w*|handcuff\w*|shackl\w*|'
    r'bleed\w*|blood\w*|knife|sword|kill\w*|chok\w*|forced?\b|forcibly|'
    r'guards?\s+(?:rush|haul|pull|charge|take))\b', re.I)
STAKE = re.compile(
    r'\b(?:arrest\w*|death|die|dying|kill\w*|poison\w*|gallows|execution|'
    r'witchcraft|treason|stole|steal|wedding|marriage|husband|wife|marry|'
    r'duke|duchess|betray\w*|disown\w*|burn\w*|fire|attack\w*|'
    r'guards?|prison|chained|proof|impost\w*|court|threat\w*|'
    r'not your|not his|not her|no longer|falsely|framed)\b', re.I)
CLOSURE = re.compile(
    r'\b(?:all is well|finally safe|everything is fine|the danger is over|'
    r'accepts his (?:proposal|hand)|she says yes|he says yes|'
    r'they (?:embrace|kiss|depart|leave together) happily)\b', re.I)
STRONG_ENDINGS = {
    'unanswered_proposal','life_or_freedom_at_risk','relationship_or_status_at_risk',
    'arrest_or_conflict_pending','immediate_physical_danger','imminent_attack',
    'secret_discovered','danger_unresolved','unexpected_proposal_pending',
}
WEAK_ENDINGS = {'unanswered_question','unanswered_high_stakes_question',
                'rejection_or_ultimatum','future_threat_or_plan','mystery_reveal_pending'}


def assess(ep: dict, promo: dict) -> dict:
    """Assign pass/review/reject with concrete evidence and explicit limitations."""
    segs = promo['segments']
    first, last = segs[0], segs[-1]
    # Continuous episode source grounding. Stitches are intentionally separately reviewed.
    if len(segs) != 1 or first['episode'] != ep['_episode_id']:
        return {'verdict': 'review', 'reasons': ['Multi-segment continuity requires an editor'],
                'model': 'deterministic_editorial_guard_v2', 'not_human_verified': True}
    events = all_events(ep)
    start, end = first['start_seconds'], last['end_seconds']
    opening = [x for x in events if x['t0'] < start+3 and x['t1'] > start]
    tail = [x for x in events if x['t0'] < end and x['t1'] > end-5]
    near = [x for x in events if x['t0'] >= start-0.05 and x['t0'] < start+9]
    severe, concerns = [], []
    hook_type = promo['hook']['source']['type']
    kind = promo['cliffhanger']['type']
    end_source = promo['cliffhanger']['source']['content']
    strong_opening = [x for x in opening if x['type'] in {'action','dialogue'} and
                      (IMMEDIATE_DANGER.search(x.get('content','')) or STAKE.search(x.get('content','')))]
    strong_physical = any(x['type'] == 'action' and IMMEDIATE_DANGER.search(x.get('content',''))
                          for x in opening)
    if hook_type == 'camera':
        if not strong_opening:
            severe.append('Opening is only a camera/establishing description; no supported dramatic beat in first 3 seconds')
        else:
            concerns.append('Camera-led opening requires video confirmation')
    # Do not reject a genuine immediate physical hook based solely on the
    # camera-anchor score. The guard audits ALL simultaneously timed events.
    if promo['hook']['score'] < 70 and not strong_physical:
        severe.append('Weak first-three-second hook score; may not stop scrolling')
    elif promo['hook']['score'] < 80 and not strong_physical:
        concerns.append('Opening may rely on context or dialogue delivery')
    if kind == 'danger_at_scene_break':
        # A plea for mercy or a crying closeup is NOT sufficient evidence of imminent danger.
        physical = any(x['type']=='action' and IMMEDIATE_DANGER.search(x.get('content',''))
                       for x in tail)
        if not physical:
            severe.append('Scene break misclassified as a rescue cliff: no physical danger in final 5 seconds')
    if kind == 'unanswered_question':
        severe.append('Generic unanswered question is not a consequential cliffhanger')
    elif kind in WEAK_ENDINGS:
        concerns.append('Ending is weaker than immediate danger, a consequential decision or a concrete reveal')
    if kind == 'desperate_plea' and not any(IMMEDIATE_DANGER.search(x.get('content','')) for x in tail):
        concerns.append('Plea for help without clear on-screen danger at the cut')
    if kind == 'episode_end_open_loop':
        if not any(STAKE.search(x.get('content','')) for x in tail if x['type'] in {'action','dialogue'}):
            concerns.append('Episode boundary lacks explicit active stakes inside last 5 seconds')
    # A resolved payoff is not an unresolved cliffhanger just because an
    # earlier moment generated curiosity. Inspect the EXACT final five seconds.
    latest = sorted((x for x in tail if x['type'] in {'action','dialogue'}),
                    key=lambda e: (e['t1'], e['t0']))
    tail_text = ' '.join(x.get('content','') for x in latest).lower()
    resolved_identity = bool(re.search(r'\b(?:this is my son|the rightful duke|he is your duke|i am the duke|my son.*duke)\b',
                                       tail_text, re.I))
    active_threat = bool(re.search(r'\b(?:attack|attacks|strike|strikes|drag|seize|arrest|kill|execution|die|hanged|gallows|under arrest|will hang)\b',
                                   tail_text, re.I))
    if kind == 'identity_revelation_pending' and resolved_identity and not active_threat:
        severe.append('The identity is fully revealed by the end: this is a payoff, not a withheld revelation')
    completed_vow = bool(re.search(r'\b(?:i will return|i shall return|nothing breaks that|i will come back|i promise|i swear|never again|you cannot stop the healer)\b',
                                   end_source, re.I))
    if kind == 'future_threat_or_plan' and completed_vow and not active_threat:
        severe.append('Final line completes a vow or future plan; no immediate consequential outcome is suspended')
    if kind == 'episode_end_open_loop' and completed_vow and not active_threat:
        concerns.append('Episode-final vow may not be a meaningful unresolved cliffhanger')
    if any(CLOSURE.search(x.get('content','')) for x in tail if x['type'] in {'action','dialogue'}):
        concerns.append('Final seconds may already resolve the conflict')
    # A cut that jumps to an unrelated scene can be technically continuous but
    # emotionally unintelligible to a viewer encountering the story cold.
    scenes = [s for s in ep['scenes'] if float(s.get('start_seconds',0)) < end and
              float(s.get('end_seconds',0)) > start] if all('start_seconds' in s for s in ep['scenes']) else []
    if not scenes:
        from .core import seconds
        scenes = [s for s in ep['scenes'] if seconds(s['start']) < end and seconds(s['end']) > start]
    if len(scenes) >= 2:
        for left,right in zip(scenes, scenes[1:]):
            from .core import seconds
            boundary = seconds(right['start'])
            if 3 <= boundary-start <= 15 and left.get('heading','').split(' - ')[0] != right.get('heading','').split(' - ')[0]:
                concerns.append('Location changes soon after the opening; verify the promo establishes one coherent situation')
                break
    clarity = promo['scores']['standalone_clarity_proxy']
    if clarity < 68:
        concerns.append('Standalone clarity proxy is low; cold viewer may lack context')
    if any(x['type']=='dialogue' and x['content'].lstrip().startswith(('...', '“...', '"...')) for x in near[:2]):
        concerns.append('Opening may begin on an incomplete spoken thought')
    if len(opening) == 0:
        severe.append('No screenplay events support the first three seconds')
    verdict = 'reject' if severe else 'review' if concerns else 'pass'
    return {'verdict': verdict, 'reasons': severe+concerns,
            'ending_strength': 'strong' if kind in STRONG_ENDINGS else 'review_required',
            'hook_evidence_type': hook_type,
            'model': 'deterministic_editorial_guard_v2', 'not_human_verified': True}


def quality_gate(ep: dict, pool: list[dict]) -> tuple[list[dict], dict]:
    """Exclude demonstrably weak candidates; rerank pass before review candidates.

    No fixed quota per episode: episodes without credible candidates are valid results.
    """
    decisions = Counter()
    retained = []
    flagged = []
    for cand in pool:
        result = assess(ep, cand)
        decisions[result['verdict']] += 1
        if result['verdict'] == 'reject':
            if len(flagged) < 12:
                flagged.append({'id': cand['id'], 'reason': result['reasons'],
                                'start': cand['segments'][0]['start'],
                                'end': cand['segments'][0]['end']})
            continue
        new = {**cand, 'automated_editorial_gate': result}
        if result['verdict'] == 'review':
            new['quality_flags'] = list(dict.fromkeys(new['quality_flags']+result['reasons']))
            new['scores'] = {**new['scores'],
                             'pre_gate_overall': new['scores']['overall'],
                             'overall': round(new['scores']['overall'] - min(10, 2.5*len(result['reasons'])),1)}
        retained.append(new)
    retained.sort(key=lambda p: (p['automated_editorial_gate']['verdict'] != 'pass',
                                 -p['scores']['overall'], -p['scores']['standalone_clarity_proxy']))
    return retained, {'counts': dict(decisions), 'examples_rejected': flagged,
                      'scope': 'script-only quality risk rules, not observed editorial correctness'}
