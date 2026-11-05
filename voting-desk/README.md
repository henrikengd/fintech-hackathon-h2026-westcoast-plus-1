# Voting Desk

Case 1, Stemmegivningsagenten. Westcoast + 1, FinTech Hackathon H2026. Student prototype, not an NBIM product.

Voting Desk reads a general meeting agenda and proposes FOR, MOT or AVSTÅ on every proposal, with the deciding guideline and a confidence. Low confidence and every vote against the board go to a stewardship manager. Nothing is published without sign-off, and every decision is logged.

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
| `sheet.py` | Review sheet |
| `run.py` | Evaluation stages and metrics |
| `report.py` | One-page requirements response. Print the HTML from a browser for the PDF |
| `rules.json` | NBIM guideline rules with dates |
| `test_desk.py` | Offline tests: `python test_desk.py` |
| `plugin/` | Plugin source. `python review.py pack` builds the zips |
| `results/` | Saved results. `results/raw/` holds every model reply |

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
| OpenAI Codex | The earlier pilot in the group repo |

API spend was about $26 in saved runs at Sonnet list prices, plus small tests.

## Credits

Open libraries: anthropic, scikit-learn, pandas, pypdf, mcp. Font: Hanken Grotesk, SIL Open Font License. No NBIM logo or typeface is used. Rule IDs are ours.
