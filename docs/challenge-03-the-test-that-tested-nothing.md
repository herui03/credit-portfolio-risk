# Challenge 03: The Test That Passed Without Testing Anything

> **Status:** resolved · **Date logged:** 2026-07-16 · **Severity:** critical (the evidence trail for two prior findings did not exist or did not run)

---

## 1. TL;DR

I wrote a test to check my committed SQL ran. It printed "RUNS OK". It had split the file on `;`, hit a semicolon inside a header comment, executed a comment-only string, received `None`, and reported success. The SQL it "validated" queried a table that did not exist. Auditing further: 4 of 10 files cited in my Evidence tables didn't exist, both `.sql` files were unrunnable, and a documented data-loss mechanism was factually wrong. I replaced ad-hoc checking with `verify_claims.py`, which re-derives all 110 figures cited in `docs/` and is itself mutation-tested.

---

## 2. What happened

Challenges [01](challenge-01-maturity-bias.md) and [02](challenge-02-hhi-cardinality.md) were both written and published. Before building the next module, I ran an audit.

### The false pass

I tested whether my committed SQL executed:

```python
sql = open("sql/vintage_curve.sql").read()
stmt = sql.split(";")[0]           # "the first statement"
con.execute(stmt, {...})
print("RUNS OK")                   # <- it printed this
```

It printed **RUNS OK**. It had validated nothing.

`vintage_curve.sql` line 18 contained a semicolon **inside a prose comment**:

```sql
--   Not a small number, no row. A gap in the chart is the honest output;
```

So `split(";")[0]` returned the first 998 characters, a **pure comment block**. DuckDB executed it, returned `None`, raised nothing, and my test reported success.

The file it "passed" queried `FROM lc`. The warehouse tables are `loan` and `loan_live`. **`lc` does not exist.** The SQL could never have run.

I only caught it because the claim was implausible: I knew the file said `lc`, so a pass was impossible. Had the table name been right and something subtler been wrong, the green light would have held.

### What the real audit found

| Check | Result |
|---|---|
| Evidence files cited in `docs/` | **4 of 10 did not exist**, `naive_vintage_trap.sql`, `profile_lendingclub.py`, `vintage_naive_vs_matched.csv`, `assumptions_and_limitations.md` |
| `sql/vintage_curve.sql` | Queried a non-existent table. **Unrunnable.** |
| `sql/concentration_hhi.sql` | Took the dimension as a bind parameter `:dim`. **No SQL engine substitutes an identifier via a parameter**, it parsed as a string literal. **Unrunnable.** |
| `python/build_warehouse.py` | Contained `WHERE id IS NOT NULL AND issue_d IS NOT NULL`, credited in its own docstring with dropping 33 rows. **The clause filtered exactly zero rows.** |

Every number in both published documents was correct. **The evidence trail behind them was fiction.**

### The 33-row error, being wrong while sounding responsible

`count(*)` on the raw file returns **2,260,701**. Any query touching a column returns **2,260,668**. Same file, same options.

`count(*)` doesn't validate columns, so it counts 33 rows the rest of the pipeline can't see. **`ignore_errors=true` discards them at parse time, silently.**

My docstring said the 33 were dropped by my `WHERE` clause and called it *"Documented, not silent."* Both halves were wrong: it wasn't my clause, and it was entirely silent. **I had written a confident, responsible-sounding sentence about a mechanism I had never inspected.**

Using `store_rejects` to capture what was actually being discarded:

| Count | Content | What it is |
|---|---|---|
| 32 | `"Total amount funded in policy code 1: 6417608175"` | export footers |
| 1 | `"Loans that do not meet the credit policy"` | section header |

They're LendingClub structural lines embedded mid-file, the CSV is concatenated quarterly exports and each export's scaffolding came along. **Not loans. Dropping them was correct.** My explanation of *why* was invention.

**Reconciliation: 2,260,701 raw lines = 2,260,668 loans + 33 structural lines.**

### The gate catching its own author

I replaced `ignore_errors` with `store_rejects` plus an assertion that all 33 rejects match the known footer pattern. **It failed immediately**, on the section header, which isn't a footer. My assertion encoded my assumption, and the assumption was 32/33 right.

That failure is the single best thing in this repo. A gate that only passes is decoration.

---

## 3. Why it matters

### (a) Technical reason

The failure mode is now familiar enough to name. All three findings on this project share one shape: **a plausible result with no error attached.**

| # | The plausible number | The reality |
|---|---|---|
| 01 | default rate falling 18.00% → 1.79% | censored denominator; truth was *rising* |
| 02 | `term` HHI 5003 = "highly concentrated" | a 51/49 coin flip, 3 points above its own floor |
| 03 | **"RUNS OK"** | a comment executed against a non-existent table |

Three in a row is a pattern, not luck. **"It ran and looked sensible" is not evidence of anything**, and the third one is the worst, because it was the thing supposed to catch the other two.

The specific bug is a parsing assumption: `split(";")` assumes semicolons only terminate statements. Prose contains semicolons. The fix strips comments *before* splitting and asserts exactly one statement survives, but the general lesson isn't about SQL parsing. It's that **a test which cannot fail is worse than no test**, because it converts an unknown into a false known. No test leaves you uncertain and careful. A false pass makes you confident and wrong.

Hence mutation testing. `verify_claims.py` is only trustworthy because I broke it on purpose and confirmed it noticed:

| Mutation | Result |
|---|---|
| Corrupt a claimed figure (6.31 → 6.99) | FAIL, exit 1 |
| Cite an evidence file that doesn't exist | FAIL, exit 1 |
| Point a committed `.sql` at a missing table | FAIL, exit 1 |
| Unmodified | **110/110, exit 0** |

### (b) Business / regulatory reason

**This is the argument for independent model validation, and I am the worked example.**

Every incentive here ran one way. I wrote the rules, I wrote the tests, I wrote the docs, and I was the one who benefited from a pass. I did not fabricate anything, every published figure was true. **I simply never checked the things that would have been inconvenient to find**, and I wrote a test whose failure mode was to agree with me. That is exactly the mechanism validation regimes exist to break, and it does not require bad faith. It requires only that the same person builds and checks.

- **Evidence trail:** in a regulated environment, a control's documentation citing files that don't exist is a finding on its own, before anyone examines whether the control works. My Evidence tables were 60% real. An auditor doesn't grade the analysis after that; they stop.
- **Reproducibility:** *"can you re-run this and get the same number?"* is the baseline question for any model or metric. My answer was no, the SQL didn't execute. Two published findings rested on ad-hoc queries typed into a shell and thrown away. **The numbers were right and I could not prove it**, which in a validation context is indistinguishable from wrong.
- **The silent-drop pattern generalises:** `ignore_errors=true` on a real feed would discard malformed *customer* records with no log line. Data completeness is a first-order control, a censored transaction feed silently understates exposure, and every downstream limit inherits the gap. The fix is cheap and it's the same one every time: **make the drop explicit, count it, assert its shape, and fail on surprise.**
- **Documentation risk:** the most dangerous sentence I wrote wasn't a wrong number. It was *"Documented, not silent"*, a confident claim about a mechanism I hadn't looked at. It would have survived any review that didn't re-run the code, because it sounded exactly like diligence.

---

## 4. Analogy

**Marking your own exam with the answer key you wrote.**

You sit the exam, then grade it against a key you also wrote. You score 100%.

The paper isn't forged, you genuinely knew most of the material, and every answer you wrote was correct. But on the three questions you were unsure about, you wrote the key to match what you'd put. Not dishonestly. You just never had a reason to check those, and no force in the room pushed back.

Then someone asks to see your working. **Four of the ten pages you cited aren't in the folder, and two of the ones that are don't add up.**

The answers were still right. **You just couldn't prove any of it, and the 100% was worth nothing**, because the grader and the candidate were the same person, and the grader never once said no.

---

## 5. The fix / decision

**Five changes:**

1. **`python/verify_claims.py`, one harness, 110 assertions.** Every figure quoted anywhere in `docs/` is re-derived from a live run against committed code. A doc and the data disagreeing fails the build with exit 1.

2. **It executes the `.sql` files as committed.** Comments are stripped *before* splitting, and it asserts exactly one statement survives, the exact bug that produced the false pass. **An evidence file that doesn't run is now a test failure, not an interview surprise.**

3. **It asserts every file named in an Evidence table exists.** The 4 missing files were written (`naive_vintage_trap.sql`, `profile_lendingclub.py`, `assumptions_and_limitations.md`, and the `vintage_naive_vs_matched.csv` artifact), and the tables can no longer drift from the filesystem.

4. **`ignore_errors` → `store_rejects` + assertions.** The build now asserts the reject count is exactly 33 **and** that every rejected row matches a known non-loan pattern. An unrecognised reject fails the build, because it might be a real loan going missing. This gate caught my own assumption on its first run.

5. **Both SQL files rewritten to actually run.** `vintage_curve.sql` targets `loan` and uses DuckDB `$param` binding. `concentration_hhi.sql` evaluates all five dimensions in one `UNION ALL` pass rather than pretending an identifier can be bound, and rewriting it surfaced a further real bug: **window functions cannot be nested**, which the harness caught on its first execution.

**Why this was the right call:** the tempting move was to quietly write the missing files, fix the SQL, and let two clean published documents stand. Nothing publicly claimed was false, I could have repaired the evidence and said nothing.

**But the repair is the least interesting part.** Challenges 01 and 02 are findings about metrics. This one is a finding about *me*, that I built the check, benefited from the pass, and wrote a check that agreed with me. That's the transferable one, and hiding it would delete the only piece of evidence in this repo that I audit my own work rather than assume it.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `python/verify_claims.py` | The harness. 110 assertions over both challenge docs; strips comments before splitting SQL (the exact bug); executes `.sql` as committed; asserts every cited evidence file exists; exit 1 on any disagreement. |
| `python/build_warehouse.py` | `store_rejects` + the reject-count and reject-pattern assertions that caught my own footer assumption. Docstring documents the `count(*)` phantom. |
| `sql/vintage_curve.sql` | Rewritten to target `loan` with `$param` binding, and the semicolon removed from the comment that caused the false pass. |
| `sql/concentration_hhi.sql` | Rewritten to `UNION ALL` across dimensions instead of binding an identifier; the nested-window-function bug the harness caught is documented in the `cumulated` CTE. |
| `docs/assumptions_and_limitations.md` | The 33-row reconciliation, the censoring assumptions, and an explicit list of what this project cannot do. |
| `Makefile` | `make verify`, the target that gates the rest. |
| `docs/challenge-03-the-test-that-tested-nothing.md` | This file. |

