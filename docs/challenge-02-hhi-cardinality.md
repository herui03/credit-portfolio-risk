# Challenge 02: The Limit That Could Never Pass

> **Status:** resolved · **Date logged:** 2026-07-16 · **Severity:** high (would have shipped a permanently-breaching limit and a falsely comfortable one)

---

## 1. TL;DR

I applied the standard HHI concentration bands (1500 / 2500) across five portfolio dimensions. `term` scored 5003, "highly concentrated", while actually being a 51.23/48.77 split, the most balanced dimension in the book. HHI's floor is 10000/n, so on a two-bucket dimension the floor is 5000: the metric sits permanently above its own alarm threshold and can never pass. Normalising for cardinality reversed the verdict on 3 of 5 dimensions.

---

## 2. What happened

Stage 2 of the portfolio monitor computes concentration on the **live book**, 907,904 loans, **$9.510bn** outstanding as of 2018-12-01 (closed loans carry `out_prncp = 0` and are excluded; exposure limits apply to money currently at risk).

### First, the metric didn't fit the asset class at all

The spec said *"HHI + Top-10"*, inherited from a **corporate FI** module where HHI measures **single-name concentration**, one obligor being a meaningful share of the book. So I computed it:

| | |
|---|---|
| Obligors (live book) | **907,904** |
| Obligor-level HHI | **0.0179** |
| Largest single exposure | **0.000421%** of book |

**HHI ≈ 0.** In consumer lending, single-name concentration is structurally impossible, the biggest borrower is four ten-thousandths of a percent. Reporting it would be theatre. So the metric has to move to the dimensions where consumer concentration actually lives: **geography, purpose, grade**, correlated exposure, not single names.

That pivot was correct. What I did next was not.

### Then I applied the standard bands to those dimensions

| Dimension | n | HHI raw | Raw band | Largest bucket |
|---|---|---|---|---|
| addr_state | 50 | 507.1 | low | CA 13.27% |
| purpose | 14 | 4074.0 | **HIGH** | debt_consolidation 58.42% |
| grade | 7 | 2363.3 | MODERATE | C 29.94% |
| **term** | **2** | **5003.0** | **HIGH** | 51.23% |
| home_ownership | 5 | 4270.0 | **HIGH** | 54.40% |

Read that table and `term` is the most concentrated dimension in the portfolio, worse than purpose, which has 58% sitting in a single bucket.

**`term` has two values: 36 months and 60 months. The split is 51.23 / 48.77.** It is a coin flip. It is the single most balanced dimension in the entire book, and the metric flagged it as the worst.

### The mechanism

HHI is the sum of squared percentage shares. Its **minimum**, a perfectly even split across `n` buckets, is:

```
HHI_floor = n × (100/n)² = 10000/n
```

| n | Floor | Alarm line (2500) |
|---|---|---|
| 50 | 200 | reachable |
| 14 | 714 | reachable |
| 7 | 1,429 | reachable |
| **2** | **5,000** | **unreachable, floor is 2× the alarm line** |

The DOJ/FTC bands assume a market with **many** participants. On a two-bucket dimension, the best possible outcome scores 5000, double the "highly concentrated" threshold. **A raw-HHI ≤ 2500 limit on `term` can never be satisfied, by any portfolio, ever.** `term`'s actual score of 5003.0 is **three points above its own theoretical floor**.

### The correction

```
HHI* = (HHI − 10000/n) / (10000 − 10000/n)
       0.00 = perfectly balanced        1.00 = everything in one bucket
```

| Dimension | n | HHI raw | Floor | **HHI\*** | Raw band | Truth |
|---|---|---|---|---|---|---|
| addr_state | 50 | 507.1 | 200.0 | **0.031** | low | balanced *(raw agrees, by luck)* |
| purpose | 14 | 4074.0 | 714.3 | **0.362** | HIGH | ✅ **genuinely concentrated** |
| grade | 7 | 2363.3 | 1428.6 | **0.109** | MODERATE | ❌ actually balanced |
| **term** | **2** | **5003.0** | **5000.0** | **0.001** | **HIGH** | ❌❌ **most balanced dim in the book** |
| home_ownership | 5 | 4270.0 | 2000.0 | **0.284** | HIGH | ⚠️ moderate, not high |

**The raw band is wrong on three of five dimensions.** Only `purpose` survives as genuinely concentrated, 58.42% of a $9.51bn book in `debt_consolidation`, HHI* 0.362.

---

## 3. Why it matters

### (a) Technical reason

An index is only interpretable against **its own attainable range**, and HHI's range is a function of cardinality. Quoting HHI without `n` is like quoting a temperature without a scale, 40 is hot or cold depending on the unit, and 5003 is "concentrated" or "perfectly balanced" depending on `n`.

The failure is the same shape as [Challenge 01](challenge-01-maturity-bias.md), which is why I now expect it: **the arithmetic was flawless and the answer was garbage.** `sum(pct*pct) = 5003.0` is exactly right. Nothing crashed. The defect is in the *comparison*, not the computation, and a plausible number came out.

The tell was available and I walked past it: **the ranking correlated inversely with bucket count.** term (n=2) scored worst, home_ownership (n=5) next, purpose (n=14), grade (n=7), state (n=50) best. My "concentration" ranking was substantially a ranking of how few categories each dimension had.

### (b) Business / regulatory reason

**A limit that cannot be satisfied is not a control, it is noise with a governance cost.**

- **Permanent breach → alert fatigue.** L-05 on `term` under raw HHI would breach every month, forever, at every institution, regardless of the book. The committee learns within two quarters that the `term` line is always red and stops reading it. **Then it stops reading the line above it too.** Chronic false positives don't just waste attention, they train people to ignore the whole report. This is the same dynamic as AML alert flooding, and it kills controls the same way.
- **False comfort in the other direction.** `grade` reads "MODERATE" on raw HHI (2363.3) but HHI* is 0.109, balanced. Meanwhile the dimension that *is* concentrated, `purpose` at HHI* 0.362, gets the same "HIGH" label as the coin flip. **The metric cannot distinguish the real problem from the fake one.** A committee acting on this would steer origination away from a non-issue while the 58% debt-consolidation concentration sits under an identical label.
- **Provenance is the root cause.** The 1500/2500 bands are from the **US DOJ/FTC Horizontal Merger Guidelines**, an *antitrust* standard for market concentration, not a banking regulation. They're widely borrowed as a credit rule of thumb, and **the borrowing is where the "many participants" assumption gets silently dropped.** A threshold imported without its assumptions is a threshold with no derivation.
- **Model validation / audit:** the first question on any threshold is *"where did this number come from, and what does it assume?"* "Industry standard HHI" would not survive follow-up. The honest answer has to name the source, the original domain, and the assumption that transfers, or doesn't.
- **Risk appetite integrity:** limits are the operational expression of appetite. A limit that mathematically cannot pass isn't expressing appetite; it's expressing that nobody checked the metric's range before writing the policy.

---

## 4. Analogy

**"Our customers are highly concentrated, 50% men, 50% women."**

Measure a shop's customer base for "gender concentration" using HHI. A perfect 50/50 split scores **5000**, which on the DOJ scale is *highly concentrated*, the same band as a monopoly.

But 50/50 is **the most diverse a two-category variable can possibly be.** No shop on earth can pass. The scale was built for markets with dozens of firms; pointed at a two-category variable, **its floor (5000) sits above its own alarm line (2500)**. The instrument is structurally incapable of returning a passing score, and it will tell you so with total confidence, every single month.

That is exactly what `term` did. 36-month vs 60-month, split 51/49, scored 5003, flagged "highly concentrated", three points off the best score physically achievable.

---

## 5. The fix / decision

**Four changes:**

1. **All concentration limits are set on HHI\*, not raw HHI.** `config/risk_limits.csv` L-05/L-06/L-07 use normalised thresholds. The correction itself is arithmetic and not a judgement call; only the threshold lines are judgement, and they're labelled as such.

2. **Raw HHI, floor, and `n` are reported alongside HHI\*, never suppressed.** Same discipline as Challenge 01: the misleading number stays visible with the context that defuses it. `limit_monitor.py` prints `n=2 raw=5003.0 floor=5000.0` as the driver string for every HHI limit, **you cannot read the verdict without seeing the cardinality.**

3. **Obligor-level HHI is computed once and documented as ≈0, not quietly dropped.** The spec asked for it; the honest response is to run it (HHI 0.0179, largest name 0.000421%), show why it's meaningless for a consumer book, and record the pivot to dimensional concentration. Silently substituting a different metric than the one specified would be the actual error.

4. **Every threshold carries a `provenance` field, and every one currently reads `ILLUSTRATIVE`.** These are my numbers, calibrated to be plausible against the observed book. In a real institution they descend top-down from a board-approved Risk Appetite Statement and are **not fitted to the portfolio they police**. The report prints provenance next to every breach so the figure can never be mistaken for a regulatory line.

**Why this was the right call:** I could have quietly switched to HHI* and reported a clean framework. The 5003-on-a-coin-flip is the finding. "Normalise HHI for cardinality" is a one-line lesson; **"I shipped a limit that was mathematically incapable of passing, and it looked authoritative"** is the transferable one.

### Current state of the framework

7 limits, **4 breaches** on the live book:

| Limit | Driver | Actual | Threshold | Status |
|---|---|---|---|---|
| L-01 single state | CA | 13.28% | 12.0% | **BREACH** (110.6%) |
| L-02 single purpose | debt_consolidation | 58.42% | 50.0% | **BREACH** (116.8%) |
| L-03 top-10 states | top_10 | 58.10% | 55.0% | **BREACH** (105.6%) |
| L-04 sub-IG grades | E,F,G | 6.48% | 8.0% | PASS (80.9%) |
| L-05 purpose HHI* | n=14 raw=4074.0 | 0.362 | 0.30 | **BREACH** (120.6%) |
| L-06 state HHI* | n=50 raw=507.1 | 0.031 | 0.15 | PASS (20.9%) |
| L-07 grade HHI* | n=7 raw=2363.3 | 0.109 | 0.25 | PASS (43.6%) |

Under **raw** HHI, L-07 (grade, 2363.3) would also have read as a near-breach against a 2500 line, and a `term` limit would have been permanently red. The corrected framework fires on the concentration that is real, purpose, and stays quiet on the three that aren't.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `sql/concentration_hhi.sql` | HHI with floor and normalisation across all five dimensions in one pass; header documents the obligor-HHI≈0 pivot and the raw-band failure table. Runs as committed. |
| `config/risk_limits.csv` | 7 limits with rationale **and** a `provenance` column reading ILLUSTRATIVE on every row. |
| `python/limit_monitor.py` | Evaluates all limits; prints `n=… raw=… floor=…` as the driver of every HHI verdict, cardinality can't be hidden. |
| `outputs/limit_breaches.csv` | The 7-limit run: 4 breaches, 3 passes with headroom (21%–81% utilisation). |
| `python/build_warehouse.py` | Live-book definition + the assertion that no closed loan leaks in (verified 0). |
| `python/verify_claims.py` | **Re-derives every figure in this document, every HHI, floor, HHI\*, Top-N and limit, from a live run, and exits non-zero on disagreement.** |
| `docs/assumptions_and_limitations.md` | Why the limits are illustrative, and the DOJ-band provenance stated plainly. |
| `docs/challenge-02-hhi-cardinality.md` | This file. |

