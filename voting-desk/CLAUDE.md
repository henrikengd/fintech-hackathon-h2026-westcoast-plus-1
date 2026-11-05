# Voting Desk

Case 1, Stemmegivningsagenten. Westcoast + 1, FinTech Hackathon H2026, jury from NBIM. Deadline Friday 6 Nov 2026 at 12:00. Send to milad.tootoonchi@nmbu.no with subject `<group name> Hackathon H2026 demo` and all member names.

## Commands

- `python run.py` reproduces the result from `results/`.
- `python app.py` starts the website.
- `python test_desk.py` runs the tests.
- `python report.py` rebuilds the one-pager. Print `results/kravrespons.html` from Chrome to get the PDF, and keep it on one page.
- `python review.py pack` builds `dist/`, including the judge zip with the key from `.env`.

## Rules

- `desk.py` and `rules.json` are frozen. Their hashes are in `results/freeze.json`, so do not edit them. Live changes go in `review.py`.
- 2025-2026 is the sealed holdout, and it has run. Never rerun it to improve a number. New work is exploratory and labelled so.
- Report results as they are, and frame thresholds as choices for the stewardship team, not targets.
- Votes are proposals. Every proposal gets a vote and a confidence, and nothing is published without sign-off.
- The API key never goes in git. `dist/voting-desk.zip` holds it and stays out of git.
- Model: Claude Sonnet 5.5, effort medium. In the plugin, the user's own Claude drafts one pass, which is not the evaluated setup.
- Keep it lean: flat files, plain names, little text, no AI-sounding prose. Credit copied code and keep the README's AI declaration current.
- Say "digital colleague" and "stewardship manager". Do not claim NBIM uses AI for votes, or that this is an NBIM product.

## Main results

Holdout: 3,449 proposals, 169 against the board. 85.2% reach a person, 67.3% go to the batch, and the primary test is +9.8 points (+0.3 to +29.9). See `README.md`, and `results/metrics.json` for all figures.
