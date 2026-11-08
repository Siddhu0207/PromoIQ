# PromoIQ v2.2 — Implemented audit fixes

This is a complete updated copy of the original 50-episode project, not an isolated demo. It uses only the Python standard library in deterministic mode and preserves the original screenplay files and existing V1 reviewer worksheets.

## What was broken and how it was fixed

1. **R039 false negative — `src/hook_detector.py`, `src/editorial_guard.py`**. A camera shot beginning at Episode 028 01:10.50 had a synchronized action 0.30 seconds later: Catherine yanks the locket from Juliana's neck. `pass_two` now examines every event overlapping the first three seconds and can promote strong action/dialogue evidence over a camera-only anchor. The action verb vocabulary recognizes yank/snatch/rip. The quality gate also checks simultaneous opening actions instead of unconditionally rejecting a low-scored camera anchor. Regression: `test_R039_locket_yank_is_valid_hook`.
2. **R009 completed reveal — `src/editorial_guard.py`**. Episode 042 00:18.00–01:12.50 ends after the mother publicly identifies the rightful Duke. The last five seconds are now screened for a fully disclosed identity; without an active fresh danger, the proposed endpoint is rejected instead of treated as a suspended mystery. Regression: `test_R009_completed_identity_reveal_is_rejected`. A *different*, later confrontation can still be a candidate.
3. **R012 completed vow — `src/editorial_guard.py`**. Episode 024 00:33.80–01:29.80 ends with a completed declaration of intent, not a suspended action. It is now rejected when there is no immediate unresolved threat. Regression: `test_R012_completed_vow_is_rejected`.
4. **Overlapping candidate variants — `src/promo_generator.py`, `src/evaluation.py`**. Per-episode final selections suppress intervals with intersection-over-union at least 0.50; `choose_examples` also excludes overlaps across top, low and rejected review pools. This prevents near-duplicate V1 packets such as R016/R036 from reappearing together. Regression: `test_new_blind_sample_is_non_overlapping`.
5. **Out-of-clip event content — `src/evaluation.py`, `src/llm_review.py`**. Packet offsets are now clipped to zero and clip duration; events that cross a boundary have explicit `PARTIAL AT CLIP START/END` flags. Because prose cannot be precisely trimmed by timestamp, reviewers are warned that partial-event descriptions may mention unseen activity. Regression: `test_new_packets_clip_partial_events_and_keep_ratings_blank`.
6. **Early context switch — `src/editorial_guard.py`**. Location changes during the first 15 seconds are flagged for coherence review rather than automatically approved. This addresses R020 without pretending that all scene switches are invalid.

## Real rerun results

- **50/50 episodes** parsed, **3,727** source events retained, **one source timing warning** preserved (Episode 022).
- **694** timestamp-grounded hook candidates, **139** cliffhanger anchors, **75** ranked continuous promo candidates across **34** episodes.
- **42/42** local regression tests pass; all ranked clips pass structural duration, source and dialogue-cut checks.
- **40/40** new, non-overlapping blind review packets prepared in `outputs/human_evaluation_v2/`; **0 real human ratings** inserted.
- Exact runtimes vary by machine; see `outputs/execution_benchmark.json`. No paid API was used. Optional Ollama runs were **not** performed.

The smaller promo count is a consequence of tighter gating/deduplication; it **does not** prove better human-rated quality. Script-only ratings and heuristic ranks do not measure click-through, video engagement or human comprehension.

## Commands

Run from the **PromoIQ** folder:

```bash
python3 run_pipeline.py --episode 003 --force
python3 run_pipeline.py --all --auto-sample-gate --experimental-stitches --force
python3 -m unittest discover -s tests -v
python3 compare_baseline.py
python3 evaluate_quality.py prepare --set human_evaluation_v2
python3 evaluate_quality.py score --set human_evaluation_v2
```

The last command will return `awaiting_two_independent_human_reviews` until both reviewers separately enter real scores. The `--set human_evaluation` option accesses the archived V1 review files; it is not required for the updated project. Do not copy V1 scores into V2 sample IDs.

## Remaining editorial checks

Watch source footage (if available) for the first 3 seconds, cut-point dialogue, the last 5 seconds and cold-viewer context. Independently score the new packets in two sheets; compare acceptance and error modes with the fixed-first-40s baseline. The seven stitched experiments require separate visual/semantic continuity review. This project produces *promo recommendations only*, not video edits.
