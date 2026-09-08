# Challenge 08: The Join That Tripled the Exposure

> **Status:** prevented by design · **Date logged:** 2026-07-16 · **Severity:** high (a silent 3× overstatement, in the layer where nobody can see the rows)

---

## 1. TL;DR

The five outputs sit at five different grains. A Tableau user who drops them into one source and joins on the shared `dimension` column gets **192 rows from 7 × 78**, and California's exposure reads **$3,787.5mm** instead of **$1,262.5mm**, a silent **3×** overstatement with no error raised. CA fans out because `addr_state` carries three limits. This is [Challenge 01](challenge-01-maturity-bias.md)'s grain lesson relocated to the BI layer, where it is *harder* to catch: a spreadsheet shows you duplicate rows, a bar chart does not. Extracts are now one file per grain, grain declared in the filename and the dictionary, and the hazard is asserted as a test.

---

## 2. What happened

Building the Tableau layer, the first question was how to shape the extract. Five artifacts, five grains:

| Artifact | Rows | Grain |
|---|---|---|
| `limit_breaches.csv` | 7 | one per `limit_id` |
| `concentration.csv` | 78 | one per (`dimension`, `bucket`) |
| `ewi_panel.csv` | 10 | one per (`ewi_id`, `scope`, `vintage_yr`) |
| `stress_results.csv` | 3 | one per `scenario_id` |
| `vintage_naive_vs_matched.csv` | 12 | one per `vintage_yr` |

The convenient move, the one a hurried analyst makes, is to flatten them into a single extract so the dashboard has one data source. `limits` and `concentration` share a `dimension` column. So join on it.

**Measured, not assumed:**

```python
merged = limits.merge(concentration, on="dimension", how="inner")
```

```
7 rows  x  78 rows   ->   192 rows

True CA exposure               $1,262.5mm
CA rows after the join          3
SUM(exposure_mm) in Tableau    $3,787.5mm      <- 3x, silently
```

**California fans out to three rows** because `addr_state` carries three limits, L-01 (single state), L-03 (top-10), L-06 (state HHI*). The join duplicates every state once per limit. Then Tableau, doing exactly what it is designed to do, sums the duplicates.

No error. No warning. **A plausible number.** For the eighth time on this project.

### Why the BI layer is the worst place for this

Challenge 01 was the same error, a grain mismatch producing a confident wrong answer, and I caught it because I could see the numbers side by side and something was off by a factor I could reason about.

**A bar chart gives you none of that.** The duplicate rows are consumed by the aggregation before anything renders. A spreadsheet at least shows you that CA appears three times. A bar labelled `CA, $3,787.5mm` shows you a bar. It looks exactly like a bar labelled `$1,262.5mm`, only taller, and "taller" is what you were looking for on a concentration chart anyway.

**The fan trap is grain error with the evidence removed.**

And the incentive runs the wrong way: 3× overstated concentration makes the chart *more* dramatic, the breach *more* severe, the analysis *more* interesting. Every pressure in the room is toward not questioning it.

---

## 3. Why it matters

### (a) Technical reason

A join multiplies rows whenever the join key is not unique on **both** sides. `dimension` is unique on neither: `addr_state` appears 3 times in limits and 50 times in concentration. The result is a **cartesian product within each key**, and every downstream aggregate inherits it.

The general rule, which I now think is the single most useful thing to carry into any BI work: **a measure is only safe to aggregate at the grain of the table it came from.** The moment you join across grains, `SUM()` stops meaning what it says, and nothing in the tool will tell you.

Tableau specifically:
- **Joins** operate on the physical layer, before aggregation → the fan trap is live.
- **Relationships** (the logical layer) aggregate each table at its own grain *before* combining → they are grain-aware and they are the correct tool.
- The default when you drag two tables onto the canvas is a **join**.

So the tool's easiest path is the wrong one. That is worth knowing before you build, not after.

Eighth in the project's pattern:

| # | The plausible number | The reality |
|---|---|---|
| 01 | default falling 18.00% → 1.79% | censored denominator |
| 02 | `term` HHI 5003 = "highly concentrated" | a 51/49 coin flip |
| 03 | "RUNS OK" | a comment executed against a missing table |
| 04 | unemployment ↑ → defaults ↓ | confounded by the lender's own response |
| 05 | "0.86% missing, tolerable" | the fastest defaults, counted as healthy |
| 06 | a blank EWI cell | a structural blind spot on 495,242 loans |
| 07 | "220/221 verified" | true, and narrower than it reads |
| **08** | **CA at $3,787.5mm** | **the same state, counted three times** |

### (b) Business / regulatory reason

**This one reaches a decision-maker faster than any other error in the repo**, because a dashboard is what gets projected on the wall.

- **It overstates concentration, which sounds conservative and isn't.** A 3× overstatement on CA turns a 13.27% share into ~40%, which would trigger every limit in the framework and demand action, reallocating origination away from a state that was never actually over-concentrated. **A false positive on a limit is not a safe error.** It burns credibility, it misallocates capital, and after the second false alarm the committee stops believing the chart. Same mechanism as [Challenge 02](challenge-02-hhi-cardinality.md)'s permanently-breaching limit, arrived at from a different direction.
- **Nobody reconciles a dashboard.** The Excel pack at least has cells someone can trace. A published Tableau viz gets read, screenshotted, pasted into a deck, and quoted six weeks later by someone who never saw the extract. **The further a number travels from its grain, the more confidently it gets quoted.**
- **This is why BI semantic layers exist.** The mature control isn't "train analysts to avoid joins", it's that measures are defined once, at a declared grain, in a governed layer, and the BI tool consumes them rather than recomputing them. My poor-man's version is one extract per grain with the grain in the filename. Not a semantic layer, but the same instinct: **make the grain impossible to lose.**
- **Data lineage is the regulatory framing.** *"Where did this number come from and at what grain was it aggregated?"* is a standard model-validation and audit question. `$3,787.5mm` has a lineage, it is just a wrong one, and it would pass any check that didn't ask about grain specifically.

---

## 4. Analogy

**Counting the guests by counting the plates.**

You need a headcount for a dinner. So you count plates.

Every guest gets a starter plate, a main plate, and a dessert plate. **You count 192 plates and report 192 guests.**

Nobody at the table looks wrong. Nobody is duplicated in any way you can *see*. Every plate is real, every plate belongs to somebody, and your arithmetic is perfect. You just answered a question about **guests** using a table whose grain is **plates**.

And the number is *high*, which for a dinner sounds like a nice problem, so nobody questions it, until you're 128 short on the actual chairs.

California got three plates because it sits under three limits. I counted plates and called it exposure.

---

## 5. The fix / decision

**Four changes:**

1. **One extract per grain. Never one joined file.** Five extracts, and `GRAINS` is a dict in `build_tableau_extracts.py` that maps every filename to its declared grain, written into `DATA_DICTIONARY.csv` and asserted in the harness. **The grain is not a comment; it is a property of the artifact.**

2. **The hazard is asserted as a test.** `verify_claims.py` performs the bad join on purpose and asserts it produces 192 rows and $3,787.5mm:

   ```python
   check("c08 naive join fans 7x78 into", len(fan), 192)
   check("c08 CA after fan trap $mm", float(ca_fan), 3787.5, tol=0.05)
   check("c08 fan trap overstates 3x", round(ca_fan / ca_true), 3)
   ```

   **The trap is a regression test.** If someone later reshapes an output and the fan trap changes shape, that fires. Documenting a hazard in prose decays; a hazard with an assertion attached does not.

3. **The guide leads with the danger, and names the tool-level fix.** "DO NOT JOIN THE EXTRACTS" is section 0 of `BUILD_GUIDE.md`, above setup, with the measured numbers. And it says what to do instead: **Relationships, not Joins**, because relationships aggregate at each table's own grain, and Tableau's default when you drag two tables together is the wrong one.

4. **The vintage extract is long, not wide, and keeps its NULL.** Reshaped to one row per (`vintage_yr`, `metric`) so the naive-vs-matched divergence is one obvious chart. The 2018 `mob12_default_pct` stays **NULL** and carries `observability_status = "NOT OBSERVED - cohort too young for MOB 12"` in the row itself. The guide's loudest instruction is **do not `ZN()` it**, Tableau's default on a continuous axis will plot that null as **0** and draw the line crashing to the floor, reinstating the exact improving trend the project exists to disprove. Asserted: exactly one NULL, and it carries its own explanation.

**Why this was the right call:** the fan trap never happened. I found it before building, in a five-line test, and the extracts were designed so it can't. **The temptation was to say nothing**, there's no scar to report, and a document about an error I avoided reads as less honest than one about an error I made.

But the reason to keep it is that **this is the first finding on this project I caught in advance rather than after publishing.** Challenges 01 through 07 are all archaeology. This one is the habit finally arriving early, and the only reason it did is that Challenge 01 taught me to ask about grain before asking about numbers. That progression is worth more than another confession.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `python/build_tableau_extracts.py` | Five extracts, one per grain; `GRAINS` dict declares each one; docstring carries the measured fan-trap numbers. |
| `tableau/DATA_DICTIONARY.csv` | 42 fields, each tagged with its extract's declared grain. |
| `tableau/BUILD_GUIDE.md` | Section 0 is the hazard, above setup. **Header states the guide itself is unverified**, Tableau is not installed and cannot be driven from the pipeline. |
| `python/verify_claims.py` | Performs the bad join deliberately and asserts 192 rows / $3,787.5mm / 3×. Asserts the 2018 NULL survives and carries its explanation. |
| `tableau/extract_vintage.csv` | Long format; exactly one NULL; `observability_status` explains it in the row. |
| `docs/challenge-08-the-fan-trap.md` | This file. |

