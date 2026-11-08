"""Global ranking, editor reports, source-aware project summary and catalog."""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from statistics import mean,median
from collections import Counter
from .core import VERSION, write_json

def make_editor_report(ep, picks, qa, filename):
    lines = [f"# PromoIQ editor review — Episode {ep['_episode_id']}", '',
             f"Source: `{filename}` | Timestamp basis: annotated screenplay | Method: {VERSION}", '',
             '## Ranked promo candidates', '']
    for p in picks:
        s = p['segments'][0]
        lines += [f"### #{p['rank']} · {s['start']}–{s['end']} · {s['duration_seconds']:.2f}s",
                  f"- **Relative heuristic score:** {p['scores']['overall']}/100 (not engagement probability)",
                  f"- **Hook:** {p['hook']['text']} (scene {p['hook']['source']['scene_id']}, event {p['hook']['source']['event_index']})",
                  f"- **Cliffhanger:** {p['cliffhanger']['text']} ({p['cliffhanger']['type']})",
                  f"- **Why it works:** {p['why_it_works']}",
                  f"- **Context proxy:** {p['scores']['standalone_clarity_proxy']}/100; **human approval:** pending",
                  '']
    if not picks:
        lines += ['**No credible 20–60-second promo survived the quality gate.** This is an editorial coverage gap, not a structural parsing error.', '']
    lines += ['## Quality and failure analysis', '',
              f"Structural validation: **{'PASS' if qa['structural_pass'] else 'FAIL'}**", '']
    for x in qa['selected_promos']:
        for weakness in x.get('specific_editorial_weaknesses', []):
            lines.append(f"- **Candidate #{x['rank']} limitation:** {weakness}")
    for r in qa['where_tool_can_pick_badly']:
        lines += [f"- **{r['issue']}:** {r['explanation']}"]
    lines += ['', '## Manual acceptance checklist', '']
    lines += [f'- [ ] {x}' for x in qa['manual_editor_checklist']]
    lines += ['', '## Important scope', '',
              'No clips are edited or exported: the deliverable is in/out timestamps, story hooks, cliffhangers and editorial rankings. '
              'An Ollama-based semantic check is optional; if not used, these are deterministic heuristic results.', '']
    return '\n'.join(lines)

def output_summary(results, directory):
    allp = [p for result in results for p in result['promos']]
    # Inter-episode scores are comparable only as deterministic heuristics;
    # never claim audience-level predictiveness.
    allp.sort(key=lambda p: (-p['scores']['overall'], -p['scores']['standalone_clarity_proxy'],
                             p['segments'][0]['episode'], p['segments'][0]['start_seconds']))
    for i, p in enumerate(allp, 1):
        p['global_rank'] = i
    covered = sorted({r['episode'] for r in results})
    expected = {f'{i:03d}' for i in range(1, 51)}
    write_json(Path(directory) / 'series_coverage.json',
               {'expected_episodes': 50, 'processed_episodes': covered,
                'processed_count': len(covered),
                'missing_episodes': sorted(expected - set(covered)),
                'missing_count': len(expected - set(covered)),
                'status': 'complete' if set(covered) == expected else 'partial_dataset',
                'note': 'Only available uploaded source files were processed; no other episodes were invented.'})
    write_json(Path(directory) / 'ranked_promos.json',
               {'promos': allp, 'episodes_processed': [r['episode'] for r in results],
                'timestamp_basis': 'annotated screenplays',
                'interpretation': 'Provisional script-only ranking; editorial review required'})
    with (Path(directory) / 'ranked_promos.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, ['rank','episode','start','end','duration_seconds','score','hook','cliffhanger','why_it_works','approval'])
        writer.writeheader()
        for p in allp:
            s = p['segments'][0]
            writer.writerow({'rank': p['global_rank'], 'episode': s['episode'], 'start': s['start'],
                             'end': s['end'], 'duration_seconds': s['duration_seconds'],
                             'score': p['scores']['overall'], 'hook': p['hook']['text'],
                             'cliffhanger': p['cliffhanger']['text'],
                             'why_it_works': p['why_it_works'],
                             'approval': p['editorial_status']})
    return allp

def txt(s,maxlen=110):
    s=' '.join(str(s).replace('"','').split())
    return s if len(s)<=maxlen else s[:maxlen-1].rsplit(' ',1)[0]+'…'


def markdown_cell(s,n=96):return txt(s,n).replace('|','\\|').replace('\n',' ')


def generate(out, included_episodes=None):
    out=Path(out)
    included_episodes = set(included_episodes) if included_episodes is not None else None
    series=json.loads((out/'ranked_promos.json').read_text(encoding='utf-8'))
    allp=series['promos']
    episode_records=[]
    qafails=[]
    for i in range(1,51):
        key=f'{i:03d}'
        if included_episodes is not None and key not in included_episodes:
            continue
        epfile=out/'promotional_candidates'/f'episode_{key}_promos.json'
        if not epfile.exists(): continue
        ep=json.loads(epfile.read_text(encoding='utf-8'))
        qa=json.loads((out/'quality_reports'/f'episode_{key}_quality.json').read_text(encoding='utf-8'))
        epa=json.loads((out/'analyzed_scenes'/f'episode_{key}_stage12_audit.json').read_text(encoding='utf-8'))
        episode_records.append({'episode':key,'logline':ep['episode_logline'],
             'source_file':ep['metadata']['source_validation'].get('source_file',''),
             'duration_seconds':ep['metadata']['source_validation']['duration_seconds'],
             'scene_count':ep['metadata']['source_validation']['scene_count'],
             'event_count':ep['metadata']['source_validation']['event_count'],
             'hook_count':ep['metadata']['detected_hooks'],
             'cliffhanger_count':ep['metadata']['detected_cliffhangers'],
             'promo_count':len(ep['promos']),
             'source_warnings':ep['metadata']['source_validation']['warnings'],
             'structural_pass':qa['structural_pass'],
             'stage2_metadata':epa['stage_2_provenance'].get('stage_2_llm_scene_analysis','episode003_existing_review'),
             'stage2_findings':epa['findings']})
        for issue in qa['selected_promos']:
            if issue['errors']:qafails.append({'episode':key,'promo':issue['promo_id'],'issues':issue['errors']})
    epset={x['episode'] for x in episode_records}
    winners=[];seen=set()
    for p in allp:
        ep=p['segments'][0]['episode']
        if ep in seen:continue
        seen.add(ep);winners.append(p)
    scores=[p['scores']['overall'] for p in allp]
    hooks=Counter(p['hook']['type'] for p in allp)
    cliffs=Counter(p['cliffhanger']['type'] for p in allp)
    short=[p for p in allp if p['duration_seconds']<=25]
    long=[p for p in allp if p['duration_seconds']>=55]
    summary={'episodes_processed':len(epset),'episodes_with_shortlists':len({p['segments'][0]['episode'] for p in allp}),
             'total_ranked_continuous_promos':len(allp),
             'mean_promo_length_seconds':round(mean(p['duration_seconds'] for p in allp),2) if allp else None,
             'median_promo_length_seconds':round(median(p['duration_seconds'] for p in allp),2) if allp else None,
             'promos_20_to_25_seconds':len(short), 'promos_55_to_60_seconds':len(long),
             'heuristic_score_mean':round(mean(scores),2) if scores else None,'heuristic_score_range':[min(scores),max(scores)] if scores else None,
             'selected_hook_categories':dict(hooks),'selected_cliffhanger_categories':dict(cliffs),
             'total_source_events':sum(x['event_count'] for x in episode_records),
             'total_hook_candidates':sum(x['hook_count'] for x in episode_records),
             'total_cliffhanger_candidates':sum(x['cliffhanger_count'] for x in episode_records),
             'source_timing_warnings':[{'episode':x['episode'],'warnings':x['source_warnings']} for x in episode_records if x['source_warnings']],
             'structural_promo_errors':qafails, 'all_selected_promos_pass_structural_qa':not qafails,
             'episodes_without_credible_candidate': [x['episode'] for x in episode_records if x['promo_count']==0],
             'method':'rule-based grounded screenplay inspection, not empirical engagement prediction',
             'semantic_llm_reranking_used':any(json.loads((out/'promotional_candidates'/f"episode_{x['episode']}_promos.json").read_text())['metadata'].get('llm_clip_review')=='completed' for x in episode_records), 'video_validation_performed':False,
             'editorial_approval':'pending',
             'stage2_analysis_note':'Episode 003 has earlier LLM scene analysis; the other 49 uploaded .txt files did not include LLM scene-analysis results; no such results were fabricated.'}
    write_json(out/'project_summary.json',summary)
    write_json(out/'episode_dashboard.json',{'episodes':episode_records})
    first_003=next((p for p in allp if p['segments'][0]['episode']=='003' and
                    p['segments'][0]['start']=='01:24.00' and
                    p['segments'][0]['end']=='02:20.50'),None)
    suggestion=({'episode':'003','start':'01:24.00','end':'02:20.50',
                'reason':'A visibly arresting rescue becomes a surprise proposal, cutting before Juliana responds; stronger cold-open potential than a threat requiring backstory.',
                'algorithmic_rank_of_this_clip':first_003['global_rank'],
                'human_approved':False} if first_003 else None)
    write_json(out/'post_first_one_per_episode.json',{
                     'ranking_method':'Best candidate of each distinct episode, cross-episode editorial diversity guard',
                     'note':'Provisional and script-based; post only after video review.',
                     'script_only_editorial_first_choice':suggestion,
                     'top_20':winners[:20], 'best_from_all_50':winners})
    with (out/'best_promo_per_episode.csv').open('w',newline='',encoding='utf-8') as fh:
        wr=csv.writer(fh);wr.writerow(['post_priority','episode','start','end','duration_seconds','heuristic_score','hook','cliffhanger','why_it_works','review_status'])
        for k,p in enumerate(winners,1):
            seg=p['segments'][0]
            wr.writerow([k,seg['episode'],seg['start'],seg['end'],seg['duration_seconds'],p['scores']['overall'],p['hook']['text'],p['cliffhanger']['text'],p['why_it_works'],p['editorial_status']])
    lines=['# PromoIQ — Recommended posting order (distinct episodes)','',
           '> Algorithmic shortlist, NOT measured viewer engagement. Requires human video review of first 3 and final 5 seconds.','',
           f"**Coverage:** {summary['episodes_processed']}/50 analyzed; **timecoded events:** {summary['total_source_events']:,}; **ranked continuous promos:** {len(allp)}.",'',
           '| Post priority | Episode | Timestamp (episode-local) | Duration | Score* | Hook (script-grounded) | Cliffhanger |',
           '|---:|---:|---|---:|---:|---|---|']
    for rank,p in enumerate(winners[:20],1):
        seg=p['segments'][0]
        lines.append(f"| {rank} | {seg['episode']} | {seg['start']}–{seg['end']} | {seg['duration_seconds']:.2f}s | {p['scores']['overall']} | {markdown_cell(p['hook']['text'],66)} | {markdown_cell(p['cliffhanger']['text'],65)} |")
    lines += ['','*Scores are only relative heuristic ordering signals, not estimated CTR, virality, or watch-through rate.*',
              '', '## Script-only editorial override',
              '', '**My suggested first post is Episode 003, 01:24.00–02:20.50 (56.5s)**: an immediate physical intervention transitions to a surprise proposal, cutting before Juliana responds. Its heuristic rank may differ narrowly from the global #1; this is NOT a human-approved or performance-tested selection.',
              '', '## Why the top five might work', '']
    for k,p in enumerate(winners[:5],1):
        s=p['segments'][0]
        lines.append(f"{k}. **Episode {s['episode']} ({s['start']}–{s['end']}):** {p['why_it_works']}")
    lines += ['','## How to validate posting decisions','',
              'Have two editors watch each candidate without context, verify the hook within 3 seconds, the exact ending and comprehension, and reject overlapping or misleading openings.',
              'Then test actual view-through and conversion performance with the platform; only those outcomes can calibrate the model.', '']
    (out/'POST_FIRST_20.md').write_text('\n'.join(lines),encoding='utf-8')

    lines=['# PromoIQ — Full catalog of all continuous promos','','One line per automatically shortlisted promo. Episode timestamps are local to each episode, NOT global series runtime.','',
           '| Global rank | Episode | Start | End | Duration | Score* | Hook | Cliffhanger |',
           '|---:|---:|---|---|---:|---:|---|---|']
    for p in allp:
        seg=p['segments'][0]
        lines.append(f"| {p['global_rank']} | {seg['episode']} | {seg['start']} | {seg['end']} | {seg['duration_seconds']:.2f}s | {p['scores']['overall']} | {markdown_cell(p['hook']['text'],70)} | {markdown_cell(p['cliffhanger']['text'],60)} |")
    lines += ['','*Heuristic scores are not observed performance. Source: timecoded scripts; no video editing performed.*','']
    (out/'COMPLETE_PROMO_CATALOG.md').write_text('\n'.join(lines),encoding='utf-8')

    q=['# PromoIQ — Where the tool can pick badly','',
       'This is a source-grounded QA checklist of failure risks, not a claim that human editors watched the videos.','',
       '## Dataset-level vulnerabilities','',
       '- **No actual footage or audio**: source timestamps cannot certify frame-accurate hook boundaries or whether the action is visually intelligible.',
       '- **Heuristics are not audience behavior**: scores cannot predict watch-through, shares, or subscriptions; human/video evaluation is required.',
       '- **A question is not necessarily a cliffhanger**: cutting after an ordinary question can feel anticlimactic even if the next line answers it.',
       '- **Long dialogue-heavy promos**: strong words alone may lack motion and fail in a sound-off social feed.',
       '- **Overlapping edits**: multiple near-identical cuts from a single episode should not flood the feed.',
       '- **Spoilers and prior-episode dependence**: revealing a Duke’s identity or family connection can lose its effect without prior context.',
       '- **Source continuity ambiguities**: locations and some noble-house names vary between scripts; preserve source text and verify before editorial use.',
       '- **Multi-segment transitions**: experiment cuts spanning adjacent episodes have not been checked for wardrobe, dialogue repetition or pace.', '',
       '## Concrete catches from this project','',
       '- **Episode 003**: the initial “Look at you...” is vague; “You stole my wedding” conveys stakes immediately. A punch-first promo may still need context.',
       '- **Episode 005**: kneeling to recover the mother’s book must **not** be mislabeled a proposal; detector now requires a ring/proposal context.',
       '- **Episode 019**: ordinary references to a son are not evidence of a secret identity; the honorific “Your Grace” is a better potential hook.',
       '- **Episode 022**: one timecoded event extends beyond its declared scene, though still within the episode; source owner should verify.',
       '- **Episode 042–043**: overlapping revelation and arrest beats risk repetitive promos; global posting order favors distinct episodes.',
       '- **Episode 050**: the secret affair and discovery are inherently context-dependent; sound-off comprehension and platform policy review are needed.','',
       '## Screening checklist', '',
       '- [ ] Hook is visible/audible within first 3 seconds, no fragment or cold open without context.',
       '- [ ] Can two new viewers name the conflict from inside the clip alone?',
       '- [ ] Ending has an unresolved consequential question, not just an arbitrary cut.',
       '- [ ] Edited duration is 20–60 seconds and audio is never cut mid-word.',
       '- [ ] Final source video timecode matches the screenplay annotations.',
       '- [ ] A 2+ segment cut retains coherent chronology, speaker identities, and audio transitions.',
       '- [ ] Do not post duplicate clips from the same scene without an explicit A/B test.','']
    (out/'QUALITY_FAILURE_ANALYSIS.md').write_text('\n'.join(q),encoding='utf-8')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-dir',default='outputs')
    args=p.parse_args()
    summary=generate(args.output_dir)
    print(f"Wrote reporting catalog for {summary['episodes_processed']} episodes with {summary['total_ranked_continuous_promos']} promos")
