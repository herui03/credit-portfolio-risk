# Assumptions & Limitations

> Every assumption this project makes, every thing it cannot do, and why. Read this
> before quoting any number from `outputs/`.
>
> Enforced by `python/verify_claims.py`, every figure cited in `docs/` is re-derived
> from a live run against committed code, and the build fails if a doc and the data
> disagree.

---

## 1. Data

| | |
|---|---|
| **Source** | LendingClub accepted loans 2007-06 → 2018-12, published on Kaggle (`wordsforthewise/lending-club`, file `accepted_2007_to_2018Q4.csv.gz`, 392 MB) |
| **Nature** | **Real, not synthetic.** Real US consumer loans, real outcomes |
| **Grain** | **One row per loan.** 2,260,668 loans, 2,260,668 distinct ids, 0 duplicates |
| **As-of date** | **2018-12-01.** Every point-in-time metric is a snapshot at this date |
| **Live book** | 907,904 loans, **$9.510bn** outstanding (`out_prncp > 0`) |

### 1.1 The 33-row reconciliation

`count(*)` on the raw file returns **2,260,701**. Any query touching a column returns **2,260,668**. Same file, same options.

The gap is real and it is not a bug in the data, it is a bug waiting to happen in the *pipeline*. `count(*)` does not validate columns, so it counts 33 rows the rest of the pipeline cannot see. `ignore_errors=true` discards them at parse time, **silently**.

Those 33 rows are LendingClub structural lines embedded mid-file (the published CSV is a concatenation of quarterly exports, and each export's scaffolding came along):

| Count | Content | What it is |
|---|---|---|
| 32 | `"Total amount funded in policy code 1: 6417608175"` | export footers |
| 1 | `"Loans that do not meet the credit policy"` | section header, the divider before the 2,749 `Does not meet the credit policy` loans |

**They are not loans. Dropping them is correct. Dropping them silently is not**, the same flag would discard a genuine loan record with one malformed field and never say so.

`build_warehouse.py` therefore uses `store_rejects=true`, asserts the reject count is exactly 33, and asserts every rejected row matches a known non-loan pattern. **An unrecognised reject fails the build.** The first version of that gate asserted all 33 were footers and failed on the section header, the gate catching its own author's assumption.

**Reconciliation: 2,260,701 raw lines = 2,260,668 loans + 33 structural lines.**

### 1.2 Columns dropped

26 of 151 columns are kept. The rest are dropped for two documented reasons:

- **Post-origination payment detail** (`total_rec_int`, `collection_recovery_fee`, `last_pymnt_amnt`, hardship and settlement fields …), these encode the outcome. They are fine for descriptive work and are **target leakage** the moment anyone fits a model here. Dropped to make the leak hard rather than to save space.
- **Secondary-applicant fields** (`sec_app_*`, `annual_inc_joint`, `revol_bal_joint` …), >90% null; `application_type` is overwhelmingly `Individual`.

`last_pymnt_d` is deliberately **kept** despite being post-origination, because the MOB reconstruction below depends on it. It is used only for **dating** an outcome, never as a feature.

---

## 2. The censoring assumption (Challenge 01)

**Right-censoring is the dominant limitation of this dataset**, and the whole vintage module is built around it. See [`challenge-01-maturity-bias.md`](challenge-01-maturity-bias.md).

- `loan_status = 'Current'` is **not a good outcome, it is an unknown outcome.** 878,317 loans (38.85%) are Current. Counting them as non-defaults understates the 2018 vintage's default rate **8.8×** (1.79% naive vs 15.75% resolved-only).
- **Resolved-only is not the fix either.** It flips the bias: charge-offs resolve at a median of **14.0 months on book** while full-term payoffs cannot resolve before month 36 or 60, so the resolved population of a young vintage is selected for failure. **Neither denominator is trustworthy.** The 2018 resolved-only figure of 15.75% must never be quoted as 2018's default rate.
- **The only honest comparison holds MOB constant.** `sql/vintage_curve.sql` returns **no row** for a cohort not observed to the target MOB. 2018 is absent from the MOB-12 curve; that absence is the method working.

### 2.1 MOB of default is reconstructed, not observed

`mob_stopped_paying = last_pymnt_d − issue_d`.

| | |
|---|---|
| Coverage | 269,320 charged-off loans; **2,325 (0.86%)** lack `last_pymnt_d` |
| Distribution | median **14.0**, mean **16.1**, range **0–66**, **0 negative** |

**This is when the borrower stopped paying, not when the loan was charged off.** Accounting charge-off typically follows 120–150 days past due, so **these curves sit roughly 4–5 months early** versus a true charge-off-date curve.

This was chosen deliberately: for an **early warning** indicator the earliest observable signal is the right anchor, and anchoring an EWI to a lagging accounting event builds the lag into the warning. But it is an approximation, and it has one sharp edge: **do not benchmark these curves against a published charge-off-date curve without adjusting for the shift**, or the 4–5 month offset will read as outperformance.

### 2.2 Vintage curves are term-segmented

36- and 60-month loans have structurally different hazard profiles. Curves are computed within a single `term`, never pooled. The headline MOB-12 series is **36-month loans only**.

---

## 3. The concentration assumptions (Challenge 02)

See [`challenge-02-hhi-cardinality.md`](challenge-02-hhi-cardinality.md).

- **Obligor-level HHI is meaningless here and is not used.** Measured: **0.0179** across 907,904 obligors, largest single exposure **0.000421%** of book. Single-name concentration is structurally impossible in consumer lending. Concentration is measured on correlated-exposure dimensions instead (state, purpose, grade).
- **All concentration limits use normalised HHI**, `HHI* = (HHI − 10000/n) / (10000 − 10000/n)`. Raw HHI's floor is `10000/n`, so the DOJ/FTC bands misfire on low-cardinality dimensions, `term` scores 5003 raw ("highly concentrated") while being a 51.23/48.77 coin flip, three points above its own floor.
- **Provenance of the 1500/2500 bands:** US DOJ/FTC *Horizontal Merger Guidelines*, an **antitrust** standard for markets with many firms, **not a banking regulation**. Widely borrowed into credit; the borrowing is where the "many participants" assumption gets dropped. Stated so nobody mistakes it for a regulatory line.

---

## 4. The limits are illustrative, this is the biggest caveat in the repo

**Every threshold in `config/risk_limits.csv` is mine.** The `provenance` column reads `ILLUSTRATIVE` on all 7 rows.

In a real institution, limits descend **top-down from a board-approved Risk Appetite Statement** and are emphatically **not fitted to the portfolio they police**. Mine were set to be plausible against the observed book, which is circular, and I can't fully rule out that they're simply tuned to be interesting.

The honest reading of the 4 breaches is: **"this is how a diversification-minded lender would constrain this book"**, never *"this book is in violation"* of anything real.

Partial defence: they are not uniformly tight. Three limits pass with genuine headroom (L-06 at 21% utilisation, L-07 at 44%, L-04 at 81%). Had I calibrated for drama, everything would breach.

---

## 5. What this project deliberately does NOT do

| Not done | Why |
|---|---|
| **Roll rate / delinquency migration** | **The data cannot support it.** Roll rates need a loan-month panel; this dataset is one row per loan with a single final-status snapshot. There are no monthly performance records. This was in the original spec and was cut once the schema was checked, claiming it would be claiming a measurement that does not exist. The proper dataset for it is Freddie Mac / Fannie Mae single-family loan performance, which is a real monthly panel. |
| **Monthly concentration drift** | Same reason, no monthly balances. Concentration is measured at the as-of snapshot, and drift can only be shown by **origination month**, which is a different (and legitimate) metric: concentration of *new business*, not of the book. |
| **PD / ECL / IFRS 9 provisioning** | Out of scope. The censoring work here is a *precondition* for an unbiased lifetime PD, not a PD model. Nothing in `outputs/` should be used as a PD. |
| **Survival analysis (Kaplan-Meier / hazard models)** | The MOB-matched curve is a crude discrete-time cumulative-incidence estimate. It **discards** incomplete cohorts rather than using them as censored observations. Proper survival analysis would use them. This is the honest next step, not a claim of what's here. |
| **A default prediction model** | Deliberately not fitted. The post-origination columns in this dataset make leakage almost effortless, and a leaky AUC of 0.95 would be worth less than nothing. |

---

## 6. Reproducibility

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python python/build_warehouse.py      # ~14s, asserts grain + rejects + leak
.venv/bin/python python/profile_lendingclub.py  # honest profile + naive-vs-matched CSV
.venv/bin/python python/limit_monitor.py        # 7 limits -> 4 breaches
.venv/bin/python python/verify_claims.py        # re-derives every figure cited in docs/
```

`verify_claims.py` is the control that matters. It:

1. Executes the `.sql` files **as committed**, an evidence file that doesn't run is a test failure, not an interview surprise.
2. Re-derives every number quoted in `docs/` and fails loudly on any disagreement.
3. Asserts every file named in an Evidence table actually exists.

It exists because three separate findings on this project were **plausible numbers with no error attached**, a censored denominator, an index read against the wrong range, and a test harness that split SQL on `;`, hit a semicolon inside a comment, executed a comment-only string, and reported "RUNS OK". Three in a row is a pattern, not bad luck. "It ran and looked sensible" is not evidence of anything.

---

## 7. Known gaps in this document

- Limit thresholds have no external anchor and I've said so, but "illustrative" is a weaker position than "derived from an appetite statement". If this project continued, deriving even one limit from a published bank's disclosed appetite would be the highest-value upgrade.
- The 4–5 month charge-off timing shift (§2.1) is asserted from industry convention, **not measured from this data**, the dataset has no charge-off date to measure it against. It is an assumption about an assumption, and it is the softest claim in the repo.
