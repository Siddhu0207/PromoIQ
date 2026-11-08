"""Blind two-reviewer evaluation packet and honest, reproducible scoring.

No human ratings are synthesized. Outputs remain 'awaiting_review' until both
independent reviewer files contain valid judgments for the same clips.
"""
from __future__ import annotations
import csv
import json
import random
from collections import Counter
from pathlib import Path
from statistics import mean
from .core import all_events, read_episode, seconds, write_json

RUBRIC = ('hook_1_to_5', 'cliffhanger_1_to_5', 'standalone_1_to_5', 'coherence_1_to_5')
COLUMNS = ('sample_id','episode','start','end','segment_manifest','script_packet',
           *RUBRIC,'would_post_yes_no','notes')


def _rows(path):
    with open(path,newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def _write(path,header,rows):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',newline='',encoding='utf-8') as f:
        wr=csv.DictWriter(f,fieldnames=header,extrasaction='ignore')
        wr.writeheader();wr.writerows(rows)


def _clip_span(episode, segments):
    """Comparable source interval; used only for single-episode review examples."""
    return (str(episode), min(seconds(s['start']) for s in segments),
            max(seconds(s['end']) for s in segments))


def _substantial_overlap(a, b, threshold=.50):
    if a[0] != b[0]:
        return False
    inter = max(0., min(a[2], b[2]) - max(a[1], b[1]))
    union = max(a[2], b[2]) - min(a[1], b[1])
    return union > 0 and (inter / union >= threshold or
                          (abs(a[2] - b[2]) < 1.5 and inter > 5))


def choose_examples(out, top=20, low=10, rejected=10, seed=301):
    """Deterministic, non-overlapping case-control review sample.

    Remove near-duplicate story beats ACROSS all three sampling groups, not
    merely repeated IDs. Favor episode diversity but never sacrifice independence
    just to reach a target quota. This is not a population-random sample.
    """
    rng = random.Random(seed)
    ranked = json.loads((out / 'ranked_promos.json').read_text(encoding='utf-8'))['promos']
    chosen, spans, seen_ids = [], [], set()
    def add(pid, group, episode, segs):
        span = _clip_span(episode, segs)
        if pid in seen_ids or any(_substantial_overlap(span, prior) for prior in spans):
            return False
        chosen.append((pid, group, str(episode), segs))
        spans.append(span)
        seen_ids.add(pid)
        return True
    top_eps = set()
    for p in ranked:
        eid = p['segments'][0]['episode']
        if eid not in top_eps and add(p['id'], 'shortlisted_top', eid, p['segments']):
            top_eps.add(eid)
            if len(top_eps) >= top:
                break
    lower_n = 0
    for p in reversed(ranked[len(ranked)//2:]):
        eid = p['segments'][0]['episode']
        if add(p['id'], 'shortlisted_low', eid, p['segments']):
            lower_n += 1
            if lower_n >= low:
                break
    rejected_pool = []
    for i in range(1,51):
        path = out / 'quality_reports' / f'episode_{i:03d}_quality.json'
        if not path.exists():
            continue
        qa = json.loads(path.read_text(encoding='utf-8'))
        for r in qa.get('automated_editorial_gate',{}).get('examples_rejected',[]):
            rejected_pool.append((r['id'], f'{i:03d}',
                                  [{'episode':f'{i:03d}', 'start':r['start'],
                                    'end':r['end'], 'start_seconds':seconds(r['start']),
                                    'end_seconds':seconds(r['end'])}]))
    rng.shuffle(rejected_pool)
    rejected_n, rejected_episodes = 0, set()
    for pid,eid,segs in rejected_pool:
        if eid not in rejected_episodes and add(pid,'filtered_reject',eid,segs):
            rejected_episodes.add(eid)
            rejected_n += 1
            if rejected_n >= rejected:
                break
    # If diversity prevents filling the final pool, allow another episode
    # occurrence, but NEVER a near-identical timeline.
    if rejected_n < rejected:
        for pid,eid,segs in rejected_pool:
            if add(pid,'filtered_reject',eid,segs):
                rejected_n += 1
                if rejected_n >= rejected:
                    break
    return chosen

def create_packet(root, seed=301, overwrite=False, folder_name='human_evaluation'):
    root=Path(root);out=root/'outputs';folder=out/folder_name;folder.mkdir(parents=True,exist_ok=True)
    if not overwrite and (folder/'sampling_manifest_INTERNAL.json').exists():
        if not (folder/'reviewer_A.csv').exists() or not (folder/'reviewer_B.csv').exists():
            raise ValueError('Existing evaluation is incomplete. Do not overwrite reviewer work without an explicit backup.')
        return {'status':'already_prepared_no_existing_reviews_overwritten',
                'packet_path':str(folder),
                'instruction':'Use score to analyze the current reviewer sheets; use --overwrite ONLY after backing up any existing ratings.'}
    samples=choose_examples(out,seed=seed)
    entries=[];reviews=[]
    for index, (promo_id,group,episode,segs) in enumerate(samples,1):
        sid=f'R{index:03d}'
        path=root/'data'/'processed'/f'episode_{episode}.json'
        ep=read_episode(path)
        # Deliberately NO logline, predicted ranking, hook label, or quality result.
        e=all_events(ep); content=[]
        for seg in segs:
            for x in e:
                start, end = seg['start_seconds'], seg['end_seconds']
                if x['t0'] < end and x['t1'] > start:
                    lo = max(0., x['t0'] - start)
                    hi = min(end-start, x['t1'] - start)
                    cut = []
                    if x['t0'] < start: cut.append('PARTIAL AT CLIP START')
                    if x['t1'] > end: cut.append('PARTIAL AT CLIP END')
                    note = ' ['+', '.join(cut)+']' if cut else ''
                    content.append(f"[{lo:05.2f}s–{hi:05.2f}s] [{x['type'].upper()}]{note} {x['label']}: {x.get('content','')}")
        file=f'packets/{sid}.txt'
        pkt=folder/file;pkt.parent.mkdir(exist_ok=True)
        pkt.write_text(f'Clip {sid} | Episode {episode} | {segs[0]["start"]} to {segs[-1]["end"]}\n'
                       'Screenplay-only transcript; picture/audio must be independently checked.\n'
                       'First 3 seconds and final 5 seconds must be evaluated separately.\n'
                       'PARTIAL entries overlap a cut; descriptive prose may mention actions beyond the visible portion.\n'
                       + '\n'.join(content)+'\n',encoding='utf-8')
        entry={'sample_id':sid,'promo_id':promo_id,'sample_group':group,
            'episode':episode,'start':segs[0]['start'],'end':segs[-1]['end'],
            'segments':segs,'script_packet':file}
        entries.append(entry)
        reviews.append({'sample_id':sid, 'episode':episode, 'start':segs[0]['start'],
                        'end':segs[-1]['end'], 'segment_manifest':json.dumps([{'episode':x['episode'],
                        'start':x['start'],'end':x['end']} for x in segs]),
                        'script_packet':file, **{k:'' for k in RUBRIC},
                        'would_post_yes_no':'', 'notes':''})
    # Hidden manifest to prevent the reviewers seeing predicted vs rejected group.
    write_json(folder/'sampling_manifest_INTERNAL.json',{'seed':seed,'samples':entries,
           'method':'distinct-episode top ranking, low-ranked shortlist, and sampled deterministic rejects; near-duplicate IoU < 0.50 across groups',
           'sampling_limitation':'nonrandom case-control sample; not a population accuracy estimate'})
    for name in ('reviewer_A.csv','reviewer_B.csv'):
        _write(folder/name,COLUMNS,reviews)
    result={'status':'awaiting_two_independent_human_reviews',
            'samples':len(samples),'group_counts':dict(Counter(x['sample_group'] for x in entries)),
            'mean_scores':None,'acceptance_rate':None,'agreement':None,
            'claim':'No actual human evaluations have been provided; no acceptance or error rate can be estimated.'}
    write_json(folder/'evaluation_results.json',result)
    return result


def _ratings_for(path, valid_ids):
    result={};errors=[];rated=0
    for row in _rows(path):
        sid=row.get('sample_id','')
        if sid not in valid_ids:
            errors.append(f'{path.name}: unknown sample {sid}');continue
        if not any((row.get(k) or '').strip() for k in RUBRIC+('would_post_yes_no',)):
            continue
        try:
            ratings={k:int(row[k]) for k in RUBRIC}
            if any(not 1<=v<=5 for v in ratings.values()):raise ValueError('rating outside [1,5]')
            decision=row['would_post_yes_no'].strip().lower()
            if decision not in ('yes','no'):raise ValueError('would_post_yes_no must be yes/no')
            if sid in result:raise ValueError('duplicate sample row')
            result[sid]={'rubric':ratings,'post':decision=='yes','notes':row.get('notes','')}
            rated+=1
        except (KeyError,ValueError,TypeError) as ex:
            errors.append(f'{path.name} {sid}: {ex}')
    return result,errors


def evaluate(root, folder_name='human_evaluation'):
    root=Path(root);folder=root/'outputs'/folder_name
    manifest=json.loads((folder/'sampling_manifest_INTERNAL.json').read_text(encoding='utf-8'))
    sample_map={x['sample_id']:x for x in manifest['samples']}
    a,err_a=_ratings_for(folder/'reviewer_A.csv',set(sample_map))
    b,err_b=_ratings_for(folder/'reviewer_B.csv',set(sample_map))
    errors=err_a+err_b
    shared=set(a)&set(b)
    partial={'status':'awaiting_two_independent_human_reviews',
          'total_samples':len(sample_map),'reviewer_A_completed':len(a),
          'reviewer_B_completed':len(b),'paired_completed':len(shared),
          'errors':errors,'acceptance_rate':None,'agreement':None,
          'note':'All results below must be obtained from real independent reviewer input.'}
    if errors or len(shared)<len(sample_map):
        write_json(folder/'evaluation_results.json',partial)
        return partial
    yes_a=[a[s]['post'] for s in sample_map]
    yes_b=[b[s]['post'] for s in sample_map]
    observed=sum(x==y for x,y in zip(yes_a,yes_b))/len(sample_map)
    pa=sum(yes_a)/len(sample_map);pb=sum(yes_b)/len(sample_map)
    chance=pa*pb+(1-pa)*(1-pb)
    kappa=(observed-chance)/(1-chance) if chance < 1 else (1.0 if observed==1 else None)
    both_accept={s for s in sample_map if a[s]['post'] and b[s]['post'] and
                 all(a[s]['rubric'][k]>=3 and b[s]['rubric'][k]>=3 for k in RUBRIC)}
    by_group={}
    for group in sorted(set(x['sample_group'] for x in sample_map.values())):
        ids={s for s,rec in sample_map.items() if rec['sample_group']==group}
        by_group[group]={'sample_count':len(ids),'both_reviewer_accept_count':len(ids&both_accept),
                         'agreement_rate':round(sum(a[s]['post']==b[s]['post'] for s in ids)/len(ids),3),
                         'both_reviewer_accept_rate':round(len(ids&both_accept)/len(ids),3)}
    result={**partial,'status':'complete_human_rated',
       'acceptance_rate':round(len(both_accept)/len(sample_map),3),
       'agreement':{'exact_post_agreement':round(observed,3),'cohens_kappa':None if kappa is None else round(kappa,3)},
       'mean_scores':{k:round(mean((a[s]['rubric'][k]+b[s]['rubric'][k])/2 for s in sample_map),2) for k in RUBRIC},
       'group_diagnostics':by_group,
       'caution':'Stratified case-control sample: these rates DO NOT estimate all-show precision/recall or live viewer engagement.'}
    write_json(folder/'evaluation_results.json',result)
    return result
