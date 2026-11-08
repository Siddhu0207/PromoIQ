"""Source-grounded validation and separate ranking for OPTIONAL multi-segment promos.

Stitched clips are never mixed into post-ready continuous rankings without video
review, because continuity cannot be certified from script annotations alone.
"""
from __future__ import annotations
import csv
import json
from pathlib import Path
from .core import read_episode, all_events, episode_bounds, seconds, write_json
from .promo_generator import cut_has_partial_dialogue


def inspect(stitch, episodes):
    problems=[]
    segments=stitch['segments']
    if not 2<=len(segments)<=5: problems.append('Expected 2–5 ordered segments')
    elapsed=0.0
    prev=None
    for seg in segments:
        ep=episodes.get(seg['episode'])
        if not ep:
            problems.append(f"Missing episode {seg['episode']}")
            continue
        start,end=seg['start_seconds'],seg['end_seconds']
        lo,hi=episode_bounds(ep)
        if not (lo<=start<end<=hi): problems.append('Segment crosses episode bounds')
        if prev:
            if int(seg['episode'])<int(prev['episode']):problems.append('Episode order reversed')
            if seg['episode']==prev['episode'] and start < prev['end_seconds']-.05:
                problems.append('Segments overlap or reverse within episode')
        if cut_has_partial_dialogue(all_events(ep),start,end)!=([],[]):
            problems.append('Segment cuts through dialogue')
        if abs(seconds(seg['start'])-start)>.051 or abs(seconds(seg['end'])-end)>.051:
            problems.append('Timestamp strings and numeric seconds disagree')
        elapsed+=end-start;prev=seg
    if not 20<=elapsed<=60:problems.append('Combined segments exceed 20–60-second constraint')
    if abs(elapsed-stitch['duration_seconds'])>.12:problems.append('Inconsistent total duration')
    h=stitch.get('hook',{}).get('source')
    c=stitch.get('cliffhanger',{}).get('source')
    if not h or h.get('episode') != segments[0]['episode'] or not (
       segments[0]['start_seconds']-.05 <= seconds(h['start']) <= segments[0]['start_seconds']+3):
        problems.append('Hook is not evidenced inside the first 3 seconds')
    if not c or c.get('episode') != segments[-1]['episode'] or not (
       segments[-1]['end_seconds']-6 <= seconds(c['start']) <= segments[-1]['end_seconds']+.05):
        problems.append('Cliffhanger evidence is not within the last 6 seconds')
    return {'structural_pass': not problems, 'problems':problems,
            'human_continuity_review':'required', 'video_validation':False}


def rank_all(root):
    root=Path(root);path=root/'outputs'/'promotional_candidates'/'stitched_experiments'
    episodes={f'{i:03d}':read_episode(root/'data'/'processed'/f'episode_{i:03d}.json') for i in range(1,51)}
    candidates=[]
    cross=path/'cross_episode_promos.json'
    if cross.exists():
        candidates.extend(json.loads(cross.read_text(encoding='utf-8')).get('experiments',[]))
    for file in sorted(path.glob('episode_*_stitched_experiments.json')):
        candidates.extend(json.loads(file.read_text(encoding='utf-8')).get('promos',[]))
    rows=[]
    for p in candidates:
        result=inspect(p,episodes)
        item={**p,'structural_evaluation':result,'posting_status':'requires_editorial_continuity_approval'}
        # A small, explicit, non-predictive prioritization for experimental review.
        item['review_priority_score']=float(p.get('heuristic_priority',80))
        rows.append(item)
    rows.sort(key=lambda x:(not x['structural_evaluation']['structural_pass'],-x['review_priority_score'],x['id']))
    for i,r in enumerate(rows,1):r['review_priority']=i
    write_json(path/'ranked_stitched_review_queue.json',{
        'candidates':rows, 'total':len(rows),
        'structurally_valid':sum(x['structural_evaluation']['structural_pass'] for x in rows),
        'editorial_approval':'pending_all',
        'note':'Separate queue; not added to continuous clip ranking without human video review'})
    with (path/'ranked_stitched_review_queue.csv').open('w',newline='',encoding='utf-8') as fh:
        wr=csv.writer(fh);wr.writerow(['review_priority','id','ordered_segments','duration_seconds',
            'hook','cliffhanger','why_it_might_work','structural_pass','problems','approval'])
        for c in rows:
            ss=' + '.join(f"E{s['episode']} {s['start']}–{s['end']}" for s in c['segments'])
            wr.writerow([c['review_priority'],c['id'],ss,c['duration_seconds'],
                        c['hook'].get('text'),c['cliffhanger'].get('text'),
                        c.get('why_it_might_work',c.get('why_it_works','')),
                        c['structural_evaluation']['structural_pass'],
                        '; '.join(c['structural_evaluation']['problems']),
                        c['posting_status']])
    return rows
