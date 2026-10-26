# Adding judgments to the archive

Run every command from `backend/`, with the virtualenv's Python
(`venv/Scripts/python.exe`, written as `python` below).

## What "searchable" and "complete" mean

A judgment is found by search only when these stores are written:

| store | what it is | written by |
|---|---|---|
| tree | the six-section tree in MongoDB (`nodes`, `document_trees`) | parse step |
| dense | the live vector index (Chroma) + `embedding_mappings` + `app/connection/*.json` | embedding step |
| fts | the keyword (BM25) index, `lexical.db` | indexing step |
| card | the case card (`case_cards`): one Gemini call | card wave / upload |
| card_vector | the card's vector (`legal_cards_v1`) | after each card |

Every write is recorded on `documents.index_status`, and the document status is
derived from it:

- **searchable**: tree, dense and fts are written. Search finds the judgment.
- **complete**: searchable, plus a complete case card and its vector.
- **failed**: a stage failed. The job status names the stage
  (`extraction_failed`, `parse_failed`, `tree_failed`, `embedding_failed`,
  `index_failed`) and `index_status.last_error` says why.
- in progress: `uploaded`, `extracted`, `parsed`, then `indexing` (tree written,
  search stores not yet).

The admin Cases page shows all of this per judgment: status, which stores are
written, the parse-quality flags, and a Retry button.

## For many PDFs (the 1,000 and then 3,000+ loads)

**1. Triage: read-only, takes minutes.**

```
python ingest_bulk.py --input "D:\path\to\pdfs" --triage-only
```

Prints how many files are digital, scanned, duplicate or corrupt, and writes a
manifest to `ingest_reports/`. Nothing is written. Fix or remove corrupt files.

**2. Ingest: extraction, OCR, parsing, vectors, keyword index.**

```
python ingest_bulk.py --input "D:\path\to\pdfs" --allow-main-db --llm-concurrency 2
```

- Each judgment is **searchable as soon as its file finishes**. Nothing else is
  needed for search; the case card comes in step 4.
- `--allow-main-db` is required on purpose: without it the tool refuses to touch
  the live database.
- It makes one Gemini call per judgment (the parse). **On the free tier, run it
  once a day.** The free tier's limits stop it partway. You can stop and re-run
  it at any time, even with a hard kill: finished files are skipped, and
  half-finished ones resume at the store that is missing. A file whose tree
  already exists is never parsed again.
- Failed files are listed in the run's report. Retry them with `--retry-failed`.
- Scanned PDFs go through OCR and are slower (about 4 s per page per core; see
  "Scanned PDFs" below).
  Embedding is CPU work too, measured at 5-20 s per judgment depending on load.

**3. Check, after every batch.**

```
python -m app.indexing.check            # read-only report; exit code 0 = no gaps
python -m app.indexing.check --repair   # fill whatever is missing (no AI calls)
```

`check` compares every store with every document and lists:

- each judgment with a missing store, and why ("no vectors", "connection JSON
  missing", "no FTS rows", "card metadata_only"...);
- orphans, meaning store entries whose document no longer exists.

`--repair` fills the gaps per judgment: it rebuilds a missing tree from the cached
parse, and re-embeds or re-indexes only what is missing. It also records the
true status for documents written before status tracking existed. **Run
`--repair` once on the existing archive before the first card wave.** Orphans
are removed only with `--prune-orphans --allow-main-db`.

**4. Card wave: one Gemini call per judgment.**

```
python -m app.ingestion.case_card --all
python -m app.ingestion.case_card --all --limit 200     # cap today's calls
```

- It only picks judgments that are searchable, not failed, and have no card, a
  `metadata_only` card, or an outdated one, so it never spends a call on a
  broken document.
- Rate limits get backoff with a shared cooldown. A daily-quota error stops the
  wave cleanly. **Re-run it the next day.** It resumes with the judgments
  still missing a card.
- After each card it refreshes that judgment's keyword row and card vector, and
  the judgment becomes **complete**.
- A card whose AI call failed is stored as `metadata_only` with `card_error`
  saying why. It is a gap in `check`, and the next wave retries it.

**5. Check again.** `python -m app.indexing.check --require-cards` exits 0 only
when every judgment is complete.

### Milestones

1. **1,000 judgments.** Run ingest daily until the folder is done, then
   `check --repair`, then card waves until `check --require-cards` passes. Then
   regenerate the evaluation (below) and measure. On the free tier, plan on
   several days. On a paid tier it takes hours (raise `--llm-concurrency` to 3
   and the card wave's `--concurrency`).
2. **3,000+ judgments.** Do the same for the remaining PDFs. Then freeze the test
   set once and run it once (below).

## For a few PDFs

Upload them through the admin panel. That runs the whole chain: extraction,
parsing, vectors, the case card, the keyword index and the card vector. If the
case-card call is rate-limited, the judgment is still **searchable**. Use the
**Card** button or the next card wave to complete it.

- **A failed upload can be retried.** Use the **Retry** button
  (`POST /api/admin/jobs/{id}/retry`). It resumes from the last stage that
  succeeded. You can also upload the same PDF again: a failed or interrupted
  earlier upload of the same file is resumed instead of being rejected as a
  duplicate.
- **If the server restarts mid-upload,** the job shows as **stalled** after 15
  minutes. Retry it.
- Extraction, OCR and embedding run in background threads, so searches stay
  responsive while an upload is processed.

Deleting through the admin panel removes the case from every store. See the
warnings below.

## Scanned PDFs

Scanned judgments (a PDF that is only page images) go through the same chain as
typed ones. Nothing extra is needed: triage, bulk ingest and admin upload detect
them and OCR them. The OCR lives in `app/ingestion/ocr.py`.

**Setup, once per machine.** Install Tesseract 5 (Windows: the UB-Mannheim
installer, default path). The accurate English model, `tessdata_best`, goes in
`backend/tessdata/eng.traineddata`:

```
curl -L -o tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata
```

Without that file Tesseract's own (fast, less accurate) model is used and a
warning is logged.

**What happens to a scanned PDF**

- Each scanned page is rendered at ~300 dpi and straightened: a tilt of up to
  15 degrees is measured and corrected, and a page scanned sideways or upside
  down is turned upright. It is then cleaned (scanner borders, binding shadow
  and page-edge lines are painted out) and OCR'd. Typed pages keep their text
  layer, so mixed files work.
- A scan that carries the scanner's own OCR text (an invisible layer, often
  garbled: "INIJIF SupIZEME COURT Or'") is treated as a scan and OCR'd afresh
  when that layer does not show the court heading. Such files used to be read
  as typed and refused as "not a judgment".
- Lines Tesseract skips or garbles, typically the bold underlined court
  heading and case-number line, are re-read one at a time.
- Stamps, handwriting and margin marks are dropped: words are checked against
  the archive's vocabulary (`app/ingestion/data/ocr_lexicon.json`, built from
  the typed judgments) and Tesseract's confidence.
- A few unambiguous misreads are repaired: a lost date dot (`7.122017`), the
  Lahore registry letter read as 1 (`933-1/2013`), `No0.`.
- Each judgment's OCR quality is saved on `documents.ocr`: pages OCR'd, mean
  confidence, vocabulary rate (typed text scores ~0.99), low-quality pages.
  Weak OCR also appears in `quality_issues`, so it shows on the admin Cases
  page.

**How accurate it is.** It was measured two ways. First, on typed judgment
pages made to look photocopied, where the true text is known: 97.6% of words
and 98.2% of characters are read correctly, as are 97% of dates, case numbers,
section numbers and names. Most of the remaining "errors" are reading-order
differences in the page header, and typos in the typed original. Second, on
all 260 scanned judgments in `remaining judgement/scanned pdf` (2,375 pages):

- 98.5% of OCR'd words are in the archive vocabulary (typed text: ~99%);
- the court heading is read on 255 of 260 first pages, and the case number on
  251 of 258;
- all 260 pass validation as Supreme Court judgments;
- 6 judgments have weak pages (27 pages in all, mostly the 1976 typewritten
  appeal and two very faint ones); these are flagged in `quality_issues`.

**Section parsing.** OCR text is laid out in paragraphs, as typed text is,
because the section parser splits judgments at blank lines. On 40 typed
judgments, each parsed once from its own text and once from OCR of its pages
made to look photocopied, the parse-quality check passed for 33 typed and 37
OCR parses (mean confidence 0.854 against 0.852), the Gemini fallback was needed
for 3 of each, and the median share of each typed section's words that land in
the same section of the OCR parse is 94-100% across the six sections.

The old OCR read 94.1% of words and 87% of key tokens, and on the 1976 appeal
it read the heading as "SUPREME COURT OF PAKIGPAN", which the validator rejects
as "not a judgment".

**The `not judgement document` folder (64 files).** 10 are tilted scans with a
garbled scanner text layer: all 10 now pass and are ingested. 40 are Urdu
judgments: refused, because OCR, vocabulary, parser and search are English
only. 14 are typed English files whose first page is not the court heading
(separate opinions and notes, e.g. a dissent that begins "Ayesha A. Malik, J.-
I have read the opinion of the majority"): refused by the typed-PDF
validation, which is unchanged.

**Speed.** About 3.5 s per page on an idle core. All 260 scanned judgments took
87 minutes with bulk ingest's default 12 OCR workers on this 8-core machine
(~27 pages a minute). An admin upload OCRs up to 4 pages at once
(`OCR_PAGE_WORKERS`).

**Self-check:** `python -m app.ingestion.ocr_selfcheck`

## Older commands you no longer need for new judgments

- `python reindex.py --resume` rebuilds the live vectors from MongoDB. You need
  it only after changing the embedding model or the chunking.
- `python reindex.py --fts` and `--cards` rebuild the keyword index and the card
  vectors from scratch.
- `python reindex.py --contextual ...` builds the contextual collection. Live
  search does not read it. It runs only if `CONTEXTUAL_INDEXING` is on (or with
  `--force-contextual`), and it resumes by default.

## After each milestone: rebuild the evaluation

```
python eval/synth_queries.py --sample 150 --max-calls 170
python eval/build_datasets.py --allow-test-changes
python eval/run_eval.py --split dev
```

`--allow-test-changes` re-freezes the held-out test set. Do this **once, at
3,000**, then leave the test set alone. `run_eval.py --split test` is the number
to report, and it is honest only if nothing was tuned against it.

Also confirm the labels in `eval/labels/real_queries_review.md` (about an hour),
then run `python eval/import_labels.py` and rebuild the datasets.

## Warnings

- **Deleting a case from the admin panel is permanent.** It removes the database
  records, the search vectors, the keyword rows, the card, and the files in
  `uploads/`. It also removes the Google Drive copy, but **only by the Drive file
  id saved at upload**. A case without a saved id (bulk ingest without `--drive`)
  keeps its Drive copy. The panel never deletes Drive files by name, because
  names repeat across thousands of judgments. Keep your own copy of every PDF.
- Do not run `reindex.py --reset` casually. It drops the whole live collection,
  and search returns nothing until the rebuild finishes.
- A hard kill of `ingest_bulk.py` on Windows can leave its worker processes
  running (`python -c "from multiprocessing.spawn ..."`). Check Task Manager
  before re-running.
