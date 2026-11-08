# PromoIQ — screenplay-to-promo discovery prototype

**Kuku AI Generalist assignment:** Find 20–60-second promo clips in a microdrama screenplay. Return the ordered `episode / start / end` segments, first-three-second hook, unresolved ending, one grounded sentence explaining the selection, global posting rank, and failure analysis. **No editing, overlays, or music.**

This release processes the **50 supplied screenplays** end-to-end and separates **hard timestamp validity**, **automated creative-risk screening**, **optional local LLM review**, and **human editorial acceptance**. Only the first two were executed to produce the bundled rankings. Scores are **relative heuristic priorities, not measured viewer engagement**.

## Project structure

```text
PromoIQ/
├── data/
│   ├── raw/                          50 supplied screenplay .txt files
│   ├── processed/                    50 parsed JSONs with event timestamps
│   └── legacy/                       preserved Episode 003 prior analysis
├── outputs/
│   ├── analyzed_scenes/              event-grounded scene findings + source audit
│   ├── detected_hooks/               per-episode hooks and cliffhanger anchors
│   ├── promotional_candidates/
│   │   ├── short_teasers/            20–under 30 seconds
│   │   ├── standard_teasers/         30–under 45 seconds
│   │   ├── extended_promos/          45–60 seconds
│   │   └── stitched_experiments/     separately ranked, unapproved 2–3-segment ideas
│   ├── quality_reports/              QA, rejected examples, editor notes per episode
│   ├── human_evaluation/             archived V1 packets, retained unchanged
│   ├── human_evaluation_v2/          NEW overlap-free 40-packet evaluation sheets
│   ├── ranked_promos.csv             validated, quality-screened continuous promo ranking
│   ├── best_promo_per_episode.csv     one clip for each episode with credible candidates
│   ├── POST_FIRST_20.md              suggested posting order, distinct episodes
│   ├── QUALITY_FAILURE_ANALYSIS.md
│   ├── execution_benchmark.json      measured run time and cost scope
│   ├── baseline_comparison.json      measurable structural-proxy baseline
│   ├── project_summary.json
│   └── ...                            complete per-episode JSON and catalogs
├── src/
│   ├── parser.py                     source text → structured timecoded events
│   ├── scene_analyzer.py             evidence-grounded scene analysis
│   ├── hook_detector.py              two-pass hook candidate detection
│   ├── promo_generator.py            cliffhangers / 20–60s windows / score
│   ├── editorial_guard.py            NEW: stricter script-only quality gate
│   ├── llm_review.py                 NEW: optional local semantic rubric reviewer
│   ├── evaluation.py                 NEW: blind reviewer sampling + scoring
│   ├── baseline.py                   NEW: simple benchmark baseline
│   ├── stitch_quality.py             NEW: validate and prioritize stitched candidates
│   ├── core.py, quality_check.py, reporting.py, audit_stage12.py
│   └── stitch_builder.py, cross_episode_stitches.py, __init__.py
├── tests/test_pipeline.py           automated reproducibility + regression tests
├── run_pipeline.py                  main entry point
├── evaluate_quality.py              prepare or score real human reviews
├── compare_baseline.py              fixed-40-second comparison
├── SUBMISSION.md                    concise assignment framing and results
└── requirements.txt                 Python 3.10+ standard library only
```

## Run it

Open a terminal inside the extracted `PromoIQ/` folder. Python **3.10+** is sufficient, without `pip install` or network access.

```bash
# 1. Process / inspect sample Episode 003
python3 run_pipeline.py --episode 003 --force
# Saves into outputs/sample_runs/ so full-series outputs are not overwritten

# 2. Process all 50 scripts, with sample structural gate and stitched ideas
python3 run_pipeline.py --all --auto-sample-gate --experimental-stitches --force

# 3. Run regression tests
python3 -m unittest discover -s tests -v

# 4. Recalculate fixed-duration baseline evidence comparison
python3 compare_baseline.py

# 5. Prepare blind human review worksheets (idempotent)
python3 evaluate_quality.py prepare --set human_evaluation_v2

# 6. AFTER two editors independently complete both V2 sheets, calculate agreement
python3 evaluate_quality.py score --set human_evaluation_v2
```

Single-episode commands default to `outputs/sample_runs/` rather than replacing the 50-episode ranking. Add `--output-dir <folder>` to override.

`human_evaluation_v2` is the NEW sample. The older `human_evaluation` is preserved only for historical comparison; its sample IDs are not interchangeable with V2. The CLI defaults to V2. `--set human_evaluation` explicitly selects the original sheets.

`--auto-sample-gate` means **automated structural validation of Episode 003**, NOT human approval. Use `--approve-sample` only if you have actually reviewed the video. Running `evaluate_quality.py prepare` again does not overwrite existing sheets. `--overwrite` is available only if you deliberately wish to replace them after backup.

**Optional local Ollama semantic reviewer:** On your own machine, start Ollama and download `llama3.1:8b`, then:

```bash
python3 run_pipeline.py --episode 003 --llm-review-promos --llm-review-limit 3 --force
```

This asks a skeptical LLM to judge the **full in-clip dialogue, actions, camera and sound descriptions**, including the first 3 and last 5 seconds, on hook, cliffhanger, comprehension and coherence. It can reject/re-rank clips but cannot change timestamps. Model responses are schema checked. Full-series mode caps clip-review requests to **3 per episode by default (at most 150 for 50 episodes)**. Adding `--semantic-review` separately reviews hooks and may require many more calls. Ollama **was unavailable in the processing environment**, so the delivered full-series outputs **do not claim an LLM review was performed**. Local hardware, inference latency and energy expense were not measured.

## Measured deterministic run on the 50 supplied scripts

| Measurement | Result |
|---|---:|
| Episodes parsed successfully | 50 / 50 |
| Source timecoded events | 3,727 |
| Detected hook anchors | 694 |
| Candidate cliffhanger endpoints (stricter rules) | 139 |
| 20–60s continuous promos in final ranking | 75 |
| Episodes with credible shortlisted clips | 34 |
| Episodes intentionally left without a qualifying pick | 16 |
| Structural errors in selected clips | 0 |
| Stitched clips passing structural review | 7 / 7 (NOT editorially approved) |
| Regression tests | 42 passed |

The stricter quality gate reviewed 469 rule-based candidates before diversity filtering: **142 pass, 201 review, 126 reject**. The 75 final promos include **45 automated-pass** and **30 review-needed** clips. The 16 empty episodes are **not processing failures**; a tool should not fabricate a compelling promo where its evidence is weak.

The benchmark (`outputs/execution_benchmark.json`) records actual elapsed time for this small, text-only, 50-episode dataset. No paid model API requests were made. This is **not** a benchmark for processing video or for Ollama inference and does **not** include editor time. The single-series input comprises approximately **102.7 minutes of annotated episode runtime**.

## Evidence comparison (not quality ground truth)

A deliberately simplistic baseline always takes the **first 40 seconds** of each episode. With identical event-evidence criteria:

| Script-only indicator | Fixed first 40s (50) | PromoIQ best available (34) |
|---|---:|---:|
| Hook evidence in the first three seconds | 10 | 34 |
| Annotated cliffhanger endpoint at the cut | 4 | 29 |
| No cut crossing dialogue | 27 | 34 |
| All three indicators simultaneously | 1 | 29 |

The comparison is **selection-biased** because PromoIQ optimizes these structural proxies. It is useful as a reproducible implementation check, **not** proof of audience engagement or a genuine human-quality win. See `outputs/baseline_comparison.json`.

## Human evaluation — ready, NOT yet rated

`outputs/human_evaluation_v2/` contains **40 newly deduplicated blind screenplay-only review packets**: 20 top picks from distinct episodes, 10 lower-ranked picks, and 10 automatically rejected examples. Independent reviewers fill `reviewer_A.csv` and `reviewer_B.csv` with 1–5 ratings for **immediate hook**, **genuine unresolved cliff**, **standalone comprehension**, and **coherence**, plus a yes/no posting recommendation and notes. The scoring program calculates consensus, mean scores and Cohen's kappa, and keeps numbers `null` until **both sheets** are completed. To verify *actual footage* quality, reviewers must watch the corresponding video; screenplay review is only a proxy. See `outputs/human_evaluation_v2/REVIEWER_INSTRUCTIONS.md`. The previous `outputs/human_evaluation/` folder is preserved; its overlapping sample IDs must not be mixed with the new set.

## What still needs real-world evidence

The prototype cannot certify that screenplay timecodes equal rendered-video frames, that sound-off audiences understand the clip, or that a good heuristic score predicts watch-through/subscription. Some clips end on a merely intriguing question or begin with confusing context. The gate now checks simultaneous physical action (Episode 028 locket yank), rejects completed identity reveals (Episode 042) and closing vows (Episode 024), and catches an Episode 047 false rescue-cliffhanger, but **false positives and false negatives remain possible**. The 7 stitched ideas pass timecode/order/dialogue checks yet still require review for audio, pacing, visual continuity and narrative comprehension.

**Recommended first submission demo:** Inspect `outputs/promotional_candidates/episode_003_promos.json`: **Episode 003 · 01:24.00–02:20.50 (56.50s)** begins with a guard being struck, develops an unexpected proposal, and ends **before Juliana answers**. The algorithm's overall #1 remains Episode 028; Episode 003 is an explained script-only editorial preference, not a fabricated measured result.

## Deliverables

- `outputs/ranked_promos.csv` — every qualifying continuous promo, source episode, start/end, evidence-backed hook/cliff and reason.
- `outputs/POST_FIRST_20.md` — recommended posting sequence with one clip per distinct episode and reasons.
- `outputs/promotional_candidates/stitched_experiments/ranked_stitched_review_queue.csv` — **ordered timestamp segments** for experimental multi-episode and three-beat ideas.
- `outputs/quality_reports/` and `outputs/QUALITY_FAILURE_ANALYSIS.md` — where the tool picks badly and where editorial reviews are pending.
- `outputs/human_evaluation_v2/` — updated non-overlapping quality study awaiting independent humans, not made-up ratings.
- `outputs/execution_benchmark.json`, `outputs/baseline_comparison.json` — real run data and explicit caveats.

## 2026-11-08 audit fixes (v2.2)

The previous AI-assisted script-only audit identified R039 (missed physical hook), R009 (revealed identity mistaken for cliffhanger), R012 (completed vow), and overlapping packets R016/R036. These were added as executable regression tests. See `FIXES_IMPLEMENTED.md` for exact file changes and limitations. The regenerated results differ from v2.1 intentionally; do **not** combine the older v1 rankings and v2.2 packets. Reviewers must independently score clips before `acceptance_rate` and `agreement` become numeric.
