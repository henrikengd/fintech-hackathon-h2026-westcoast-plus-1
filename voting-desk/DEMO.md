# Demo, 5 minutes

Before starting: run `python app.py` and wait for "Ready" (up to four minutes on a first start). Leave the agent box off. Open `Kravrespons.pdf` and, as backup, `results/sheets/sealed_China_Yangtze_Power_Co___Ltd.html`.

The sheet and the filing are seed-picked, not chosen by us. The sheet is the first meeting in the seed 2026 order of the sealed set that shows both a vote against the board and a miss. The filing is `data/meetings/us/BRCB_2026_05_27.htm`, drawn from the 2026 filings with `random.Random(2026).choice(sorted(names))`.

1. **Question, 30 s.** Speaker: ____
   "Kan en maskin gjenskape hvordan verdens største fond stemmer, og begrunne det?" No. Following the board matches 95.1%, so accuracy says nothing. A digital colleague can find which votes a stewardship manager must read before the intention is published.
2. **Live, 20 s.** Speaker: ____
   In a second tab, drop the filing on the page and leave it running, up to a minute. If it fails, say so and carry on.
3. **Sheet, 60 s.** Speaker: ____
   In the first tab, open China Yangtze Power from the sample links. Show the three lanes, then a vote, a confidence and the rule with its checked quote on item 5.
4. **One miss, 30 s.** Speaker: ____
   Item 3, the internal control auditor: we drafted FOR at High 99 and sent it to the batch. NBIM voted MOT, citing section 5.1. Items 5 and 6 go the other way: we proposed MOT and NBIM voted FOR. That pattern was right on 1 of 14 sealed rows.
5. **A person decides, 40 s.** Speaker: ____
   Enter a name at the bottom of the sheet. On item 5 change MOT to FOR, type a reason and press Log. An override with no reason is refused. Open `results/decisions.jsonl` and show the entry: name, reason, override. Nothing is published without sign-off.
6. **Results, 60 s.** Speaker: ____
   Return to the second tab and show its sheet if it has finished. If a pass gave an item two votes, the sheet says so and a person reads it. Then open the one-pager. On 1,000 meetings at companies the system was not tuned on, 92.7% reach a person and 48.4% go to the batch. Say the weak parts: lane precision 46.1%, and a local history model added after the run beats us at equal reach (-6.4 points, -13.0 to -0.7).
7. **Practice against policy, 30 s.** Speaker: ____
   NBIM voted against in 86 of 88 cases with a non-founder in both roles and 1 of 20 with a founder. After "will not" became "may not", it went from 6 of 8 to 0 of 6, and the founder sentence was gone. Precedent has to be discounted when a guideline changes.
8. **Close, 30 s.** Speaker: ____
   Eleven ideas failed tests written beforehand, and they are listed. 123 instructions planted in ballot text, none reached the batch. On 20 filings no draft followed a planted line, and the scan missed the indirect wording in all 20. Next: a trial beside a stewardship manager, and the stewardship team sets the threshold.

If live fails, stay on the sealed sheet.

## Jury answers

**Why this target, and what were the alternatives?** Whether NBIM votes differently from the board, because that decides what a person must read before publication. Vote accuracy would reward following the board, 95.1%. Literal MOT is reported beside it.

**Would you put this in production?** Not as it is. 33 of 454 votes against the board went unread, document reading is untested, and vote intentions at a third party are unsolved. A season's trial beside a stewardship manager, yes, with sign-off on every vote.

**One more week, what first?** Test document reading on filings, which the sealed test did not do, starting outside the US.

**Where does the truth come from?** The 2026 truth and the development pool came from NBIM's voting API, with keys, cleared with the organisers. The running system does not need it. `data/unseen_votes.csv` is that pull for the 751 companies. A public check: 92 sealed US pay items to 30 June, 81 FOR and 11 MOT, no conflicts, in Norges Bank's N-PX filings from SEC EDGAR.

**Your MOT precision is below following the board.** Yes: 40.3% against 59.7%. Following the board only says MOT when the board does, so it finds 9.2% of MOT votes. We find 54.7%, at the cost of false flags a person reads.

**What does the threshold do?** A proposal scoring above .22 goes to a person even when the agent follows the board. About 90% of votes against the board lay above it in 2024 and 2025 at about 1,000 other companies. It is the stewardship team's choice: .17 reads more, .28 reads less.

**Is this the evaluated version?** Three passes with version 3 routing ran on the sealed set. Changes after that run are listed in the README and touch no sealed lane. The agent box and the plugin are not that version.

**Tangen said 95 percent.** If that figure is accuracy, following the board gives 95.1% here, so we report reach and precision. We have seen no published method. We make no claim about how NBIM uses AI.

**Why not ISS?** We have no comparison. NBIM says the voting decision is its own, and we draft from its own guidelines and votes.

**Vote intentions at a third party?** Not solved. Drafts go to an outside API before publication, so this needs a setup NBIM approves. Routing could run with no outside API. Drafting needs a language model, and no local one was tested.

**Did you try a local model?** Yes. Henrik Engdal's was not as good: 44.7% at equal reach against our 48.4%, F1 42.0% against 45.3%, no vote, reason or quote, and the batch gap is not proven. Our own history model is the better local option.

**Could the model remember NBIM's votes?** We cannot rule it out. From 1 July the lane was right on 14 of 63, against 188 of 375 before, but the history model, which remembers nothing, fell the same way. With names and exact dates masked on 40 meetings, 97.8% of drafts stayed the same. That points to harder meetings, not proof.

**Did 2026 votes help you inside the test?** Barely. With history stopped at 1 January, full path: reach 92.5%, batch 48.4%, lane 46.7% and 44.3%.

**What does Claude add if a free model matches the queue?** Checked quotes and reasons, not finds. The history model clears 54.9% at equal reach against our 48.4%, and 48.5% with its record stopped at 1 January. At 438 proposals its precision is 46.3%, ours 46.1%.
