# Challenge 05: I Made the Same Mistake Inside the Fix For It

> **Status:** resolved · **Date logged:** 2026-07-16 · **Severity:** high (understated every vintage curve; conclusion survived, all figures moved)

---

## 1. TL;DR

[Challenge 01](challenge-01-maturity-bias.md) is an entire document arguing that treating *unknown* as *no* fabricates trends. Its own fix then did exactly that: `mob_stopped_paying <= 12` evaluates `NULL <= 12` → `NULL` → `ELSE 0`, so 2,325 charged-off loans with no `last_pymnt_d` were counted as *"did not default by month 12."* All 2,325 repaid **exactly zero principal**, they are the fastest defaults in the book, and their timing was knowable from the column next door. Fixing it recovered **1,343 defaults** and moved every published figure. **The conclusion survived**: 2011 still the trough, 2016 still the peak, deterioration **56.6%** instead of 60.1%.

---

## 2. What happened

Challenge 01's thesis, in its own words:

> *"Censored records are not missing data and they are not negatives, they are **unknown**. Treating 'unknown' as 'no' is what fabricated the trend."*

Its fix was `sql/vintage_curve.sql`, which counts a default like this:

```sql
CASE WHEN is_charged_off = 1
      AND mob_stopped_paying <= $target_mob
     THEN 1 ELSE 0 END
```

`mob_stopped_paying` is `NULL` when `last_pymnt_d` is absent. **`NULL <= 12` evaluates to `NULL`**, which is not true, so `CASE` falls through to `ELSE 0`.

**Every loan with no `last_pymnt_d` was silently counted as "did not default by month 12."**

I had even quoted the number in Challenge 01, *"only 2,325 of 269,320 charged-off loans lack `last_pymnt_d`, 0.86%"*, and moved on. I treated it as tolerable missing data. **I never asked what those loans were.**

### What they actually are

| | Charged-off **with** `last_pymnt_d` | Charged-off **without** (the 2,325) |
|---|---|---|
| Count | 266,995 | **2,325** |
| Avg total paid | $8,340.97 | $1,426.03 |
| **Avg principal repaid** | $4,421.79 | **$0.00** |
| Never paid a cent | n/a | **848 (36.5%)** |

**All 2,325 repaid exactly zero principal.** Verified: `max(total_rec_prncp) = 0.00` across every one of them. 848 never made a payment at all; the rest paid something that went entirely to interest and fees.

These are not ambiguous records. **They are the fastest, worst defaults in the book**, and the query counted them as loans that were fine at month 12.

**And the MOB was not even unknown.** Zero principal repaid on a 36- or 60-month amortising loan says the default was immediate. The evidence was in `total_rec_prncp`, one column over. I hadn't looked.

That is the part that stings. Challenge 01 was about a *genuinely* unknown quantity, censored outcomes that truly hadn't happened yet. **This is worse: it was knowable, and I asserted a treatment without checking.**

### The size of it

For 36-month loans, **1,704** such loans were being counted as non-defaults. Across all fully-observed vintages the fix recovered **1,343 defaults** at MOB 12:

| Vintage | Before (buggy) | After (fixed) | Defaults recovered | Understated by |
|---|---|---|---|---|
| 2008 | 9.03 | 9.15 | 3 | 0.125pp |
| 2009 | 5.81 | **6.12** | 16 | **0.303pp** |
| 2010 | 4.17 | 4.41 | 22 | 0.240pp |
| 2011 | 3.86 | **4.03** | 24 | 0.170pp |
| 2012 | 5.01 | 5.13 | 51 | 0.117pp |
| 2013 | 4.15 | 4.23 | 80 | 0.080pp |
| 2014 | 4.60 | 4.66 | 93 | 0.057pp |
| 2015 | 5.20 | 5.27 | 200 | 0.071pp |
| 2016 | 6.18 | **6.31** | 406 | 0.126pp |
| 2017 | 5.52 | 5.66 | 448 | 0.140pp |

**The conclusion survived.** 2011 is still the trough, 2016 still the peak, and the deterioration is still real, **56.6%** relative rather than 60.1%. Every downstream figure moved:

| Figure | Before | After |
|---|---|---|
| 2011 → 2016 deterioration | 60.1% | **56.6%** |
| corr(default, unemployment) | −0.545 | **−0.521** |
| corr(default, % grade A/B) | −0.910 | **−0.908** |
| Grade B drift 2013→2016 | +43% | **+44%** |
| Severe scenario anchor | 2.25× | **2.33×** |
| Base / Adverse / Severe loss | 5.61 / 8.42 / 12.62% | **5.76 / 8.65 / 13.43%** |

---

## 3. Why it matters

### (a) Technical reason

**`NULL` in SQL is not false, it is unknown, and it loses every comparison silently.** `NULL <= 12` is `NULL`; `CASE WHEN NULL THEN 1 ELSE 0 END` is `0`. The language's own three-valued logic collapses "I don't know" into "no" the instant it meets a `CASE`, and it does not warn you. This is the single most common way a correct-looking SQL predicate quietly drops records.

The general defect is bigger than the SQL. **I wrote a document about a failure mode, then reproduced the failure mode in its remedy.** Understanding an error abstractly gave me no protection against committing it concretely, because the error doesn't announce itself as the thing you already know about. It shows up as a `NULL` you glanced at, quoted as a percentage, and classified as tolerable.

Fifth in the project's pattern, and the most humbling:

| # | The plausible number | The reality |
|---|---|---|
| 01 | default falling 18.00% → 1.79% | censored denominator |
| 02 | `term` HHI 5003 = "highly concentrated" | a 51/49 coin flip |
| 03 | "RUNS OK" | a comment executed against a missing table |
| 04 | unemployment ↑ → defaults ↓ | confounded by the lender's own response |
| **05** | **0.86% missing data, tolerable** | **the fastest defaults in the book, counted as healthy** |

The tell I walked past: **I quoted a null rate and never asked what the nulls were.** A null rate is a description of a *symptom*. The question is always *what is systematically different about the records that are missing this field?* Here the answer was devastating and one query away, the nulls weren't random, they were **the extreme tail of the outcome I was measuring**.

### (b) Business / regulatory reason

**Missingness that correlates with the outcome is not a data-quality nuisance. It is a bias with a direction.**

- **The direction is always flattering.** Loans that never repaid a dollar are the worst loans. Dropping them makes the book look better. Every one of the five findings on this project has erred toward the flattering answer, and that is not coincidence, it's that nobody, including me, interrogates a number that looks acceptable. Under-provisioning follows the same gradient: a censored PD understates ECL, and understated ECL flatters earnings.
- **Non-random missingness is a first-order model-validation question**, not a footnote. "What is the null rate?" is the junior version. "**Are the nulls systematically different from the observed records?**" is the one that matters, and it's the one that catches this. Any validation function worth the name asks the second.
- **The magnitude was small; that is not the defence.** 0.30pp at worst, and the conclusion held. But I had no way of knowing that *before* I checked, I classified it as tolerable based on the count being small, not on any evidence about what the records were. **A 0.86% null rate concentrated entirely in the tail of your loss distribution could just as easily have been 8.6% and reversed a finding.** The size of the error was luck. The process that produced it was not.
- **It also means the count-based triage instinct is wrong.** "Only 0.86%, move on" is exactly the reasoning that lets systematic exclusions through. The test has to be about the *nature* of the missing records, not their share.

---

## 4. Analogy

**The exit survey that only reaches people who stayed.**

You run the staff-satisfaction survey. 0.86% of employees didn't respond. Tiny. You note the response rate in a footnote and report the results.

**The 0.86% are the people who already quit.** Their laptops were deactivated, so the email bounced. They are not a random 0.86%, they are *definitionally* the least satisfied people in the company, and your survey scored them as "no complaints."

The number is small. The bias is not, because **the missingness is caused by the very outcome you're measuring.**

And the punchline is the same as mine: you didn't need better data to catch it. **You needed to ask who the non-responders were**, which was one question away, and you never asked because 0.86% sounded ignorable.

---

## 5. The fix / decision

**Four changes:**

1. **A business-rule column, separate from the raw one.** The warehouse now derives both:
   - `mob_stopped_paying`, raw, `NULL` when undated. **Kept unpatched** so its distribution (median 14.0, mean 16.1, range 0–66) can be quoted honestly.
   - `mob_default = coalesce(mob_stopped_paying, 0)` for charged-off loans, **the field curves must use**.

   Two columns rather than a patched one, because the raw distribution and the business rule are different questions and conflating them is how the next person inherits my bug.

2. **The rule is asserted at build time, not trusted.** `mob_default` is only defensible if "no `last_pymnt_d`" really does imply "zero principal repaid". So the build asserts it:

   ```python
   assert bad == 0, "MOB_DEFAULT RULE BROKEN: {bad} charged-off loans have no
                     last_pymnt_d but DID repay principal."
   ```
   If a loan ever appears that lacks the date **but repaid principal**, it cannot honestly be dated MOB-0, and the build fails rather than quietly mis-dating it.

3. **Assigning MOB 0, and why that's the honest choice.** Zero principal repaid on an amortising loan means default was immediate. MOB 0 is the earliest-possible treatment, which is what the evidence supports. It is not a guess dressed as a value: the alternative (leaving them `NULL`) is a *stronger* claim, because it asserts they didn't default by month 12, and that is demonstrably false.

4. **Every published figure re-derived and corrected.** Challenge 01 and Challenge 04 carry the new numbers; `verify_claims.py` grew assertions for the rule itself (2,325 records, all zero-principal, all dated MOB-0, 848 never paid a cent) so the correction can't silently regress.

**Why this was the right call, and why the doc exists rather than a quiet patch:** the correction is 0.3pp at worst and the conclusion held. I could have fixed the coalesce, re-run, updated the numbers, and said nothing; nobody reading the repo would have known. **The reason not to is that this is the most useful failure in the project.** Challenges 01–04 are things I caught in someone else's reasoning, or in a metric, or in a spec. **This one I caught in myself, inside the document where I explained the exact error to everyone else.** That's the one worth keeping, because it's the honest answer to "does understanding a bias protect you from it?", no. Only a check does.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `python/build_warehouse.py` | Both columns, raw `mob_stopped_paying` and rule-based `mob_default`, plus the build-time assertion that no undated charge-off ever repaid principal. |
| `sql/vintage_curve.sql` | Now reads `mob_default <= $target_mob`; the corrected verified output is in its footer. |
| `python/verify_claims.py` | Asserts the rule itself: 2,325 records, all zero-principal, all dated MOB-0, 848 never paid a cent, and re-derives all 157 published figures. |
| `outputs/vintage_naive_vs_matched.csv` | The corrected curve, regenerated. |
| `docs/challenge-01-maturity-bias.md` | Carries the correction inline rather than a silently updated table. |
| `docs/challenge-04-the-recession-that-helped.md` | All correlations, drift figures, and scenario anchors re-derived post-fix. |
| `docs/challenge-05-unknown-is-not-zero-again.md` | This file. |

