# Narrative (case-description) evaluation

Users search by **describing their case** in 40-150 words: facts, what each side
claims, what the courts below held, sometimes the outcome. They may be the
appellant's lawyer, the opposing party, or a layperson or victim. One judgment has to be
findable from all of those descriptions. This harness measures that. It is
separate from the short-query harness (`run_eval.py`, `dev.jsonl`/`test.jsonl`),
but it reuses evallib's dataset format and split rule.

## Files

| file | what it is |
|---|---|
| `synth_narratives.py` | One LLM call per judgment writes 4 descriptions (2 alternatives each): `appellant_lawyer` (detailed), `opposing_party` (detailed), `layperson` (loose), `layperson_other_side` (loose). Checks: 40-150 words, no case number or citation, no party names in loose descriptions, and no 4-gram shared with the judgment or its card. Exempt from the 4-gram check: names in detailed descriptions, and 4-grams made only of function words and procedural words. Every alternative that fails a check is logged. The script resumes where it stopped. `--sample` stratifies by subject. `--max-calls` caps the calls. `--fill-missing` asks again only for slots whose alternatives were all rejected. `--recheck` reapplies the checks to the stored outputs with 0 calls. `--calibrate` runs the checks on the hand-written rows with 0 calls. |
| `synthetic/synthetic_narratives.jsonl` | Generated rows. `spare: true` rows are second alternatives that passed; the builder does not use them. |
| `synthetic/narrative_rejections.jsonl` | Every rejected alternative, with the reason and the offending 4-grams, case numbers or names. |
| `synthetic/narrative_calls.jsonl` | One line per LLM call, including the parsed output. This is what makes `--recheck` free. |
| `narrative_negatives.json` | 54 hand-written out-of-archive descriptions. 42 are near-domain (`verify_at_scale: true`) and 12 are far-domain (foreign law or no court case). |
| `narrative_lib.py` | Row format (`perspective`, `detail`, origins), the conversion of `results/narrative_baseline_v0.json` (frozen) into 25 `hand_written` rows, the `retrieve_v2` runner, and the LLM-call guard. |
| `build_narrative_datasets.py` | Writes `datasets/narrative_dev.jsonl` and `narrative_test.jsonl`, using evallib's split rule (by judgment, hash-stable). `--freeze` writes `narrative_test.sha256`. **Freeze once, at 3,000 judgments.** |
| `run_narrative_eval.py` | Metrics: case findability (≥1, ≥2, majority, all), p@1 and recall@5 (shown and before the gate) by perspective, detail and origin, out-of-archive leaks and "high" leaks, refusal rate, confidence-label distribution, latency, party pinning. `--hand-written-baseline` diffs against narrative_baseline_v0. Each saved run records the config flags and the sha256 and mtime of every retrieval file. |
| `labels/narrative_negative_candidates.json` | Near-domain negatives that retrieved a judgment. Each one needs a human decision. |
| `results/runs/narrative_dev_current.json` | The round-2 narrative baseline (11 judgments, current pipeline). |
| `results/runs/narrative_handwritten_current.json` | The 25 hand-written rows on the current pipeline, diffed against v0. |

Rows use the existing format plus `perspective`, `detail`
(`detailed`/`loose`) and `origin`, which is one of `synthetic_narrative`,
`narrative_negative` or `hand_written`. `query_type` is `paraphrase`, so
`run_eval.py --dataset eval/datasets/narrative_dev.jsonl` can still load the file.

## Round-2 narrative baseline (11 judgments, measured 2026-10-04)

`results/runs/narrative_dev_current.json`, measured with the default config:
`NARRATIVE_FACETS=True`, `NARRATIVE_MAX_CONFIDENCE=medium`, judge off,
analyzer off. The retrieval code did not change during the run; its file hashes
are in `code_state`. The run made 0 LLM calls.

| narrative_dev: 7 judgments, 34 descriptions, 40 out of archive | value |
|---|---|
| findability, ≥2 generated descriptions shown first | 6/7 (0.857, CI 0.49-0.97). 3628e429 is 0/4: all refused at window rank 1 |
| findability, all origins: ≥1 / majority / all | 7/7 / 6/7 / 3/7 |
| p@1 shown (= recall@5 shown) | 25/34 = 0.735 (CI 0.57-0.85). Detailed 0.88, loose 0.59 |
| p@1 / recall@5 before the gate | 32/34 = 0.941 / 34/34 = 1.000 |
| wrong judgment shown first | 0/34 |
| false refusals | 9/34 = 0.265. Each one is a gate refusal, not a retrieval miss |
| out of archive: leaks / shown "high" / refused | 0/40 / 0 / 40/40 |
| top labels of correct results | medium 24, high 1 |
| latency p50 / p95 | 3.9 s / 25.9 s. CPU was shared with other agents' model loads, so p95 is overstated |

The hand-written rows (`--hand-written-baseline`) on the current pipeline give
detailed 11/11, loose 3/5, leaked 0/7, 0 shown "high", party-pinned 0/2. With
`--override NARRATIVE_FACETS=false --override NARRATIVE_MAX_CONFIDENCE=high`
the same runner reproduces narrative_baseline_v0 exactly (11/11, 3/5, 2/7, 1
"high"). The one exception is party pinning (0/2 vs 2/2), which comes from the
exact_match party-pin fix and has no flag. So the leak and label changes
against v0 come from the narrative facet path and the label cap, not from the
harness.

## Everyday commands (no LLM calls)

```
python eval/run_narrative_eval.py                                    # narrative_dev
python eval/run_narrative_eval.py --save eval/results/runs/<name>.json --label "<what changed>"
python eval/run_narrative_eval.py --hand-written-baseline            # v0 rows, diffed
python eval/build_narrative_datasets.py --check                      # counts per split/perspective/detail/origin
python eval/synth_narratives.py --recheck                            # after editing a check
for f in narrative_lib synth_narratives run_narrative_eval; do python eval/$f.py --self-check; done
```

On the default config the runner allows **0 Gemini calls** (`--llm-budget 0`).
If a flag turns on an LLM stage (judge, LLM facets), those calls fail as if the
LLM were unavailable, the run continues, and the blocked count is printed. Pass
`--llm-budget N` when you want to measure an LLM stage on purpose. On the free
tier, budget about 1-3 calls per description, which is about 5 descriptions per
minute.

## Out-of-archive rows: candidate positives, not failures

A near-domain negative (`verify_at_scale: true`) that shows a judgment is
**not** counted as a failure or a pass. It is printed as a candidate positive and
merged into `labels/narrative_negative_candidates.json`. Someone has to read the
shown judgment and decide:

* If it really decides that situation, the row becomes a positive. Move it into
  a dataset with `relevant {pdf_id: 2}`, or add a hand-written row.
* If it does not, set `verify_at_scale: false` in `narrative_negatives.json` so
  the row counts as a plain failure from then on.

Far-domain rows never become candidates. If one of them leaks, that is a failure.
"Leaks shown as high" counts every leak regardless of domain. On the free tier
the target is 0.

## Milestone runbook

The figures below assume Gemini's free tier: 15 requests/min shared with users,
the card wave and the other agents. The generator sleeps 4.5 s between calls,
and a call takes about 5-10 s, so it runs at about 5 calls/min. That is roughly
1/3 of the quota. **Check the daily request cap of your Gemini model.** If one
day's cap is too small, run the same command on several days. It resumes and
never repeats a judgment that already has a successful call.

### At 1,000 judgments

Before you start, the owner has done bulk ingest, then `python -m app.indexing.check --repair`
reports 0 gaps, then the card wave has finished. The generator uses the cards
for the prompt and for stratifying by subject. It still runs on a judgment
without a card, but the prompt is weaker.

```
python eval/synth_narratives.py --sample 200 --dry-run              # check the plan (0 calls)
python eval/synth_narratives.py --sample 200 --max-calls 220        # ~200 calls, ~45-60 min of quota
python eval/synth_narratives.py --sample 200 --fill-missing --max-calls 60   # ~25-45 calls
python eval/build_narrative_datasets.py                             # test NOT frozen
python eval/run_narrative_eval.py --save eval/results/runs/narrative_dev_1000.json --label "1,000 judgments"
```

* Expected LLM calls: about 200 for generation, 25-45 for fill-missing, and up
  to about 20 retries on rate limits. Call it about 270 at most, and cap it with
  `--max-calls`. On today's corpus 14 calls produced 39 of 44 slots.
* The 11 judgments that are already generated are skipped. Their rows stay in
  the dataset in the same split.
* Measurement uses no LLM calls. It covers about 60% of 200 judgments, at about
  3.5 descriptions each plus about 90 negative and hand-written rows. That is
  roughly 500 rows at 3-8 s each, so about 30-70 min of CPU.
* Afterwards, review `labels/narrative_negative_candidates.json`. At 1,000
  judgments some near-domain negatives (bail, rent, pre-emption) will probably
  have a genuine match.
* Spot-check about 30 generated descriptions in `synthetic_narratives.jsonl`.
  Their labels are correct by construction, but nobody has read the text.

### At 3,000+ judgments: the reportable number

```
python eval/synth_narratives.py --sample 500 --dry-run
python eval/synth_narratives.py --sample 500 --max-calls 550        # ~350-500 new calls (overlap with the 1,000 sample is skipped)
python eval/synth_narratives.py --sample 500 --fill-missing --max-calls 120
python eval/build_narrative_datasets.py --check                     # read the counts first
# human review: resolve every near-domain candidate; spot-check ~50 narrative_test rows
python eval/build_narrative_datasets.py --freeze                    # ONE TIME: writes narrative_test.sha256
python eval/run_narrative_eval.py --save eval/results/runs/narrative_dev_3000.json --label "3,000 dev"
python eval/run_narrative_eval.py --split test --save eval/results/narrative_test_3000.json --label "3,000 TEST (reported)"
```

* Expected LLM calls: about 600-650 at most, including fill-missing and retries.
  That is about 2-2.5 hours of quota at 5 calls/min, spread over as many days as
  the daily cap requires.
* **Freeze once.** After `--freeze`, a rebuild that would change
  `narrative_test.jsonl` is refused unless you pass `--allow-test-changes`, and
  `run_narrative_eval.py --split test` refuses to run on a modified file. Run the
  test split once, after every tuning decision has been made on dev. Do not tune
  against it.
* A larger sample is fine if the quota allows it. Do not change
  `evallib.SPLIT_SALT` or `TEST_PERCENT`: that would move judgments between dev
  and test.
* Plan targets on the frozen test set: findability (≥2 descriptions shown first)
  ≥ 0.90, p@1 ≥ 0.85, recall@5 ≥ 0.95, 0 out-of-archive "Strong match" on the
  free tier, and retrieval p95 ≤ 4 s.

### Known caveats

* The generated texts come from Gemini (`gemini-3.5-flash-lite` today) and are
  checked mechanically, not by a person. For each judgment, the outcome stated in
  the narratives comes from the card's `outcome` field. That field is regex/LLM
  extracted, so it can be wrong.
* The 4-gram rule is strict. Against the judgment plus its card it rejects 9 of
  the owner's 11 hand-written detailed narratives. Expect 10-20% of detailed
  slots to stay empty after fill-missing, mostly for election and
  service-tribunal judgments, whose terms ("election tribunal", "civil
  servants") have no everyday synonym. Findability is computed over the
  descriptions that exist. The runner lists any judgment with fewer than 2.
* The 25 hand-written rows and the 4 current test judgments have already been
  seen during development. Today's narrative_test is not unseen data. It becomes
  meaningful at 3,000, where these rows are a small fraction.
* Latency depends on machine load. A run made while other model-loading
  processes share the CPU overstates p95.
