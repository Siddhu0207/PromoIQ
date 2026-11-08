"""PromoIQ: parsed scripts -> scene evidence -> hooks -> ranked teaser candidates.

Run from any directory: python /path/to/PromoIQ/run_pipeline.py --episode 003
The deterministic run requires Python 3.10+ but no third-party packages.
"""
from __future__ import annotations
import argparse
import time
from collections import Counter
from pathlib import Path
from src.core import VERSION, input_files, read_episode, validate_episode, write_json
from src.parser import parse_sources
from src.scene_analyzer import analyze_episode
from src.hook_detector import detect_hooks
from src.promo_generator import assemble_promos, choose_diverse
from src.quality_check import analyze
from src.audit_stage12 import audit
from src.reporting import make_editor_report, output_summary, generate
from src.stitch_builder import experimental_stitches
from src.cross_episode_stitches import experiments as cross_experiments
from src.llm_review import review_candidates
from src.editorial_guard import quality_gate
from src.stitch_quality import rank_all

ROOT = Path(__file__).resolve().parent
BUCKETS = ('short_teasers', 'standard_teasers', 'extended_promos')

def bucket_for(duration):
    """Duration partition: [20,30), [30,45), [45,60]."""
    duration = float(duration)
    if not 20 <= duration <= 60:
        raise ValueError(f'Promo length outside assignment 20–60 seconds: {duration}')
    return 'short_teasers' if duration < 30 else 'standard_teasers' if duration < 45 else 'extended_promos'

def process_one(path, out, top_n=4, force=False, semantic_review=False,
                llm_promos=False, model='llama3.1:8b', timeout=300, stitches=False, gate=True, llm_limit=3):
    path, out = Path(path), Path(out)
    ep = read_episode(path)
    eid = ep['_episode_id']
    validity = validate_episode(ep)
    if not validity['passed']:
        raise ValueError(f'Episode {eid}: {validity["errors"]}')

    analyzed = analyze_episode(ep, out/'analyzed_scenes'/f'episode_{eid}_analysis.json')
    stage12 = audit(ep)
    write_json(out/'analyzed_scenes'/f'episode_{eid}_stage12_audit.json', stage12)
    found = detect_hooks(path, out/'detected_hooks', force=force,
                         semantic_review=semantic_review, model=model, timeout=timeout)
    pool, stats, cliffs = assemble_promos(ep, found['hooks'], top_pool=250)
    gate_report = {'status': 'disabled_for_baseline'}
    if gate:
        pool, gate_report = quality_gate(ep, pool)
    reviewed_count = min(llm_limit, len(pool)) if llm_promos else 0
    if llm_promos:
        pool = review_candidates(ep, pool, model, timeout=timeout, limit=llm_limit)
    picks = choose_diverse(pool, n=top_n)
    write_json(out/'detected_hooks'/f'episode_{eid}_cliffhangers.json',
               {'episode':eid,'cliffhangers':cliffs,'source':'timestamped screenplay, not picture-verified'})
    qa = analyze(ep, picks, pool, stats)
    qa['automated_editorial_gate'] = gate_report
    write_json(out/'quality_reports'/f'episode_{eid}_quality.json', qa)
    if not qa['structural_pass']:
        raise ValueError(f'Episode {eid}: shortlisted promos failed structural QA')

    result = {
        'episode':eid, 'episode_logline':ep.get('logline',''),
        'timestamp_basis':'annotated screenplay, not actual video timing',
        'score_interpretation':'relative heuristic score, not audience-performance prediction',
        'promos':picks,
        'metadata':{'method':VERSION,'source_file':ep.get('source_file'),
                    'selected_count':len(picks), 'candidate_status':'shortlisted' if picks else 'no_credible_candidate_review_needed', 'candidate_pool_count':len(pool),
                    'detected_hooks':len(found['hooks']),'detected_cliffhangers':len(cliffs),
                    'scene_count':len(analyzed['scenes']), 'source_validation':validity,
                    'editorial_approval':'pending',
                    'llm_clip_review':'completed' if llm_promos else 'not_requested',
                    'llm_clip_requests':reviewed_count,
                    'llm_hook_requests_upper_bound':len(found['hooks']) if semantic_review else 0,
                    'automated_quality_gate': gate_report}
    }
    write_json(out/'promotional_candidates'/f'episode_{eid}_promos.json', result)
    for bucket in BUCKETS:
        subset = [p for p in picks if bucket_for(p['duration_seconds']) == bucket]
        write_json(out/'promotional_candidates'/bucket/f'episode_{eid}_{bucket}.json',
                   {'episode':eid,'category':bucket,'promos':subset,
                    'count':len(subset), 'editorial_approval':'pending',
                    'selection':'shortlisted continuous clips only'})
    (out/'quality_reports'/f'episode_{eid}_editor_review.md').write_text(
        make_editor_report(ep, picks, qa, path.name), encoding='utf-8')
    if stitches:
        special = experimental_stitches(ep, found['hooks'], cliffs)
        write_json(out/'promotional_candidates'/'stitched_experiments'/f'episode_{eid}_stitched_experiments.json',
                   {'episode':eid,'promos':special,'status':'experimental_unranked_human_review_required'})
    return result, qa

def main(argv=None):
    p = argparse.ArgumentParser(description='PromoIQ: timecoded screenplay to 20–60s ranked promo windows')
    p.add_argument('--episode', default='003', help='Single episode number, e.g. 003')
    p.add_argument('--all', action='store_true', help='Process the full 50-episode dataset')
    p.add_argument('--auto-sample-gate', action='store_true',
                   help='For --all: proceed after automatic Episode 003 structural QA (not human sign-off)')
    p.add_argument('--approve-sample', action='store_true',
                   help='For --all: caller states a human reviewed sample; the program cannot verify approval')
    p.add_argument('--source-dir', type=Path, default=ROOT/'data'/'raw')
    p.add_argument('--input-dir', type=Path, default=ROOT/'data'/'processed')
    p.add_argument('--output-dir', type=Path, default=None,
                   help='Default: outputs/ for full batch; outputs/sample_runs/ for a single episode')
    p.add_argument('--skip-parse', action='store_true', help='Use preprocessed JSON without reparsing text')
    p.add_argument('--top-per-episode', type=int, default=4)
    p.add_argument('--semantic-review', action='store_true', help='Optional local Ollama check of detected hooks')
    p.add_argument('--llm-review-promos', action='store_true', help='Optional local Ollama critique of promo candidates')
    p.add_argument('--no-quality-gate', action='store_true', help='Disable rule-based editorial gate (baseline / ablation only)')
    p.add_argument('--model', default='llama3.1:8b')
    p.add_argument('--llm-review-limit',type=int,default=3,help='Cap optional Ollama clip reviews per episode (default 3)')
    p.add_argument('--timeout', type=int, default=300)
    p.add_argument('--experimental-stitches', action='store_true', help='Generate separate non-approved montage experiments')
    p.add_argument('--force', action='store_true', help='Recompute detected hooks even if a cached result exists')
    a = p.parse_args(argv)
    if a.output_dir is None:
        a.output_dir = ROOT/'outputs' if a.all else ROOT/'outputs'/'sample_runs'
    wall_start = time.perf_counter()
    parse_elapsed = 0.0
    episode_durations = {}
    if not (1 <= a.top_per_episode <= 30):p.error('--top-per-episode must be between 1 and 30')
    if a.timeout <= 0:p.error('--timeout must be positive')
    if not 1<=a.llm_review_limit<=30:p.error('--llm-review-limit must be 1–30')
    if a.all and not (a.auto_sample_gate or a.approve_sample):
        p.error('Full-series processing requires --auto-sample-gate or --approve-sample')
    if not a.skip_parse:
        parse_start = time.perf_counter()
        try:
            report = parse_sources(a.source_dir, a.input_dir, episode=None if a.all else a.episode,
                                   overwrite=True, legacy_dir=ROOT/'data'/'legacy')
        except Exception as exc:
            p.error(f'Screenplay parsing failed: {exc}')
        parse_elapsed = round(time.perf_counter()-parse_start, 3)
        write_json(a.output_dir/'source_parsing_report.json', report)
        print(f"Parsed {report['count']} screenplays and {report['total_events']} timestamped events")
    available = input_files(a.input_dir, None if a.all else a.episode)
    if not available:p.error('No processed JSON episodes matched')
    if a.all and len(available) != 50:
        p.error(f'Expected 50 processed episodes, found {len(available)}')

    results = []
    if a.all:
        samples = input_files(a.input_dir,'003')
        if len(samples) != 1:p.error('Episode 003 sample is missing or duplicated')
        ep_start = time.perf_counter()
        sample, sample_qa = process_one(samples[0],a.output_dir,a.top_per_episode,force=a.force,
                          semantic_review=a.semantic_review,llm_promos=a.llm_review_promos,
                          model=a.model,timeout=a.timeout,stitches=a.experimental_stitches,gate=not a.no_quality_gate,llm_limit=a.llm_review_limit)
        episode_durations['003'] = round(time.perf_counter()-ep_start, 3)
        if not sample_qa['structural_pass']:
            p.error('Episode 003 sample gate failed')
        results.append(sample)
        print('Episode 003: PASS (automated structural gate; human review still required)')

    errors = []
    for path in available:
        if a.all and path.name == 'episode_003.json':continue
        try:
            ep_start = time.perf_counter()
            result, quality = process_one(path,a.output_dir,a.top_per_episode,force=a.force,
                              semantic_review=a.semantic_review,llm_promos=a.llm_review_promos,
                              model=a.model,timeout=a.timeout,stitches=a.experimental_stitches,gate=not a.no_quality_gate,llm_limit=a.llm_review_limit)
            episode_durations[result['episode']] = round(time.perf_counter()-ep_start, 3)
            results.append(result)
            print(f"Episode {result['episode']}: {result['metadata']['detected_hooks']} hooks, "
                  f"{result['metadata']['detected_cliffhangers']} cliffs, "
                  f"{len(result['promos'])} promos, QA PASS (editorial coverage may be empty)")
        except Exception as exc:
            errors.append(f'{path.name}: {exc}')
            print(f'FAILED {path.name}: {exc}')
    if errors:
        raise SystemExit('Not all episodes passed: ' + '; '.join(errors))
    if not results:p.error('No successful episodes')
    global_promos = output_summary(results, a.output_dir)
    summary = generate(a.output_dir, included_episodes={r['episode'] for r in results})
    if a.all and a.experimental_stitches:
        cross_experiments(available,a.output_dir/'promotional_candidates'/'stitched_experiments'/'cross_episode_promos.json')
        rank_all(ROOT)
    benchmark = {'run_type':'full_series' if a.all else 'single_episode',
        'episodes_processed':len(results), 'total_runtime_seconds':round(time.perf_counter()-wall_start,3),
        'parsing_seconds':parse_elapsed, 'per_episode_seconds':episode_durations,
        'semantic_model_calls_performed':sum(r['metadata'].get('llm_clip_requests',0) for r in results) if a.llm_review_promos and not a.semantic_review else ('not_exact_if_hook_review_is_cached' if a.semantic_review else 0),
        'ollama_clip_request_limit_per_episode':a.llm_review_limit,
        'paid_api_calls':0, 'known_paid_api_spend_usd':0,
        'inference_spend_note': 'No paid API is used. Local Ollama hardware/electricity costs are not measured.' if (a.semantic_review or a.llm_review_promos) else 'Rule-based mode, no LLM inference.',
        'human_review_time': 'not_measured', 'timing_scope':'wall-clock processing on this runtime, not a general service SLA',
        'quality_gate_enabled':not a.no_quality_gate, 'ollama_requested':a.semantic_review or a.llm_review_promos}
    write_json(a.output_dir/'execution_benchmark.json',benchmark)
    print(f"Benchmark: {benchmark['total_runtime_seconds']} seconds (wall clock)")
    print(f"Complete: {len(results)} episodes, {len(global_promos)} promos, "
          f"{summary['total_hook_candidates']} hooks, {summary['total_cliffhanger_candidates']} cliffs")
    print(f'Ranked CSV: {a.output_dir / "ranked_promos.csv"}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
