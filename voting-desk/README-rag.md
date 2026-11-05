# Local evidence search

The active local classifier now maximizes **F1 for NBIM voting differently from the board**, with chronological training and 2024 threshold calibration. See [README-f1.md](README-f1.md). Earlier literal-MOT experiments remain separately documented below.

This exploratory RAG pilot runs retrieval on this computer. SQLite stores source text, metadata and vectors. SQLite FTS5 provides BM25 keyword search; FastEmbed runs `BAAI/bge-small-en-v1.5` on CPU and produces 384-dimensional embeddings. Hybrid search combines both rankings with reciprocal rank fusion. Exact cosine search over one meeting's passages is sufficient for this pilot; there is no separate database server.

The first download obtains the open embedding model. Later searches load its cached files with network access disabled for the model loader. No Azure account or embedding API key is needed. The optional Claude generation step still uses the existing paid Anthropic API.

## Start

Run from `voting-desk/` in the existing project environment:

```bash
.venv/bin/python -m ensurepip --upgrade
.venv/bin/python -m pip install -r requirements-rag.txt
.venv/bin/python local_rag.py setup
.venv/bin/python local_rag.py build
.venv/bin/python rag_app.py
```

The search page opens at <http://127.0.0.1:8502/>. It provides a meeting selector, keyword/vector/hybrid search, exact excerpts, an extracted-source view with the excerpt highlighted, and links to SEC originals. It makes no Claude calls. The existing Voting Desk remains at its original port.

By default the builder takes the first five eligible filings in chronological order from 2024 for document browsing. Two of those meetings belong to the reserved mixed-year test partition, so this index must not be used for tuning voting recommendations. The separate evaluation index below excludes them. There are 32 eligible local 2024 filings in the current source collection; one incomplete filing-index entry is reported as skipped. Expanding the browsing corpus is explicit:

```bash
.venv/bin/python local_rag.py build --limit 32 --db data/local-rag/all-2024.sqlite
.venv/bin/python rag_app.py --db data/local-rag/all-2024.sqlite --port 8503
```

Existing indexes are never overwritten. Use a new `--db` path when changing the corpus, model or experiment. Model weights and generated databases live under the ignored `data/local-rag/` directory.

## Retrieve evidence

Use English queries because both the pilot documents and the embedding model are English. For example:

```bash
.venv/bin/python local_rag.py status
.venv/bin/python local_rag.py search --meeting 1818232 --query "director independence committee membership"
.venv/bin/python local_rag.py context --meeting 1818232 --query "executive compensation performance targets"
```

`context` emits a JSON evidence bundle containing exact passages and source identifiers, ready to supply to a model. Search scores describe ranking, not the probability that a vote is correct. Vector search always finds nearest passages, even when the document does not contain the answer.

## Source boundaries

- The corpus reads `data/meetings/us.csv` and the existing local HTML filings. From `real_votes.csv`, it reads only the meeting/company/date identity needed to join the files.
- NBIM votes, target columns and NBIM outcome rationales are excluded from the search index and embedding inputs. Public facts in a pre-decision filing remain eligible evidence.
- Each source must have a publication date strictly before the meeting date minus five days, matching the existing experiment's cutoff. This restriction is checked during both ingestion and retrieval.
- Every search is scoped to one meeting before ranking. Company/date/source metadata are stored explicitly; text similarity never selects a different company or time period.
- Excerpts retain their original wording within a canonical text extraction. Character offsets refer to that extraction, not the original HTML bytes or PDF page numbers. Tables retain row/cell separators, but complex layouts still require checking the original.
- Source hashes, model-file hashes and the FastEmbed version are recorded. A changed model is rejected when querying an old index. Missing documents and dates are reported rather than filled in.

There is no meeting-summary embedding in this first version: the known meeting ID directly selects its context. Evidence passages are the retrieval unit; each voting proposal remains a separate assessment unit. A later historical-example index needs separate date and evaluation-fold restrictions before it can contain NBIM's earlier votes.

## Optional Claude connection

For the whole-source chronological comparison on the same 1,883 proposals as the local disagreement model, see [Claude with retrieved historical votes](README-claude-board.md). That experiment uses `claude_board_experiment.py`; the document-only connection below is a separate, smaller cohort.

Prepare an evidence bundle for every proposal in an indexed meeting:

```bash
.venv/bin/python rag_review.py --meeting 1818232
```

Add `--generate` to make one paid Claude call using the current configured model and key. The bundle includes proposal inputs, retrieved source passages and the rules applicable on the meeting date. It does not include NBIM targets or voting history. The output uses a separate experimental schema and does not update old review sheets, confidence calibration or saved benchmark scores.

```bash
.venv/bin/python rag_review.py --meeting 1818232 --generate
```

Citation checks establish whether a quoted passage was actually retrieved. They do not prove that the passage logically supports the recommendation. The user must review the evidence and recommendation.

## Evaluation

The results page is at <http://127.0.0.1:8502/evaluation>. It reads saved aggregate reports and makes no model calls. It shows unfinished runs with their completed-meeting counts and compares each run with baselines on the same rows.

The [local vector voting model](README-vector.md) is a separate CPU-only alternative to Claude. It predicts MOT from earlier similar ballot items, with forward validation and a recall target. Its [historical-neighbour explorer](http://127.0.0.1:8502/vector) shows the saved evidence behind each score.

An earlier [learned historical/vector model](README-learning.md) used a joint MOT precision/recall target. It compared 12 supervised variants without API calls and exported a source-fact review queue for development errors. That target is retired; its saved results remain historical.

Build the evaluation corpus from 2024 meetings in the existing 80% training partition. The split manifest and file hashes are checked first. The current corpus contains 22 meetings, 235 proposals and 10,774 passages. Of the proposals, 232 have known NBIM votes and 11 are MOT. This is previously used development data; no new final-test score is claimed.

```bash
.venv/bin/python rag_development.py
# Only when the index does not already exist:
.venv/bin/python rag_development.py --build
.venv/bin/python rag_eval.py baseline
```

The following commands make paid Claude calls. Each run uses the same model, prompt and dated rules. `proposal` retrieves passages for each proposal; `meeting` also retrieves shared facts about board composition, independence, attendance, compensation and auditors. Neither supplies NBIM targets or vote history to Claude.

```bash
.venv/bin/python rag_eval.py run --mode hybrid --strategy proposal
.venv/bin/python rag_eval.py run --mode hybrid --strategy meeting
.venv/bin/python rag_eval.py report
```

Completed and failed calls have immutable caches tied to the source dataset, full evidence bundle, code and generation settings. Repeating the same command reuses them. Failed calls remain in the scoring denominators. Changing the prompt or evidence creates a separate experiment; it does not replace previous results. After concurrent runs finish, regenerate the report once to collect all caches.

The main scores classify a literal MOT vote. Precision is TP / (TP + FP); recall is TP / (TP + FN). A missing recommendation for a true MOT counts as FN. Unknown NBIM labels are excluded. Recommendation coverage, manual-review share, exact guideline quotes and exact source quotes are separate measures. Quote matching checks that text exists, not that it supports the conclusion. The earlier 85.2% routing recall measures a different outcome.

`mot_experiment.py` compares three local classifiers using five company/date-grouped folds inside the 2019–2023 portion of the mixed training set. It chooses its threshold from out-of-fold predictions before evaluating on the 2024 development subset. The saved Claude comparison is descriptive because the earlier system used a different training/history setup.

`rag_retrieval_eval.py` compares keyword, vector, hybrid and an experimental alternating rank merge. It uses 12 annotated development questions plus 24 predefined query variants. Its anchor-hit@5 is the share with a known evidence quote among the first five passages. The annotations do not exhaust all relevant evidence, so this is not full retrieval recall or voting recall.

`rag_injection_eval.py --run` makes one paid request with an attack appended to a copy of a cached evidence bundle. It compares that answer with the original. This tests one generation-context injection; ingestion and retrieval are outside that test's scope. The original documents and index remain unchanged.

Detailed artifacts are under `data/local-rag/`: `rag-evaluation-v1/`, `mot-experiment-v1/`, `retrieval-evaluation-v1.json` and `rag-injection-evaluation-v1/`. They are ignored by Git. Frozen historical results remain in `results/`.

## Verification

```bash
.venv/bin/python -m unittest test_rag_corpus test_local_rag test_rag_app test_rag_review test_desk test_dataset -v
```

The tests cover source integrity, date and meeting boundaries, absence of target columns, retrieval behaviour, HTML escaping and generation with a mocked client. Additional evaluation tests are in `test_rag_eval.py`, `test_rag_review_enriched.py`, `test_rag_retrieval_eval.py`, `test_mot_experiment.py` and `test_rag_injection_eval.py`. These tests make no paid API calls.

This work was implemented with Codex assistance. Technical references: [SQLite FTS5/BM25](https://www.sqlite.org/fts5.html), [FastEmbed](https://qdrant.tech/documentation/fastembed/fastembed-quickstart/). The frozen `desk.py`, `rules.json` and saved holdout results remain unchanged.
