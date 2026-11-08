"""Conservative *experimental* three-beat montages inside one episode.

Never treats montages as automatically approved: hard edits can create continuity
failures that cannot be validated without footage.
"""
from __future__ import annotations
from .core import all_events, timestamp, evidence
from .promo_generator import cut_has_partial_dialogue


def make_segment(epno, start, end):
    return {'episode': epno, 'start': timestamp(start), 'end': timestamp(end),
            'start_seconds': start, 'end_seconds': end,
            'duration_seconds': round(end-start, 2)}

def experimental_stitches(ep, hooks, cliffs):
    events = all_events(ep)
    number = ep['_episode_id']
    # Distinct beats: personal betrayal -> physical threat/rescue -> unanswered proposal.
    first = sorted((h for h in hooks if h['hook_type'] == 'betrayal' and h['source_event']['type'] == 'dialogue'),
                   key=lambda h: (-h['hook_score'], h['start_seconds']))
    middle = sorted((h for h in hooks if h['hook_type'] in {'urgent_command', 'abduction_or_force'} and
                     h['source_event']['type'] in {'dialogue','action'}),
                    key=lambda h: (h['start_seconds'], -h['hook_score']))
    proposal = [c for c in cliffs if c['cliffhanger_type'] == 'unanswered_proposal']
    kneels = [e for e in events if e['type'] == 'action' and
              ('one knee' in e.get('content', '').lower() or 'kneel' in e.get('content','').lower())]
    for intro in first:
        a = intro['start_seconds']
        cuts_a = [e['t0'] for e in events if e['type'] == 'camera' and 9 <= e['t0']-a <= 17]
        if not cuts_a:
            continue
        b = max(cuts_a)
        for mid in middle:
            c = mid['start_seconds']
            if c < b + 6:
                continue
            # If source action begins 0.2 sec before the line, include shot change.
            lead = [e['t0'] for e in events if e['type'] == 'camera' and c-.2 <= e['t0'] <= c]
            c = min(lead) if lead else c
            cuts_mid = [e['t0'] for e in events if e['type'] == 'camera' and 10 <= e['t0']-c <= 16]
            if not cuts_mid:
                continue
            d = max(cuts_mid)
            for cliff in proposal:
                f = cliff['end_seconds']
                final_opener = [e for e in kneels if d + 5 < e['t0'] < f - 2 and 5 <= f-e['t0'] <= 15]
                if not final_opener:
                    continue
                e = final_opener[-1]['t0']
                cuts = [(a,b), (c,d), (e,f)]
                if any(cut_has_partial_dialogue(events, x, y)[0] or cut_has_partial_dialogue(events, x, y)[1] for x, y in cuts):
                    continue
                duration = round(sum(y-x for x,y in cuts),2)
                if not 20 <= duration <= 60:
                    continue
                segments = [make_segment(number,x,y) for x,y in cuts]
                return [{'id': f'EXPERIMENTAL-STITCH-{number}', 'segments': segments,
                         'duration_seconds': duration,
                         'hook': {'text': intro['reason'], 'source': intro['source_event']},
                         'cliffhanger': {'text': cliff['cliffhanger'], 'source': cliff['evidence']},
                         'middle_evidence': evidence(mid_event) if (mid_event := next((x for x in events if x['scene_id'] == mid['source_event']['scene_id'] and x['event_index'] == mid['source_event']['event_index']), None)) else mid['source_event'],
                         'why_it_works': 'Compresses betrayal, forced removal/intervention and a surprise proposal into three consecutive story beats.',
                         'editorial_status': 'experimental_not_approved',
                         'review_flags': ['Jumps between story beats may feel discontinuous',
                                          'Check wardrobe, audio continuity and character comprehension in actual footage',
                                          'These are scripted timestamps; no editing has been performed']}]
    return []
