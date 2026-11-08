"""Conservative experiments spanning consecutive episodes.
An episode-to-episode continuity note is REQUIRED. Results are deliberately
unranked until an editor assesses causal clarity, wardrobe and sound continuity.
"""
from __future__ import annotations
import re
from pathlib import Path
from .core import read_episode,all_events,episode_bounds,evidence,seconds,timestamp,write_json
from .promo_generator import detect_cliffhangers,cut_has_partial_dialogue


def experiments(paths, out_file=None, max_results=15):
    eps={read_episode(p)['_episode_id']:read_episode(p) for p in paths}
    from .hook_detector import pass_one,pass_two
    all_results=[]
    for num in range(1,50):
        a,b=eps.get(f'{num:03d}'),eps.get(f'{num+1:03d}')
        if not a or not b:continue
        note=b.get('continuity_notes','').lower()
        if not re.search(r'episode\s*0*'+str(num)+r'\b', note):continue
        ah=pass_two(a,pass_one(a));be=detect_cliffhangers(b)
        a0,a1=episode_bounds(a);b0,b1=episode_bounds(b)
        ae=all_events(a);bf=all_events(b)
        candidates=[]
        for h in ah:
            s=h['start_seconds']; da=a1-s
            if not 8 <= da <= 26 or h['hook_score']<77 or cut_has_partial_dialogue(ae,s,a1)!=([],[]):continue
            for c in be:
                e=c['end_seconds'];db=e-b0
                if not 10 <= db <= 35 or c['cliffhanger_score'] < 83 or not 20 <= da+db <=60:continue
                if cut_has_partial_dialogue(bf,b0,e)!=([],[]):continue
                # Avoid clips that start with a vague fragment even if regex found a hit.
                if h['source_event']['type']=='camera':continue
                score=round(.54*h['hook_score']+.46*c['cliffhanger_score']-max(0,da+db-50)*.15,1)
                candidates.append((score,h,c,s,e,da,db))
        if not candidates:continue
        candidates.sort(key=lambda x:-x[0])
        score,h,c,s,e,da,db=candidates[0]
        results={
            'id':f'EXPERIMENTAL-CROSS-{num:03d}-{num+1:03d}',
            'status':'experimental_editor_review_required',
            'ranked_for_posting':False,
            'episode_pair':[f'{num:03d}',f'{num+1:03d}'],
            'segments':[{'episode':f'{num:03d}','start':timestamp(s),'end':timestamp(a1),'start_seconds':s,'end_seconds':a1,'duration_seconds':round(da,2)},
                        {'episode':f'{num+1:03d}','start':timestamp(b0),'end':timestamp(e),'start_seconds':b0,'end_seconds':e,'duration_seconds':round(db,2)}],
            'duration_seconds':round(da+db,2),
            'hook':{'type':h['hook_type'],'text':h['reason'],'source':h['source_event']},
            'cliffhanger':{'type':c['cliffhanger_type'],'text':c['cliffhanger'],'source':c['evidence']},
            'heuristic_priority':score,
            'why_it_might_work':'Begins near an episode-ending source hook, then continues chronologically into the next episode and cuts before another unresolved beat.',
            'continuity_note':b['continuity_notes'],
            'review_flags':['Not fully context-tested: adjacent episodes can repeat dialogue or have time jumps.',
                            'Check audiovisual transitions and character identities in video before posting.',
                            'Do not treat heuristic priority as a verified commercial score.']
        }
        all_results.append(results)
    all_results.sort(key=lambda c:(-c['heuristic_priority'],c['episode_pair']))
    obj={'status':'experimental_not_approved','experiments':all_results[:max_results],
         'candidate_pair_count':len(all_results),'unranked_with_continuous_promos':True,
         'method':'2 chronological segments from adjacent episodes with explicit continuity notes'}
    if out_file:write_json(out_file,obj)
    return obj

if __name__=='__main__':
    r=experiments(sorted(Path('data/processed').glob('episode_*.json')),'outputs/experimental_cross_episode_promos.json')
    print(f"Generated {len(r['experiments'])} cross-episode experimental candidates")
