# Voting Desk

Case 1, Stemmegivningsagenten. Westcoast + 1, FinTech Hackathon H2026. Student prototype, not an NBIM product.

Voting Desk reads a general meeting agenda and proposes FOR, MOT or AVSTÅ on every proposal, with the deciding guideline and a confidence. Low confidence and every vote against the board go to a stewardship manager. Nothing is published without sign-off, and every decision is logged.

Det aktive modellvalget [maksimerer nå F1 for avvik fra styret](README-f1.md). Se også [den låste oktober-testen](README-fresh-test.md) og [Claude med lokalt historikksøk](README-claude-board.md). Den nye [sammenligningen av historikksøk og daterte saksdokumenter](README-relevance.md) viser hvilke endringer som faktisk påvirker F1, med kontroll av tidsgrenser og kilder.

Laget kan installere de lagrede modellene, sammenligne resultatene og kjøre eksempelsaker fra [modellpakken](model-kit/README.md).

## Try it

Unzip `voting-desk.zip`. You need Python 3.12 or later.

**Website.** Open the folder in VS Code and run `app.py`, or run this in a terminal:

```bash
python app.py
```

The first run installs everything into a `.venv` inside this folder, which takes up to two minutes. Your browser then opens. Drop a PDF, HTML or text filing. The zip includes a temporary API key for the website. Delete the zip and folder when you are done, and nothing stays behind.

**Claude plugin, no API key.** In Claude, go to Customize, Plugins, Add, Upload plugin, and choose `voting-desk-plugin.zip` (`voting-desk-plugin-mac.zip` on Mac). Use a session that runs on your computer, attach a filing and ask for a review. It needs Python, not a key. The first time, it sets itself up inside Claude's plugin folder: wait up to two minutes, then start a new chat. Your own Claude drafts in one pass and the same checks route each proposal. That is not the evaluated setup, and each sheet says so.

**Reproduce the result, no key.**

```bash
python run.py
```

The website's agent searches the filing and is the default. Untick it for the three-pass method evaluated below.

## Files

| File | Job |
|---|---|
| `desk.py` | Votes, precedent, screen, prompt, checks, lanes |
| `agent.py` | Optional research in the document |
| `review.py` | Live review and the plugin's tools |
| `app.py` | Drop-a-file page |
| `boot.py` | Sets up the environment on first run |
| `sheet.py` | Review sheet, filled into the design in `assets/` |
| `assets/` | Page design in NBIM's dark style: `style.css`, `report.js`, NBIM logo and company logos |
| `run.py` | Evaluation stages and metrics |
| `report.py` | One-page requirements response. Print the HTML from a browser for the PDF |
| `rules.json` | NBIM guideline rules with dates |
| `test_desk.py` | Offline tests: `python test_desk.py` |
| `plugin/` | Plugin source. `python review.py pack` builds the zips |
| `results/` | Saved results. `results/raw/` holds every model reply |

## Local evidence search

The active local model maximizes F1 for NBIM voting differently from the board. Model selection uses forward validation before 2024; the final threshold uses 2024 calibration: [README-f1.md](README-f1.md). Earlier balanced-threshold and literal-MOT experiments remain documented separately. There is no active 85/85 constraint.

An exploratory local RAG pilot combines SQLite keyword search with CPU embeddings. Run `python rag_app.py` after the setup in [README-rag.md](README-rag.md). It uses pre-decision source documents, has its own index and does not change the saved holdout results.

## Mixed-year 80/20 experiment

Prepare the experimental data partition from the pooled NBIM source:

```bash
python run.py split
```

All 13,757 observations from 2019-2026 already live in `data/real_votes.csv`. The older validation/test tables and five pilot meetings are subsets of this source. Adding them again would duplicate observations. The N-PX file belongs to an unverified manager and is outside this NBIM dataset.

The command writes `data/mixed-80-20/train.csv`, `test.csv` and `manifest.json`. It shuffles company/date groups with seed 2026, within each year and whether the group contains a MOT vote. Same-company meetings on the same date stay together, including distinct meeting IDs. About 80% of groups go to training and 20% to testing. Group sizes differ, so the row proportions are approximate. The manifest records actual yearly counts, missing labels, file hashes and dataset identity. Rows without a known vote stay in the data and must be excluded from supervised target scoring.

This is an exploratory mixed-year experiment. The case asks for earlier training meetings and later test meetings. This split estimates performance within a historical period and contains data already seen in earlier development. Year balancing does not remove all bias.

Use the saved assignment through the dataset loader:

```python
import desk
from dataset import load_split

parts = load_split()
train, test = parts["train"], parts["test"]
train_prior = desk.precedent_features(train, votes=train)
test_prior = desk.precedent_features(test, votes=train)
screen = desk.Screen().fit(train, train_prior)
```

Supply `train` as the historical record in `desk.request` as well. This keeps test labels out of training features and test prompts while retaining the five-day historical cutoff. The frozen `desk.load_votes` assigns splits by date, so use `load_split` for this experiment.

Choose thresholds and calibrate confidence with an internal split or cross-validation inside the 80% training partition. Future model outputs must use a separate directory named with the manifest's dataset ID. Existing model weights, confidence, Claude replies and metrics belong to the original time-based experiment. Preparing this dataset does not train or evaluate the full pipeline. `python run.py` still reproduces those original saved metrics.

Re-running the same preparation verifies and reuses identical output. A different seed or source requires a new `--output` directory. Run `python -m unittest test_dataset -v` to check the partition and loader.

## Method

Our starting point is NBIM's: support the board. The target is whether NBIM voted differently from the board.

1. A text model on ballot wording and NBIM's earlier votes scores each proposal. Fitted on 2019-2023.
2. Claude Sonnet 5.5, effort medium, drafts each meeting three times from the rules in force on the meeting date and NBIM's earlier votes at the company.
3. Python checks each quote against the rule in force. A failed answer goes to a person.
4. Each proposal lands in With board, Against board or Unclear.

Prompts were tuned on 2023 and the threshold set on 2024. The holdout ran once after `results/freeze.json`. The stewardship team should choose the threshold.

## Results

Holdout 2025-2026: 3,449 scored proposals, 169 votes against the board.

| Method | Against board caught | Not flagged | Precision |
|---|---:|---:|---:|
| Follow the board | 0.0% | 100.0% | n/a |
| Proposal type | 87.6% | 31.5% | 6.3% |
| Earlier vote at company | 69.2% | 69.7% | 11.2% |
| Repeat the last vote | 40.8% | 96.6% | 59.0% |
| Claude, guidelines only | 14.8% | 98.7% | 55.6% |
| Text model with precedent | 81.7% | 60.8% | 10.2% |
| **Full system, all sent to a person** | **85.2%** (69 to 94) | **67.3%** (43 to 81) | **12.8%** |
| Full system, Against board lane | 50.3% | 95.2% | 51.2% |

- **Coverage.** All 3,469 proposals got a vote and a confidence.
- **Confidence.** Each proposal shows a number: how often that kind of draft matched NBIM's vote on 2024. High is 95 or more, Medium 80 to 94, Low under 80. Anything below 95 goes to a person, so Unclear is never High. See `metrics.json` for the check on the holdout.
- **Primary test.** 9.8 points more proposals in the batch than the text model at the same recall (+0.3 to +29.9).
- **MOT.** Precision 48.8%, recall 56.1%. Following the board: 67.7% and 11.7%.
- **Accuracy.** 94.4%, against 95.1% for following the board.
- **Threshold.** 90.8% caught on 2024, 85.2% on the holdout.
- **New cases.** 61.9% caught where the company had no earlier vote against the board.

**Policy against practice.** NBIM softened its chair and CEO rule from "will not" to "may not" around March 2026. Where drafts cited it, NBIM voted against the board in 6 of 8 cases before and 0 of 6 after. Our drafts followed precedent and missed this. The sample is small.

**Resistance test.** Text planted in 41 holdout items, in three wordings. All 123 attempts were flagged and none reached the batch. Drafts changed 4 times. Harmless control text changed 3 of 41, so that is ordinary variation.

**Agent, exploratory.** On 52 US holdout meetings, searching the proxy gave more specific reasons but caught no more: 91.7% both ways, with 44.4% not flagged against 58.6%.

**Model choice.** Haiku, Sonnet and Opus 5.5 could not be separated on 12 meetings. Yahoo Finance is left out because it returns today's data.

## Limits

- Holdout counts, 2026 baselines and four outcomes were seen before the freeze. They were not used for tuning.
- After the freeze we corrected reporting in `run.py`, including a rounding bug that had put the primary test at +19.0, plus evidence checks in `agent.py`. `uv.lock` was replaced by `requirements.txt`. `desk.py`, `rules.json` and the data match the freeze, so `desk.review` stays as unused code and `review.py` replaces it.
- Live review uses the same checks and threshold, but agenda reading and document passages were not evaluated.
- Most votes against the board turn on facts not on the ballot, and on engagement we cannot see.
- 7.7% of proposals cite a deciding rule. The others cite the starting point of supporting the board.
- A verified quote shows that a rule exists, not that it applies.
- The confidence number was added after the freeze, calibrated on 2024 only. It comes from pass agreement, flags and the text model. The lanes are unchanged. The model's own low rating routes nothing; using it would give 93.5% caught and 48.4% not flagged.
- The website's default agent is the exploratory path. The evaluated method is the three-pass one.
- The resistance test covers ballot text, not uploaded documents.
- The vote file comes from the organisers, and we use it as supplied.
- 194 companies, probably from current holdings. Position size and market cap are not used.
- NBIM publishes no effective dates or abstention rule, so dates are first public sightings and AVSTÅ goes to a person.
- NBIM's votes are public, so the model may remember them. With names masked on 30 meetings, 94.1% of drafts were unchanged.
- We found no source showing NBIM uses AI in vote decisions.

## Data

| Source | URL |
|---|---|
| NBIM votes, from the organisers, shared with their approval in `data/` | https://www.nbim.no/en/responsible-investment/voting/our-voting-records/ |
| Global Voting Guidelines | https://www.nbim.no/en/responsible-investment/voting/global-voting-guidelines/ |
| Position papers | https://www.nbim.no/en/responsible-investment/position-papers/ |
| SEC EDGAR | https://www.sec.gov/edgar |

## AI use

| Tool | Used for |
|---|---|
| Claude Sonnet 5.5 API | The drafting model and agent. Haiku and Opus 5.5 in the model comparison |
| Claude Code, Opus 5.5 | Research, design review, code, reports and this README. People set the direction and checked the results |
| OpenAI Codex | The earlier pilot, local RAG/vector experiments, supervised history models, tests and exploratory reports |

API spend was about $26 in saved runs at Sonnet list prices, plus small tests.

## Credits

Open libraries: anthropic, scikit-learn, pandas, pypdf, mcp. Font: Hanken Grotesk, SIL Open Font License. No NBIM logo or typeface is used. Rule IDs are ours.
