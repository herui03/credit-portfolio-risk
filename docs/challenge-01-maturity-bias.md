# Challenge 01: The Portfolio That Looked Best Exactly When It Was Worst

> **Status:** resolved · **Date logged:** 2026-07-16 · **Severity:** critical (the metric was sign-flipped, not just imprecise)

---

## 1. TL;DR

I computed default rate by vintage year on 2.26M LendingClub loans and got a beautiful improving trend, 18.00% (2015) falling to 1.79% (2018). The trend was entirely fake: 86.26% of 2018 loans were still open and had not had time to default. Measuring every vintage at a matched 12 months on book reversed the finding, defaults actually **rose** from 4.03% (2011) to 6.31% (2016), a 57% relative deterioration.

---

## 2. What happened

I loaded **LendingClub accepted loans, 2007-06 to 2018-12**, **151 columns, 139 vintage months**. Grain check passed cleanly: 2,260,668 `id`, 2,260,668 distinct, **zero duplicates, one row per loan**.

> **A correction I made later, during verification.** I first wrote this section as "2,260,701 rows". That figure is what `count(*)` returns, and it is a phantom: `count(*)` doesn't validate columns, so it counts 33 rows the rest of the pipeline cannot see. They are LendingClub structural lines embedded mid-file (the CSV is concatenated quarterly exports), 32 export footers reading `"Total amount funded in policy code N: ..."` and 1 section header reading `"Loans that do not meet the credit policy"`. The honest reconciliation is **2,260,701 raw lines = 2,260,668 loans + 33 structural lines**. Details in [`docs/assumptions_and_limitations.md`](assumptions_and_limitations.md).

The obvious first portfolio metric is the default rate:

```sql
-- The query that lied
SELECT round(100.0*sum(CASE WHEN loan_status LIKE '%Charged Off%' THEN 1 ELSE 0 END)
             / count(*), 2) AS default_pct
FROM lc;
-- 11.91%
```

11.91% overall. Then I split it by vintage year, which is exactly what a portfolio EWI pack does, *is new business getting better or worse?*

| Vintage | Loans | **Naive default %** | Still `Current` % | Resolved % |
|---|---|---|---|---|
| 2014 | 235,629 | 17.47 | 5.06 | 94.68 |
| 2015 | 421,095 | **18.00** | 10.28 | 89.18 |
| 2016 | 434,407 | 15.71 | 30.86 | 67.47 |
| 2017 | 443,579 | 8.83 | 59.03 | 38.17 |
| 2018 | 495,242 | **1.79** | **86.26** | **11.37** |

**Read the naive column alone and the story is spectacular:** default rate collapsed from 18.00% to 1.79% in three years, a 90% improvement. Underwriting transformed. Put that in a risk committee pack and you would be congratulated.

**Now read the column next to it.** 86.26% of 2018 loans are still `Current`. They are 0–12 months old, on 36- and 60-month terms. **They have not had time to default yet**, and the naive metric counts every one of them as a non-default.

The denominator is the whole vintage. The numerator can only contain loans that already failed. For a young vintage those are structurally mismatched.

### The size of the lie

Restricting the denominator to **resolved** loans only (`Fully Paid` or `Charged Off`, loans whose outcome is actually known):

| Vintage | Naive default % | **Resolved-only default %** | Understatement |
|---|---|---|---|
| 2016 | 15.71 | 23.28 | **1.5×** |
| 2017 | 8.83 | 23.12 | **2.6×** |
| 2018 | 1.79 | **15.75** | **8.8×** |

The 2018 figure was understated **8.8-fold**.

### But "resolved-only" is also wrong, in the opposite direction

This is the part I nearly got wrong twice. Filtering to resolved loans does not fix the bias, it **flips** it. Among young loans, the ones that have already resolved are disproportionately *fast* outcomes: charge-offs cluster at a median of **14.0 months on book** (mean 16.1), while the full-term payoffs that dominate the good outcomes cannot resolve until month 36 or 60. So resolved-only **over**states default for young vintages, 2018's 15.75% is inflated by the same censoring, just from the other side.

**Neither denominator is right.** Both are artifacts of *when I happened to look*.

### The correct measurement: match the observation window

The only honest comparison holds **months on book (MOB)** constant, ask every vintage the same question: *how many had defaulted by month 12?*, and include only vintages old enough to have been observed that long.

I reconstructed MOB of default from `last_pymnt_d - issue_d`. **2,325 of 269,320** charged-off loans (**0.86%**) have no `last_pymnt_d`; MOB range 0–66, zero negative values.

> **A correction I made later, and it is the same error this document is about.** I first waved those 2,325 through as missing data, and the curve query read `mob_stopped_paying <= 12`. `NULL <= 12` evaluates to `NULL`, falls through to `ELSE 0`, and **counts them as "did not default by month 12."**
>
> They are not missing data. **All 2,325 repaid exactly zero principal** (verified: `max(total_rec_prncp) = 0.00` across every one; 848 never paid a cent). They are the **fastest defaults in the book**, and here the MOB was not even unknown, it was knowable from the column next door, and I hadn't looked. **I committed the "unknown is not zero" error inside the fix for the "unknown is not zero" error.**
>
> The warehouse now derives `mob_default = coalesce(mob_stopped_paying, 0)` for charged-off loans, with the zero-principal rule asserted at build time. That recovered **1,343 defaults** and moved every figure in the table below by 0.00–0.30pp. **The conclusion did not change**, 2011 is still the trough, 2016 still the peak, the deterioration still real at 56.6% instead of 60.1%. Full write-up in [`challenge-05-unknown-is-not-zero-again.md`](challenge-05-unknown-is-not-zero-again.md).

**Cumulative default by MOB 12, 36-month loans, fully-observed vintages only:**

| Vintage | Loans | **Cum. default by MOB 12 %** |
|---|---|---|
| 2011 | 14,101 | **4.03** ← trough |
| 2012 | 43,470 | 5.13 |
| 2013 | 100,422 | 4.23 |
| 2014 | 162,570 | 4.66 |
| 2015 | 283,173 | 5.27 |
| 2016 | 323,495 | **6.31** ← peak |
| 2017 | 320,419 | 5.66 |

**The trend reverses.** Credit quality did not improve, it **deteriorated 56.6% relative** from 2011 (4.03%) to 2016 (6.31%), then eased slightly in 2017.

And 2018 **is absent from the table**, because it cannot be observed to MOB 12 in data ending 2018-12. That absence is the method working: it forces you to say *"I don't know yet"* instead of reporting a fake 1.79%.

---

## 3. Why it matters

### (a) Technical reason

This is **right-censoring**: for a subset of records the outcome hasn't occurred *yet*, and the observation window is cut off. Censored records are not missing data and they are not negatives, they are **unknown**. Treating "unknown" as "no" is what fabricated the trend.

The failure mode is the dangerous one: **nothing crashed and every number was arithmetically correct.** `11.91%` is a true statement about the extract. It is simply not a statement about credit risk. The bug lives in the *question*, not the code, and the output is plausible enough to survive review.

The tell was available the whole time and I walked past it: **the metric correlated almost perfectly with vintage age.** Any risk metric that moves monotonically with how old the cohort is, is measuring age, not risk.

This is also why survival analysis exists. The MOB-matched cumulative rate is a crude, hand-rolled discrete-time survival curve, the same instinct behind Kaplan-Meier: *only compare subjects observed for the same duration.*

### (b) Business / regulatory reason

An **EWI** exists to fire before losses arrive. This one **pointed the wrong way during the exact window it needed to be right**. Through 2015–2016, when MOB-matched defaults were climbing to their 6.31% peak, the naive dashboard showed defaults falling to 1.79%. It would have read *all clear* while the book deteriorated. **An EWI with the wrong sign is worse than no EWI**, it manufactures false confidence, and it justifies loosening exactly when you should tighten.

- **IFRS 9 / ECL:** staging and lifetime ECL are built on lifetime PD. A censored PD understates PD, which understates provisions. This is not a reporting nit, it is **under-provisioning**, and it is the kind of finding that restates earnings.
- **Basel / IRB PD estimation:** regulators require PD estimated over a full observation period with maturity-matched cohorts, precisely because this error is so easy and so flattering. The requirement exists *because* people do what I did.
- **Stress testing:** every stressed scenario is a multiplier on a base-case PD. If the base case is understated 8.8×, the stress result is understated 8.8× too. **The error propagates into the scenario analysis and gets worse, not better.**
- **Model validation / audit:** "what is your denominator, and is every cohort observed for the same window?" is a first-question, not a deep-dive question. Failing it voids every downstream number, limits, appetite, capital.
- **Governance:** the naive number is the *flattering* one. That is not a coincidence, censoring bias almost always flatters recent business, which is the business the people in the room just wrote. That asymmetry is the whole argument for independent validation.

---

## 4. Analogy

**"Our newest hires are incredibly loyal."**

HR asks which joining cohort is most loyal. You count, for each cohort, the share who have quit:

- **2015 cohort:** 40% have quit.
- **2024 cohort (joined last month):** 0.5% have quit.

**Conclusion: our 2024 hires are 80× more loyal than our 2015 hires.** Obviously absurd, they've had *one month* to quit; the 2015 cohort had *nine years*. You measured tenure, not loyalty.

The fix is the same fix: ask every cohort the identical question, **"how many had quit by month 12?"**, and only include cohorts that have actually been around 12 months. The 2024 cohort simply doesn't get a number yet.

That is MOB matching. My 2018 vintage was the new hire, and I called it loyal.

---

## 5. The fix / decision

**Four changes:**

1. **MOB-matched vintage curves are the portfolio's default lens.** `sql/vintage_curve.sql` computes cumulative default by MOB, and **refuses to emit a vintage that has not been observed to the requested MOB**. A vintage with insufficient observation returns no row, not a small number. Absence is the honest output.

2. **The naive metric is kept, and shown next to the honest one.** Same discipline as P1's dual-grain evaluator: the flattering number cannot be reported alone. `outputs/vintage_naive_vs_matched.csv` always carries both, plus `still_current_pct`, because that column is the tell, and it should be impossible to look at the metric without seeing it.

3. **`still_current_pct` becomes a data-quality gate, not a footnote.** Any vintage above a censoring threshold is flagged `INSUFFICIENT_OBSERVATION` in the Excel risk pack rather than being charted. A risk committee should see a gap in the line, not a fabricated downtick.

4. **The assumption is documented, not buried.** MOB of default is reconstructed from `last_pymnt_d`, which is *when the borrower stopped paying*, typically **4–5 months earlier than the accounting charge-off date** (charge-off usually follows ~120–150 days past due). So my curves are shifted early versus a true charge-off-date curve. I chose this deliberately: **for an EWI, "stopped paying" is the better anchor**, it is the earliest observable signal, and an early-warning metric anchored to a lagging accounting event defeats its own purpose. But the shift is a real limitation and it is stated in `docs/assumptions_and_limitations.md`, not hidden.

**Why this was the right call:** I could have quietly switched to MOB-matched curves and reported the correct 4.03% → 6.31% trend. That would have been accurate and would have thrown away the finding. **The 8.8× gap, and the sign flip, is the finding.** The corrected number is a fact about LendingClub; the reversal is a transferable lesson about how portfolio metrics lie.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `sql/vintage_curve.sql` | MOB-matched vintage curve; hard-refuses cohorts below the observation window, absence instead of a fake number. Runs as committed. |
| `sql/naive_vintage_trap.sql` | The original lying query, kept deliberately, with the censoring documented in the header and `still_current_pct` welded into its output. |
| `outputs/vintage_naive_vs_matched.csv` | Both metrics side by side plus `still_current_pct`. `mob12_default_pct` is **blank for 2018**, the gate, visible in the artifact. |
| `python/profile_lendingclub.py` | Grain check (2,260,668 ids, 0 duplicates), the status distribution that exposed 86.26% `Current` in 2018, and the 33-row reconciliation. |
| `python/build_warehouse.py` | Grain + reject + live-book-leak assertions; the build fails rather than shipping a bad table. |
| `python/verify_claims.py` | **Re-derives every figure in this document from a live run and exits non-zero on disagreement.** Mutation-tested: corrupting a figure, deleting an evidence file, or breaking a `.sql` file each fail it. |
| `docs/assumptions_and_limitations.md` | The `last_pymnt_d` → MOB approximation and its 4–5 month early shift; the 33-row reconciliation; what this project deliberately cannot do. |
| `docs/challenge-01-maturity-bias.md` | This file. |

