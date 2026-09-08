# Challenge 06: The Early Warning Panel That Was Silent on Half the Book

> **Status:** resolved · **Date logged:** 2026-07-16 · **Severity:** high (a slow-only EWI panel reads "nothing to report" on the largest, worst vintage in the book)

---

## 1. TL;DR

I built the EWI panel and found that two of my three indicators return **nothing** for the 2018 vintage, 495,242 loans, the largest in the book, because they need 12 months on book and the cohort is 0–11 months old. A committee reading a blank column reads it as "nothing to report". **First-Payment Default is the only indicator that can speak, and it reads 0.073%, 5.09× its baseline and the highest in the book's history.** FPD is observable from ~MOB 5 instead of MOB 12, and it independently corroborates the rating drift found in [Challenge 04](challenge-04-the-recession-that-helped.md).

---

## 2. What happened

The panel, as of 2018-12-01, baseline window 2013–2015:

| EWI | Indicator | Scope | Vintage | Value | Baseline | Ratio / Drift | Status |
|---|---|---|---|---|---|---|---|
| E-01 | First-Payment Default | portfolio | 2016 | 0.032% | 0.014% | 2.233× | **AMBER** |
| E-01 | First-Payment Default | portfolio | 2017 | 0.047% | 0.014% | 3.279× | **RED** |
| E-01 | First-Payment Default | portfolio | **2018** | **0.073%** | 0.014% | **5.093×** | **RED** |
| E-02 | Rating Drift | grade A | 2016 | 1.75% | 1.27% | +36.9% | **RED** |
| E-02 | Rating Drift | grade B | 2016 | 4.15% | 3.12% | +33.0% | **RED** |
| E-02 | Rating Drift | grade C | 2016 | 7.90% | 5.99% | +31.8% | **RED** |
| E-02 | Rating Drift | grade D | 2016 | 12.62% | 9.22% | +36.8% | **RED** |
| E-03 | Vintage Deterioration | portfolio | 2016 | 6.31% | 4.72% | 1.338× | AMBER |
| E-03 | Vintage Deterioration | portfolio | 2017 | 5.66% | 4.72% | 1.199× | GREEN |
| E-03 | Vintage Deterioration | portfolio | **2018** | n/a | 4.72% | n/a | **NO SIGNAL** |

**Read the 2018 rows.** The vintage is **495,242 loans**, the largest LendingClub ever wrote, and the one currently sitting in the live book. E-02 and E-03 have nothing to say about it. Not "green". **Nothing.** They need MOB 12 and the cohort is 0–11 months old, so the [Challenge 01](challenge-01-maturity-bias.md) gate correctly refuses to emit a row.

That gate is right, a cohort not observed to MOB 12 is unknown, and unknown is not zero. **But "correctly silent" and "reassuring" look identical on a dashboard.** A committee scanning a panel of blanks and greens has no way to distinguish *"we checked and it's fine"* from *"we structurally cannot know yet."*

**And FPD, which can see, is screaming.** 0.073%, 5.09× its 2013–2015 baseline of 0.014%, monotonic since 2014, the highest in the book's history.

### Why FPD can speak when the others can't

FPD is a loan that charges off **having never made a payment**. Clean in this data:

| | |
|---|---|
| Loans with `total_pymnt = 0` | **949** |
| …of which charged off | **848** |
| …still labelled `Late (31-120 days)` | **101** |
| …with a `last_pymnt_d` (consistency check) | **0** |

The value is timing:

| Indicator | Speaks from |
|---|---|
| **FPD** | **~MOB 5** (first payment due, then 30/60/90/120 dpd → charge-off) |
| Rating drift / vintage curve | MOB 12 |

**FPD measures the underwriting decision, not the economy.** A borrower who never pays once cannot be explained by anything that happened *after* origination, no job loss, no rate move, no life event. It is a verdict on the decision at the point of sale, and it is available roughly seven months before the vintage curve can render one.

### The corroboration

| Vintage | FPD | MOB-12 vintage curve |
|---|---|---|
| 2013 | 0.012% | 4.23% |
| 2014 | 0.015% | 4.66% |
| 2015 | 0.016% | 5.27% |
| 2016 | 0.032% | 6.31% |
| 2017 | 0.047% | 5.66% |
| **2018** | **0.073%** | **unknown, too young** |

Two indicators built on entirely different mechanics, one on never-paying at month 0, one on cumulative default at month 12, both rise from 2013 to 2016. Then the slow one goes quiet and the fast one keeps climbing.

And E-02 makes it three: four independent grades drifted **+31.8% to +36.9%** from their own baselines in the same year, on 310,669 loans. **Three indicators, three mechanisms, one direction.**

### The honest part about the gate

FPD is censored too, a never-payer takes ~5 months to be *labelled* charged off, so a recent loan has already failed while the label lags. The 101 unlabelled never-payers sit at `mob_observed` 0–2, confirming it exactly. So `ewi_fpd.sql` gates on `mob_observed >= 6`.

**Measured, that gate does almost nothing:**

| | 2018 FPD |
|---|---|
| Ungated | 0.070% |
| Gated (`mob >= 6`) | **0.073%** |

**+0.003pp.** FPD is a ~0.07% event and the unlabelled population is 101 loans against 495,242. **The gate is protective, not material**, and I predicted it would matter and it didn't. It is kept because the principle generalises to a live feed where the cut-off is today and the censored share is far larger, **not** because it rescued this number. Dressing it up as rigour would be exactly the kind of thing this repo is about.

---

## 3. Why it matters

### (a) Technical reason

**A metric's observability lag is part of its specification, and it is routinely omitted.** Every indicator here is correct. The panel is still misleading, because a reader cannot tell the difference between three states that render almost identically:

| What the panel shows | What it means |
|---|---|
| GREEN | measured, and fine |
| blank /, | **structurally unknowable yet** |
| RED | measured, and bad |

The second is the dangerous one, and **it is most likely to occur exactly where the risk is newest**, because "newest" is precisely what "not yet observable" means. The blind spot isn't randomly distributed; **it sits on the freshest exposure by construction.** A panel of slow indicators is systematically blindest at the moment of maximum uncertainty.

This is the [Challenge 01](challenge-01-maturity-bias.md) lesson one layer up. There, the fix was making the vintage query refuse to emit a row for an unobserved cohort, absence instead of a fabricated downtick. That fix was right, and it created this problem: **absence is honest but it is not legible.** Suppressing a bad number and communicating that you suppressed it are two different jobs, and I'd only done the first.

The fix isn't a cleverer slow indicator. It's **pairing every slow indicator with a fast one that shares its failure mode but not its lag**, and rendering "no signal" as a distinct state rather than an empty cell.

### (b) Business / regulatory reason

**The entire purpose of an EWI framework is the "E".** An indicator that reports reliably at MOB 12 on a 36-month book is not early warning, it's history. By the time the 2018 vintage's MOB-12 curve exists, the loans are a year old, the money is out the door, and the only remaining decision is provisioning.

- **The blank column is the finding.** On this book, the 2018 vintage is 495,242 loans and a large share of the $9.510bn live book. Two of three indicators say nothing about it. **Presenting that as a panel without flagging the blindness is a reporting failure**, regardless of every individual number being right.
- **FPD is where the decision still exists.** At ~MOB 5 you can still tighten a credit policy, pull a channel, or re-underwrite a segment. That is what "early" buys, **optionality**. At MOB 12 you're calculating a loss, not preventing one.
- **FPD is also the fraud and mis-selling tripwire.** A never-paying loan points at origination: broker fraud, income misrepresentation, a leaky channel, a scorecard drifting off. **5.09× baseline is not a credit-cycle signal, it is a signal about the lender.** That is why FPD is typically monitored at the *originating channel* level, and the natural next cut here would be by `purpose` and `verification_status`.
- **Three independent corroborations, one direction.** FPD 5.09×, rating drift +31.8–36.9% across four grades, vintage curve 1.338× in 2016. Different mechanics, different observation windows, same conclusion. **A single indicator moving is noise; three unrelated ones moving together is a book.** That triangulation is the only reason I'd put weight on a 0.07% event at all.
- **This also closes a control gap I opened myself.** Limits `L-04` and `L-07` are denominated in grade and assume the label's meaning is fixed. E-02 monitors that assumption directly. **A limit denominated in an internal rating is only as good as a separate control on what the rating means**, otherwise it measures a label, not a risk.

---

## 4. Analogy

**A smoke alarm that only triggers once the fire reaches the ceiling.**

Your alarm works. It has never given a false positive. It is correctly calibrated, tested, and certified.

It just needs the fire to have been burning for twenty minutes before it makes a sound.

So the panel on your wall reads **all clear**, and it is *telling the truth*. There is genuinely no ceiling-level heat yet. The alarm is not broken and it is not lying.

**The room is full of smoke.**

The fix was never a more sensitive ceiling sensor. It's a smoke detector, **a different mechanism, at the smouldering stage, where you can still act.** The ceiling sensor stays; it confirms. But you don't hang a panel of ceiling sensors and call it fire safety, and you never let "all clear" and "not yet detectable" print the same way.

The 2018 vintage is the smoke. E-02 and E-03 are the ceiling. FPD is the smoke detector, and it reads 5.09×.

---

## 5. The fix / decision

**Five changes:**

1. **"NO SIGNAL" is a rendered state, not an empty cell.** `ewi_monitor.py` emits the literal string `NO SIGNAL - cohort not observed to MOB 12` for E-03/2018 rather than a blank or a null. It is impossible to scan the panel and mistake unknowable for fine.

2. **The panel deliberately includes an indicator that fails.** E-03 is kept **precisely because** it goes silent on 2018. Dropping it would produce a tidier panel that hides the lag. **The contrast between E-01 speaking and E-03 unable to is the deliverable**, the panel is designed to make its own blind spot visible.

3. **FPD added as the fast indicator, with an honest gate.** `sql/ewi_fpd.sql` gates on `mob_observed >= 6`. The file's own header states the gate moves 2018 by **+0.003pp** and is protective rather than material. I predicted it would matter; it didn't; the file says so.

4. **Rating drift measured within grade, against each grade's own baseline.** Working inside grade is what removes the mix confound that inverted the macro correlation in Challenge 04. Baseline is the 2013–2015 mean, declared in `config/ewi_thresholds.csv` as a judgement, with the reason (2012 and earlier are a materially different business: 603 loans in 2007 against 320,419 in 2017).

5. **Ratios report to 3dp.** At 2dp, E-03/2017 rendered as `1.20 GREEN` against an amber line of `1.20`. The raw value is 1.199, so the verdict was correct and unreadable, **a number whose displayed precision hides the basis of its own verdict invites the reader to think the panel is broken.** Same class as the reverse-stress rounding bug in `stress_test.py`: never let a rounded figure sit next to the inequality it was judged by.

### One more thing I got wrong here

`ewi_rating_drift.sql` shipped with a header block titled **VERIFIED OUTPUT** containing baselines of 3.05 / 5.85 / 9.03 and drifts of +35% to +40%. **I had estimated those before running the file.** The real figures are 3.12 / 5.99 / 9.22 and +31.8% to +36.9%.

Nothing is verified because a comment says so. The header now carries pasted output from an actual run, asserted in `verify_claims.py`, and a note recording that the first version was invented. **That is the sixth time on this project a plausible number appeared with no error attached**, this one under a heading claiming it had been checked.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `sql/ewi_fpd.sql` | FPD by vintage with the maturity gate; header states plainly that the gate moves 2018 by +0.003pp and is protective, not material. Runs as committed. |
| `sql/ewi_rating_drift.sql` | Within-grade drift vs each grade's own 2013–2015 baseline; header records that its first "VERIFIED OUTPUT" block was invented before the file was run. |
| `python/ewi_monitor.py` | The panel. Emits `NO SIGNAL - cohort not observed to MOB 12` as a rendered state; 3dp ratios so a verdict is never illegible at its own threshold. |
| `config/ewi_thresholds.csv` | 3 indicators with `baseline_definition`, `rationale` and `provenance`, all three thresholds labelled ILLUSTRATIVE. |
| `outputs/ewi_panel.csv` | The run: E-01 RED at 5.093× for 2018, E-03 NO SIGNAL for the same vintage. |
| `python/verify_claims.py` | Asserts all 203 published figures including every FPD count, every drift baseline, and the fact that E-03 has no signal for 2018 while E-01 is RED. |
| `docs/challenge-06-the-silent-panel.md` | This file. |

