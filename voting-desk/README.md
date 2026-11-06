# Voting Desk

Case 1, Stemmegivningsagenten. Westcoast + 1, FinTech Hackathon H2026. Student prototype, not an NBIM product.

Voting Desk reads a general meeting agenda and proposes FOR, MOT or AVSTÅ on every proposal, with a confidence and the guideline it rests on. The agent proposes, the code checks, and a person decides. Start with [Kravrespons.pdf](Kravrespons.pdf).

## Run it

Python 3.12 or newer on Windows x64, Apple silicon or Linux x64 (`python3` on Mac):

```bash
python app.py
```

The first start sets itself up and takes up to four minutes. Drop a filing, for example `data/meetings/us/BRCB_2026_05_27.htm`. The Claude key is in `.env`.

Plugin, no key: upload the zip for your system from `plugin/` in Claude. Your own Claude drafts one pass, which is not the tested setup.

The pages are drawn in NBIM's dark style from `assets/`: `style.css`, `report.js`, the NBIM logo and company logos. `sheet.py` fills them with data.

To reproduce the numbers, with no key:

```bash
python run.py
```

## How it decides

1. Claude reads the agenda and writes three drafts from NBIM's guidelines and the company's earlier votes.
2. A local text model gives each proposal a risk score.
3. Python checks every quote. If the drafts disagree, a check fails, or the score is at or above 0.22, a person reads it.
4. The rest is signed off in a batch.

The 0.22 threshold is where about 90% of votes against the board lay above the cut in 2024 and 2025, at about 1,000 other companies. It is the stewardship team's choice.

## Result

We locked the system and ran it once on 1,000 meetings from 2026, at 751 companies outside development. 9,218 proposals, 454 against the board.

| | Result |
|---|---:|
| Votes against the board that reach a person | 92.7% (89.7 to 95.2) |
| Proposals in the batch | 48.4% (46.5 to 50.3) |
| Against board lane, precision and recall | 46.1%, 44.5% |
| MOT drafts, precision and recall | 40.3%, 54.7% |
| Following the board, MOT precision and recall | 59.7%, 9.2% |

Our own local history model matches the system on routing when history stops on 1 January, 48.5% against 48.4%. It gives no vote, reason or quote, which is what Claude adds. Henrik's local model did worse, 44.7% at equal reach. Eleven other ideas failed tests written beforehand, and `results/metrics.json` lists them.

The agent followed a planted instruction in none of 20 filings. Indirect wording passes our scan.

## Where to check

Method: this file and `Kravrespons.pdf`. Evaluation: `results/metrics.json`, `python run.py` and `python test_desk.py`. Decision support: `results/sheets/`. Robustness: `results/document_resistance_20.json`, and how the sealed set was drawn in `selection/`.

## Limits

The lane is weak after June, 14 of 63 right. Auditor proposals are weak, 20 of 32 reached. The test read ballot text, so document reading is not evaluated. 73 of 79 rules use today's text at every date. Claude may have seen NBIM's votes, which we cannot rule out. Details are in `results/metrics.json`.

After the sealed run we changed labels, messages and live-path fixes, and no sealed lane moved, so some code differs from `results/freeze_v3.json`. `desk.py` and `rules.json` match it. The history model was built after the run, and its comparison column was removed from `results/items_sealed.csv`.

## One more week

1. Facts from filings outside the US, including auditor fees.
2. Opus on unused meetings, with precision named up front.
3. A local language model, with routing in-house too.
4. Position size, so the largest holdings come first.

## Data

- NBIM votes, supplied by the organisers: https://www.nbim.no/en/responsible-investment/voting/our-voting-records/
- NBIM voting API, cleared with the organisers: https://vd.a.nbim.no/v1
- Global voting guidelines: https://www.nbim.no/en/responsible-investment/voting/global-voting-guidelines/
- SEC EDGAR: https://www.sec.gov/edgar

## AI use and credits

Claude Sonnet 5.5 drafts. Claude Code and OpenAI Codex helped with research, code and reports, and we checked the results. API spend was about $170.

Oskar did the error analysis, and Henrik built the local models. Henrik's other experiments are on branch `NK-experiments`. Libraries: anthropic, scikit-learn, pandas, pypdf, mcp. Font: Hanken Grotesk, SIL Open Font License.
