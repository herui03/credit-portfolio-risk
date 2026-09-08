# Tableau Public, Click-by-Click Build Guide

> ## ⚠️ READ THIS BEFORE YOU TRUST A WORD BELOW
>
> Everything else in this repo is asserted by `python/verify_claims.py`, every published
> figure re-derived from a live run, build fails on disagreement.
>
> **This file is the one exception.**
>
> Tableau is not installed on the build machine and cannot be driven from the pipeline.
> A `.twbx` is a binary Tableau writes; nothing here can produce or test one.
>
> | | Status |
> |---|---|
> | `extract_*.csv` | ✅ **verified**, asserted against `outputs/*.csv` cell by cell |
> | `DATA_DICTIONARY.csv` | ✅ **verified**, generated from the extracts |
> | **This guide** | ❌ **hand-written, never executed** |
>
> Menu paths and pill behaviour vary between Tableau versions. **If a step doesn't match
> what you see, the extracts are still right, trust the data, adapt the click, and fix
> the step here.** Section 8 is how you check your work without trusting this file.

---

## 1. The two mistakes that will silently ruin this

Read these before you open Tableau. Both produce a chart that looks fine and is wrong.

### ❌ Mistake 1: joining the extracts

There are **five extracts because there are five grains.** Joining them is a **fan trap**, and it is silent.

```
limits (7 rows, one per limit)  JOIN  concentration (78 rows, one per dimension+bucket)
  ON dimension    →    192 rows

True CA exposure               $1,262.5mm
SUM(Exposure Mm) after join    $3,787.5mm      ← 3× overstated, no error
```

CA fans out to 3 rows because `addr_state` carries three limits. Tableau then sums the duplicates, doing exactly what it's designed to do.

✅ **Add each extract as its own Data Source.** One dashboard, five sources. That is normal.
🚫 Never drag two extracts onto the same canvas. Tableau's default there is a **Join**.

### ❌ Mistake 2: letting the 2018 NULL become a zero

`extract_vintage.csv` contains **exactly one NULL**: `Value` for `Metric = mob12_default_pct`, `Vintage Yr = 2018`.

That null is the finding. The 2018 cohort is 0–11 months old and **cannot** be observed to 12 months on book. Unknown is not zero.

**Tableau's trap:** `Format → Pane → Special Values → Marks → "Show at Default Position"` plots nulls at **zero**. Your line crashes to the floor at 2018, and you have just re-drawn the exact improving trend this whole project disproves.

✅ Leave Special Values on the default (**Hide**). The line should simply **stop at 2017**.
✅ Tableau will show a small **"1 null"** indicator in the bottom-right. **That's correct. Leave it.**

---

## 2. Install & connect · ~15 min

1. Download **Tableau Public** (free, native macOS): <https://public.tableau.com/app/discover>
2. Create a Tableau Public account, you need it to publish.
3. Open it. On the left: **Connect → To a File → Text file**
4. Choose:
   ```
   ~/Documents/Projects/credit-portfolio-risk/tableau/extract_vintage.csv
   ```
5. You'll land on the **Data Source** tab and see 36 rows. Good.
6. Bottom-left, click **Sheet 1**.

> Add the other four later via **Data → New Data Source**. Do it *when you need them*, not now, and never onto the same canvas.

---

## 3. Sheet 1: "The Lie and The Truth" · ~40 min

**This is the headline.** One chart, two lines, same data, opposite conclusions. Build this one properly; the rest are supporting.

### The fields you'll see

Tableau renames `snake_case` to Title Case. From `extract_vintage.csv`:

| Tableau shows | What it is |
|---|---|
| `Vintage Yr` | 2007–2018 (lands in **Measures**, you'll fix that) |
| `Value` | the metric's value |
| `Metric Label` | which line: the lie / the tell / the truth |
| `Observability Status` | why 2018 is blank |
| `N Loans` | cohort size |

### Steps

**2.1, Fix `Vintage Yr`.** It arrives as a Measure (it's a number). You want it as a continuous axis.
- Drag **`Vintage Yr`** to **Columns**. It becomes `SUM(Vintage Yr)`.
- Right-click the pill → **Dimension**.
- Right-click it again → **Continuous**. The pill turns **green**.
- ✅ *You should see:* an axis running 2007 → 2018.

**2.2, Put the metric on Rows.**
- Drag **`Value`** to **Rows** → becomes `SUM(Value)`.
- Right-click → **Measure → Average**. Now `AVG(Value)`.
- ✅ *Why AVG:* grain is one row per metric per year, so SUM and AVG are identical **today**. AVG stays correct if the grain ever changes. SUM would silently double if a year ever got two rows.

**2.3, Split into lines.**
- Drag **`Metric Label`** to **Colour**.
- ✅ *You should see:* three lines.

**2.4, Drop the third line.**
- Drag **`Metric Label`** to **Filters**.
- Tick only:
  - `Naive default % (THE LIE)`
  - `MOB-12 matched default % (the truth)`
- Leave `Still Current % (the tell)` **unticked**, it's a different scale and belongs on its own sheet.

**2.5, Marks type.**
- Marks card dropdown → **Line**.

**2.6, Tooltip.**
- Drag **`Observability Status`** to **Tooltip**.
- Drag **`N Loans`** to **Tooltip**.
- ✅ Now hovering the gap at 2018 explains itself.

**2.7, Check the null did the right thing.**

> 🚨 **Stop here and look at 2018.**
>
> - The **"THE LIE"** line should run all the way to **2018** and end at **1.79**.
> - The **"the truth"** line should **stop at 2017** (5.66). **Nothing at 2018.**
> - Bottom-right should show a small **"1 null"** indicator.
>
> **If the truth line dives to 0 at 2018, you have the bug.** Fix:
> `Format → Pane → Special Values → Marks →` set to **Hide**, not "Show at Default Position".

**2.8, Label the lines** (optional, worth it).
- Drag **`Metric Label`** to **Label** → on the Label card set **Marks to Label: Line Ends**.

**2.9, Colour.**
- Click **Colour → Edit Colours**.
- `Naive default % (THE LIE)` → a **muted grey**.
- `MOB-12 matched default % (the truth)` → a strong **red or navy**.
- ✅ *Why:* the lie should look unremarkable. It looked unremarkable to me too, that's the whole point.

**2.10, Annotate the gap.**
- Right-click empty space near 2018 → **Annotate → Area**. Type:
  > *2018 vintage: 495,242 loans. Not observed to MOB 12. Unknown ≠ zero.*

**2.11, Rename the sheet.** Double-click the tab → `The Lie and The Truth`.

### ✅ What "done" looks like
Two lines crossing: grey falling 18.00 → 1.79, red climbing 4.03 → 6.31 then **stopping**. The gap where 2018 should be is the argument.

---

## 4. Sheet 2: Concentration · ~25 min

**Data → New Data Source →** `extract_concentration.csv`. New worksheet.

**3.1, Top-10 states by exposure**
- Filter: **`Dimension`** → tick only `addr_state`
- Filter: **`Rank By Exposure`** → **At most 10**
- **Rows:** `Bucket` · **Columns:** `Exposure Mm` (SUM)
- **Colour:** `Pct Of Book`
- **Tooltip:** `Cumulative Pct`, `N Loans`
- Marks: **Bar**. Sort `Bucket` descending by `Exposure Mm`.
- ✅ CA on top at **$1,262.5mm / 13.27%**. If CA reads ~$3,788mm, **you joined the extracts**, go back to §0.

**3.2, The HHI point (this is the interesting sheet)**

Create a calculated field: **Analysis → Create Calculated Field**, name it `HHI Normalised (calc)`:

```
// HHI*, cardinality-corrected.
// Raw HHI's floor is 10000/n, so the DOJ bands (1500/2500) misfire on
// low-cardinality dimensions: `term` scores 5003 raw ("highly concentrated")
// while being a 51/49 coin flip, 3 points above its own floor.
// See docs/challenge-02-hhi-cardinality.md
( AVG([Hhi Raw]) - AVG([Hhi Floor]) ) / ( 10000 - AVG([Hhi Floor]) )
```

New sheet:
- **Rows:** `Dimension` · **Columns:** `HHI Normalised (calc)`
- **Tooltip:** `Hhi Raw`, `Hhi Floor`, `N Buckets`
- ✅ `purpose` ≈ **0.362** (genuinely concentrated). `term` ≈ **0.001**, despite raw HHI 5003.
- Put raw and normalised **side by side**. The point is that they disagree on three of five dimensions.

---

## 5. Sheet 3: EWI Panel · ~25 min

**Data → New Data Source →** `extract_ewi.csv`.

- **Rows:** `Indicator`, `Scope` · **Columns:** `Vintage Yr` (→ **Dimension**, **Discrete**, blue)
- **Text:** `Ratio Or Drift` · **Colour:** `Status`
- Marks: **Square** (a highlight table)

**Colour → Edit Colours → assign manually.** Do not let Tableau pick:

| Status value (exact) | Colour |
|---|---|
| `RED` | `#B42318` |
| `AMBER` | `#B25E09` |
| `GREEN` | `#0F766E` |
| `NO SIGNAL - cohort not observed to MOB 12` | **`#EEF1F5` pale grey** |

> **The grey is the most important colour on the dashboard.** `NO SIGNAL` must not read as green and must not read as an empty cell. It's a structural blind spot on **495,242 loans**, the largest vintage in the book. It has to look like *absence*, deliberately.

Calculated field so the blind spot is never a blank square, `EWI Label`:

```
// Renders the blind spot as text. A blank cell reads as "nothing to report".
// It is not, it is 495,242 loans nobody can see yet.
IF ISNULL(AVG([Ratio Or Drift])) THEN "no signal"
ELSE STR(ROUND(AVG([Ratio Or Drift]), 3))
END
```

Put `EWI Label` on **Text** instead of `Ratio Or Drift`.

✅ E-01 / 2018 reads **5.093**, RED. E-03 / 2018 reads **"no signal"**, grey.

---

## 6. Sheet 4: Stress · ~15 min

**Data → New Data Source →** `extract_stress.csv`.

- **Columns:** `Scenario` · **Rows:** `Loss Rate Pct` (AVG)
- **Label:** `Expected Loss Mm` · Marks: **Bar**
- Sort ascending by `Pd Multiplier`
- ✅ Base **5.76** / Adverse **8.65** / Severe **13.43**

**Worksheet → Show Caption**, paste:
> Within-grade PD shocks anchored to observed variation. No macro model is fitted: corr(default, unemployment) = −0.521 across 11 vintages, negative, because the lender tightened underwriting as unemployment peaked. See `docs/challenge-04`.

---

## 7. Dashboard · ~20 min

- **New Dashboard.** Size: **Fixed → 1200 × 900**. (Automatic renders inconsistently on Tableau Public.)
- Layout: **"The Lie and The Truth" full width across the top**, it is the argument. Concentration + EWI below. Stress bottom-right.
- Drag a **Text** object to the very top:

> **All thresholds are illustrative.** Data: LendingClub 2007–2018, real and public. Live book 907,904 loans / $9.510bn. **`NO SIGNAL` ≠ green**, 2 of 3 EWIs cannot see the 2018 vintage (495,242 loans).

- Bottom-left of the dashboard pane → **Device Preview → add a Phone layout.** Recruiters open links on phones.

---

## 8. Publish · ~10 min

**Server → Tableau Public → Save to Tableau Public As…**

- Name: `Credit Portfolio Risk Monitor, LendingClub 2007-2018`
- **Untick "Show Sheets as Tabs"**, the dashboard is the deliverable, not your working sheets.
- Copy the public URL into `README.md`.

> Tableau Public is **public by design**. That's the point, you get a link. This is public LendingClub data, so nothing sensitive is exposed. **Never do this with real customer data.**

---

## 9. Verify, do not trust this guide

This guide has never been executed. **The extracts are the truth.** Check these four before publishing:

| Check | Expected | If it's wrong |
|---|---|---|
| 2016 MOB-12 matched | **6.31** | wrong filter or measure |
| **2018 MOB-12** | **blank, no mark** | ← **you let the null become 0. Go to §0.** |
| Top-10 states cumulative | **58.10%** | you joined the extracts |
| E-01 FPD 2018 | **5.093**, RED | wrong colour mapping |

**If the 2018 point plots at zero, stop and fix it before publishing.** That single mark undoes the entire argument of the dashboard, and it is the easiest mistake to make in Tableau, the default behaviour is against you.

---

## 10. What to say in an interview

Do not claim you generated a Tableau workbook from Python. Say:

> "The pipeline emits grain-separated extracts, deliberately separate, because joining them on a shared column is a fan trap that overstates exposure 3× silently. I built the dashboard in Tableau Public from those extracts. The design decision I'd point at is the vintage chart: it has a deliberate gap at 2018, because that cohort can't be observed to twelve months on book, and Tableau's default is to plot that null at zero. Zero is a lie there. The gap is the finding."

That's honest, specific, and a thing you actually did.

---

## 11. Time budget

| | |
|---|---|
| Install & connect | 15 min |
| **Sheet 1, the headline** | **40 min** |
| Sheet 2, Concentration | 25 min |
| Sheet 3, EWI | 25 min |
| Sheet 4, Stress | 15 min |
| Dashboard | 20 min |
| Publish + verify | 15 min |
| **Total** | **~2.5 hours** |

**If you only have an hour: do §1, §2, §6, §7.** One chart that reverses its own conclusion beats four mediocre ones, and it's the only chart you'll actually get asked about.
