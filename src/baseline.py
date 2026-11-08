"""Simple ablation: compare evidence coverage with fixed first-40-second clips.

Metrics are structural proxies, NOT human judgments or measured watch-through.
"""
from __future__ import annotations
from pathlib import Path
from .core import input_files, read_episode, episode_bounds, write_json, timestamp, all_events
from .hook_detector import pass_one, pass_two
from .promo_generator import detect_cliffhangers, cut_has_partial_dialogue
import json


def calculate(root):
    root=Path(root)
    processed=root/'data'/'processed'; output=root/'outputs'
    ranked=json.loads((output/'ranked_promos.json').read_text(encoding='utf-8'))['promos']
    best={}
    for p in ranked:
        best.setdefault(p['segments'][0]['episode'],p)
    rows=[]
    for ep_path in input_files(processed):
        ep=read_episode(ep_path);ei=ep['_episode_id']
        lo,hi=episode_bounds(ep)
        hooks=pass_two(ep,pass_one(ep));cliffs=detect_cliffhangers(ep)
        def grade(start,end):
            h=any(start-.05<=x['start_seconds']<=start+3 and x['hook_score']>=80 for x in hooks)
            c=any(abs(end-x['end_seconds'])<=.55 and x['cliffhanger_score']>=83 for x in cliffs)
            no_cut=cut_has_partial_dialogue(all_events(ep),start,end)==([],[])
            return {'immediate_hook_evidence':h,'cliffhanger_endpoint_evidence':c,
                    'no_partial_dialogue':no_cut,'all_three':h and c and no_cut}
        base_end=min(lo+40,hi)
        base=grade(lo,base_end)
        selected=best.get(ei)
        chosen=grade(selected['segments'][0]['start_seconds'],selected['segments'][0]['end_seconds']) if selected else None
        rows.append({'episode':ei, 'fixed_baseline':{'start':timestamp(lo),'end':timestamp(base_end),**base},
                     'tool_best':({'id':selected['id'],'start':selected['segments'][0]['start'],
                                   'end':selected['segments'][0]['end'],**chosen} if chosen else None)})
    outcomes={}
    for method in ('fixed_baseline','tool_best'):
        vals=[r[method] for r in rows if r[method] is not None]
        outcomes[method]={'episodes_with_candidate':len(vals),
           **{k:sum(x[k] for x in vals) for k in ('immediate_hook_evidence','cliffhanger_endpoint_evidence','no_partial_dialogue','all_three')}}
    result={'method':'first 40s of each episode vs one top-ranked promo per episode',
            'scope':'automatic timecode/event-evidence indicators only; not a human-rated quality or accuracy measurement',
            'same_episode_denominator':len(rows), 'outcomes':outcomes,'episodes':rows,
            'selection_bias_warning':'The tool explicitly optimizes hook/end evidence; improvement on these proxy metrics is expected and does not validate storytelling quality.'}
    write_json(output/'baseline_comparison.json',result)
    return result
