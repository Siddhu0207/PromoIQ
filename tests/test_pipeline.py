"""Structural, reproducibility and regression tests for the real 50 source scripts."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.core import all_events, ep_id, read_episode, seconds, timestamp, validate_episode
from src.parser import parse_file
from src.scene_analyzer import analyze_episode
from src.hook_detector import pass_one, pass_two, detect_hooks
from src.promo_generator import detect_cliffhangers, assemble_promos, choose_diverse, cut_has_partial_dialogue, proposed_cliff
from src.quality_check import check_promo
from src.editorial_guard import assess, quality_gate
from src.stitch_quality import inspect
from src.evaluation import RUBRIC, evaluate, choose_examples, _substantial_overlap, _clip_span, create_packet
from unittest.mock import patch
import csv
from src.stitch_builder import experimental_stitches
from src.cross_episode_stitches import experiments
from src.audit_stage12 import audit
from run_pipeline import BUCKETS, bucket_for

class SampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT/'data'/'processed'/'episode_003.json'
        cls.ep = read_episode(cls.path)
        cls.events = all_events(cls.ep)
        cls.hooks = pass_two(cls.ep,pass_one(cls.ep))
        cls.pool,cls.stats,cls.cliffs = assemble_promos(cls.ep,cls.hooks)
        cls.selected = choose_diverse(cls.pool,4)

    def test_timecode_roundtrip(self):
        for t in ('00:08.80','01:04.50','02:25.75'):
            self.assertEqual(timestamp(seconds(t)),t)
    def test_malformed_timecode(self):
        with self.assertRaises(ValueError):seconds('00:74.00')
    def test_episode_id(self):
        self.assertEqual(ep_id('Episode 3'),'003')
    def test_episode_003_shape(self):
        v=validate_episode(self.ep)
        self.assertTrue(v['passed'])
        self.assertEqual((v['scene_count'],v['event_count']), (3,118))
    def test_invalid_event_detected(self):
        bad=json.loads(json.dumps(self.ep)); bad['scenes'][0]['events'][0]['end_seconds']=-1
        self.assertFalse(validate_episode(bad)['passed'])
    def test_sample_preserves_source_matched_prior_analysis(self):
        a=analyze_episode(self.ep)
        self.assertEqual(a['metadata']['prior_llm_analysis_scenes'],3)
        self.assertEqual(a['metadata']['scene_count'],3)
    def test_sample_scene_audit_flags_uniform_promo_scores(self):
        f=audit(self.ep)['findings']
        self.assertTrue(any(x['kind']=='uniform_scene_scores' for x in f))
    def test_hook_cache_is_reproducible(self):
        with tempfile.TemporaryDirectory() as d:
            x=detect_hooks(self.path,d,force=True)
            y=detect_hooks(self.path,d)
            self.assertEqual(x,y)
            self.assertGreater(len(x['hooks']),0)
    def test_hooks_are_at_real_events(self):
        self.assertTrue(any(h['start']=='00:08.80' and 'wedding' in h['reason'] for h in self.hooks))
    def test_known_cliffhanger_endpoints(self):
        self.assertTrue(any(c['end']=='01:24.00' for c in self.cliffs))
        self.assertTrue(any(c['end']=='02:20.50' and c['cliffhanger_type']=='unanswered_proposal' for c in self.cliffs))
    def test_episode_003_first_promo_is_a_real_window(self):
        s=self.selected[0]['segments'][0]
        self.assertEqual((s['start'],s['end']),('01:24.00','02:20.50'))
    def test_all_sample_promos_pass_qa(self):
        for promo in self.selected:self.assertEqual(check_promo(self.ep,promo),[])
    def test_no_mid_dialogue_edits(self):
        for promo in self.selected:
            seg=promo['segments'][0]
            self.assertEqual(cut_has_partial_dialogue(self.events,seg['start_seconds'],seg['end_seconds']),([],[]))
    def test_no_duplicate_sample_window(self):
        boundaries=[(p['segments'][0]['start'],p['segments'][0]['end']) for p in self.selected]
        self.assertEqual(len(boundaries),len(set(boundaries)))
    def test_sample_stitch_is_sequential(self):
        montages=experimental_stitches(self.ep,self.hooks,self.cliffs)
        self.assertGreater(len(montages),0)
        for clip in montages:
            prev=0
            for s in clip['segments']:
                self.assertGreater(s['start_seconds'],prev)
                prev=s['end_seconds']

class FullSeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=sorted((ROOT/'data'/'raw').glob('episode-*.txt'))
        cls.processed=sorted((ROOT/'data'/'processed').glob('episode_*.json'))
        cls.ranked=json.loads((ROOT/'outputs'/'ranked_promos.json').read_text())['promos']

    def test_fifty_distinct_input_episodes(self):
        self.assertEqual(len(self.sources),50)
        self.assertEqual({read_episode(p)['_episode_id'] for p in self.processed},{f'{i:03d}' for i in range(1,51)})
    def test_parse_roundtrip_preserves_original_events(self):
        count=0
        for p in self.sources:
            raw,val=parse_file(p)
            stored=read_episode(ROOT/'data'/'processed'/f"episode_{raw['_episode_id']}.json")
            for a,b in zip(raw['scenes'],stored['scenes']):self.assertEqual(a['events'],b['events'])
            count+=val['event_count']
        self.assertEqual(count,3727)
    def test_all_episode_timing_valid_and_22_warning_preserved(self):
        flags=[]
        for p in self.processed:
            ep=read_episode(p);v=validate_episode(ep)
            self.assertTrue(v['passed'])
            flags.extend([(ep['_episode_id'],w) for w in v['warnings']])
        self.assertEqual(len(flags),1)
        self.assertEqual(flags[0][0],'022')
    def test_scene_reports_exist_for_every_episode(self):
        files=sorted((ROOT/'outputs'/'analyzed_scenes').glob('episode_*_analysis.json'))
        self.assertEqual(len(files),50)
        for p in files:
            obj=json.loads(p.read_text())
            self.assertEqual(obj['metadata']['scene_count'],len(obj['scenes']))
    def test_non_proposal_kneeling_not_mislabeled(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_005.json')
        events=all_events(ep)
        samples=[e for e in events if e['type']=='action' and 'kneels down beside juliana' in e['content'].lower()]
        self.assertTrue(samples)
        for e in samples:
            c=proposed_cliff(e,events)
            self.assertFalse(c and 'proposal' in c[0])
    def test_promo_count_and_fifty_episode_coverage(self):
        self.assertGreater(len(self.ranked),40)
        self.assertLess(len(self.ranked),160)
        self.assertGreaterEqual(len({p['segments'][0]['episode'] for p in self.ranked}),30)
        self.assertEqual(json.loads((ROOT/'outputs'/'project_summary.json').read_text())['episodes_processed'],50)
    def test_every_promo_structurally_valid(self):
        for p in self.ranked:
            s=p['segments'][0]
            ep=read_episode(ROOT/'data'/'processed'/f"episode_{s['episode']}.json")
            self.assertEqual(check_promo(ep,p),[],p['id'])
            self.assertTrue(20<=p['duration_seconds']<=60)
    def test_duration_buckets_cover_all_candidates_without_overlap(self):
        counts=[]
        for bucket in BUCKETS:
            total=0
            for p in (ROOT/'outputs'/'promotional_candidates'/bucket).glob('episode_*.json'):
                record=json.loads(p.read_text())
                for item in record['promos']:
                    self.assertEqual(bucket_for(item['duration_seconds']),bucket)
                total+=len(record['promos'])
            counts.append(total)
        self.assertEqual(sum(counts),len(self.ranked))
    def test_quality_reports_exist_for_fifty(self):
        files=list((ROOT/'outputs'/'quality_reports').glob('episode_*_quality.json'))
        self.assertEqual(len(files),50)
        self.assertTrue(all(json.loads(p.read_text())['structural_pass'] for p in files))
        self.assertEqual(sum(bool(json.loads(p.read_text())['has_editorial_candidate']) for p in files), len({x['segments'][0]['episode'] for x in self.ranked}))
    def test_cross_episode_experiments_are_chronological(self):
        r=experiments(self.processed)
        self.assertGreaterEqual(len(r['experiments']),1)
        for p in r['experiments']:
            a,b=p['segments']
            self.assertEqual(int(b['episode']),int(a['episode'])+1)
            self.assertTrue(20<=p['duration_seconds']<=60)
    def test_no_false_human_or_video_approval(self):
        summary=json.loads((ROOT/'outputs'/'project_summary.json').read_text())
        self.assertFalse(summary['video_validation_performed'])
        self.assertEqual(summary['editorial_approval'],'pending')
    def test_known_047_plea_not_mislabeled_as_rescue(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_047.json')
        cliffs=detect_cliffhangers(ep)
        self.assertFalse(any(c['cliffhanger_type']=='danger_at_scene_break' and
                             c['end']=='01:23.50' for c in cliffs))
    def test_camera_candle_hook_is_filtered(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_047.json')
        hooks=pass_two(ep,pass_one(ep))
        pool,_,_=assemble_promos(ep,hooks,250)
        _,report=quality_gate(ep,pool)
        bad=[x for x in report['examples_rejected'] if x['start']=='00:00.00']
        self.assertTrue(bad)
        self.assertTrue(any('camera/establishing' in t or 'Weak first-three-second' in t for t in bad[0]['reason']))
    def test_source_gated_003_first_promo_survives(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_003.json')
        hooks=pass_two(ep,pass_one(ep))
        pool,_,_=assemble_promos(ep,hooks,250)
        kept,report=quality_gate(ep,pool)
        self.assertTrue(any(p['segments'][0]['start']=='01:24.00' and p['segments'][0]['end']=='02:20.50' for p in kept))
        self.assertGreater(report['counts']['reject'],0)
    def test_R039_locket_yank_is_valid_hook(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_028.json')
        hooks=pass_two(ep,pass_one(ep))
        pool,_,_=assemble_promos(ep,hooks,1000)
        matched=[p for p in pool if p['segments'][0]['start']=='01:10.50' and
                 p['segments'][0]['end']=='02:08.80']
        self.assertTrue(matched, 'R039 window must be reconstructible')
        p=matched[0]
        self.assertEqual(p['hook']['source']['type'],'action')
        self.assertIn('yanks',p['hook']['text'].lower())
        self.assertEqual(assess(ep,p)['verdict'],'pass')

    def test_R009_completed_identity_reveal_is_rejected(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_042.json')
        pool,_,_=assemble_promos(ep,pass_two(ep,pass_one(ep)),1000)
        matched=[p for p in pool if p['segments'][0]['start']=='00:18.00' and
                 p['segments'][0]['end']=='01:12.50']
        self.assertTrue(matched)
        result=assess(ep,matched[0])
        self.assertEqual(result['verdict'],'reject')
        self.assertTrue(any('fully revealed' in x for x in result['reasons']))

    def test_R012_completed_vow_is_rejected(self):
        ep=read_episode(ROOT/'data'/'processed'/'episode_024.json')
        pool,_,_=assemble_promos(ep,pass_two(ep,pass_one(ep)),1000)
        matched=[p for p in pool if p['segments'][0]['start']=='00:33.80' and
                 p['segments'][0]['end']=='01:29.80']
        self.assertTrue(matched)
        self.assertEqual(assess(ep,matched[0])['verdict'],'reject')

    def test_new_blind_sample_is_non_overlapping(self):
        samples=choose_examples(ROOT/'outputs')
        self.assertEqual(len(samples),40)
        self.assertEqual(len({p[0] for p in samples}),40)
        spans=[_clip_span(ep,segs) for _,_,ep,segs in samples]
        for i,a in enumerate(spans):
            for b in spans[i+1:]:
                self.assertFalse(_substantial_overlap(a,b),f'overlap {a} {b}')

    def test_new_packets_clip_partial_events_and_keep_ratings_blank(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'data').mkdir()
            (root/'data'/'processed').symlink_to(ROOT/'data'/'processed',target_is_directory=True)
            (root/'outputs').mkdir()
            (root/'outputs'/'ranked_promos.json').write_bytes((ROOT/'outputs'/'ranked_promos.json').read_bytes())
            (root/'outputs'/'quality_reports').symlink_to(ROOT/'outputs'/'quality_reports',target_is_directory=True)
            result=create_packet(root,folder_name='human_evaluation_v2')
            self.assertEqual(result['samples'],40)
            f=root/'outputs'/'human_evaluation_v2'
            for packet in (f/'packets').glob('R*.txt'):
                import re
                for m in re.finditer(r'\[(-?\d+\.\d+)s–(-?\d+\.\d+)s\]',packet.read_text()):
                    self.assertGreaterEqual(float(m.group(1)),0)
                    self.assertGreaterEqual(float(m.group(2)),float(m.group(1)))
            with (f/'reviewer_A.csv').open(newline='') as fd:
                rows=list(csv.DictReader(fd))
            self.assertEqual(len(rows),40)
            self.assertTrue(all(not x['would_post_yes_no'] and not x['hook_1_to_5'] for x in rows))

    def test_human_packet_has_no_fake_ratings(self):
        r=json.loads((ROOT/'outputs'/'human_evaluation'/'evaluation_results.json').read_text())
        self.assertEqual(r['status'],'awaiting_two_independent_human_reviews')
        self.assertIsNone(r['acceptance_rate'])
        self.assertEqual(r['paired_completed'],0)
    def test_baseline_has_explicit_scope_and_measured_counts(self):
        r=json.loads((ROOT/'outputs'/'baseline_comparison.json').read_text())
        self.assertEqual(r['same_episode_denominator'],50)
        self.assertIn('not a human',r['scope'])
        self.assertEqual(r['outcomes']['tool_best']['episodes_with_candidate'], len({x['segments'][0]['episode'] for x in self.ranked}))
    def test_benchmark_is_measured_not_an_estimate(self):
        r=json.loads((ROOT/'outputs'/'execution_benchmark.json').read_text())
        self.assertEqual(r['episodes_processed'],50)
        self.assertGreater(r['total_runtime_seconds'],0)
        self.assertEqual(r['semantic_model_calls_performed'],0)
    def test_llm_rubric_mock_only(self):
        from src.llm_review import review_one
        ep=read_episode(ROOT/'data'/'processed'/'episode_003.json')
        p=next(x for x in self.ranked if x['segments'][0]['episode']=='003')
        response={k:4 for k in ('first_3_second_hook','unresolved_cliffhanger', 'standalone_clarity','narrative_coherence')}
        response.update(verdict='review',weakness='Needs visual confirmation')
        with patch('src.llm_review.local_ollama',return_value=response) as mock:
            r=review_one(ep,p,'fake-for-test')
        self.assertEqual(r['rubric_score'],80)
        self.assertFalse(r['human_approval'])
        self.assertTrue(mock.called)
    def test_all_stitched_candidates_hard_validated(self):
        obj=json.loads((ROOT/'outputs'/'promotional_candidates'/'stitched_experiments'/'ranked_stitched_review_queue.json').read_text())
        self.assertEqual(obj['total'],7)
        self.assertEqual(obj['structurally_valid'],7)
        self.assertTrue(all(not p['structural_evaluation']['problems'] for p in obj['candidates']))
        self.assertEqual(obj['editorial_approval'],'pending_all')
    def test_one_episode_without_candidate_does_not_overwrite_global(self):
        before=(ROOT/'outputs'/'ranked_promos.json').read_bytes()
        with tempfile.TemporaryDirectory() as temp:
            proc=subprocess.run([sys.executable,str(ROOT/'run_pipeline.py'),'--episode','001','--skip-parse',
                            '--output-dir',temp],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            single=json.loads((Path(temp)/'project_summary.json').read_text())
            self.assertEqual(single['episodes_processed'],1)
            self.assertEqual(single['total_ranked_continuous_promos'],0)
        self.assertEqual(before,(ROOT/'outputs'/'ranked_promos.json').read_bytes())
    def test_human_scoring_works_on_fake_test_fixture_only(self):
        from src.evaluation import evaluate, RUBRIC
        with tempfile.TemporaryDirectory() as temp:
            f=Path(temp)/'outputs'/'human_evaluation';f.mkdir(parents=True)
            manifest={'samples':[{'sample_id':'R001','sample_group':'shortlisted_top'},
                                {'sample_id':'R002','sample_group':'filtered_reject'}]}
            (f/'sampling_manifest_INTERNAL.json').write_text(json.dumps(manifest))
            head=['sample_id',*RUBRIC,'would_post_yes_no','notes']
            for name in ('reviewer_A.csv','reviewer_B.csv'):
                with (f/name).open('w',newline='') as out:
                    w=csv.DictWriter(out,fieldnames=head);w.writeheader()
                    w.writerow({'sample_id':'R001',**{k:5 for k in RUBRIC},'would_post_yes_no':'yes'})
                    w.writerow({'sample_id':'R002',**{k:1 for k in RUBRIC},'would_post_yes_no':'no'})
            result=evaluate(temp)
            self.assertEqual(result['status'],'complete_human_rated')
            self.assertEqual(result['acceptance_rate'],.5)
            self.assertEqual(result['agreement']['cohens_kappa'],1)
    def test_requires_explicit_batch_gate(self):
        proc=subprocess.run([sys.executable,str(ROOT/'run_pipeline.py'),'--all','--skip-parse'],
                            cwd=ROOT,capture_output=True,text=True)
        self.assertNotEqual(proc.returncode,0)
        self.assertIn('--auto-sample-gate',proc.stderr)

if __name__=='__main__':unittest.main()
