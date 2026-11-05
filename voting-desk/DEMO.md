# Demo, 5 minutes

Before starting: run `python app.py` and wait for "Ready" (about a minute). Open `results/kravrespons.html` and `results/sheets/holdout_Tesla__Inc.html` as backup.

1. **Problem, 45 s.** NBIM votes on about 110,000 proposals a year, and 94% go with the board. Accuracy says nothing here. The work is finding the votes where NBIM says no, and giving the reason.
2. **Live, 90 s.** Drop a proxy statement on the page. Show the three lanes. Every proposal has a vote and a confidence. Open one proposed vote against the board: rule, quote, fact to check, rationale in the published format.
3. **A person decides, 30 s.** Change one proposed vote, type a reason and press Log. Nothing is published without sign-off.
4. **Results, 75 s.** Open the one-pager. Say the weak parts yourself: 85.2% on the holdout against 90.8% on 2024, and a primary test with a lower bound near zero.
5. **Practice against policy, 30 s.** The chair and CEO rule softened, and NBIM's votes moved with it, from 6 of 8 to 0 of 6. Our drafts missed this because they followed precedent.
6. **Close, 30 s.** Resistance: 123 planted instructions, none reached the batch. Next: side-by-side trial with analysts.

If live fails, open the holdout sheet and say so.

## Jury questions

**Why this target, and what were the alternatives?** It measures disagreement with the board, which is what NBIM must explain. The alternatives were raw MOT and three-class accuracy. Raw MOT misleads because boards oppose some proposals themselves, and accuracy rewards never saying no. We report MOT too.

**Would you put it in production?** Not as a decision maker. As a drafting step with sign-off, after a trial beside analysts, once the team has chosen the threshold. Recall moved from 90.8% to 85.2% between years, and the interval runs from 69% to 94%.

**One more week?** Discount precedent when a guideline changes, use the model's low confidence as a routing signal, and collect documents outside the US.

**What does Claude add over the text model?** 51% against 37% precision in the queue, 9.8 points more in the batch with a lower bound near zero, and a reason a person can check. Repeating the last vote is more precise but catches less.

**What did you change after seeing the holdout?** Reporting and the exploratory agent's evidence checks, including a rounding bug that had overstated the primary test. All of it is listed in the README. The drafting code is byte-identical to the freeze.

**Does the model remember NBIM's votes?** It may. With names masked on 30 meetings, 94.1% of drafts stayed the same.
