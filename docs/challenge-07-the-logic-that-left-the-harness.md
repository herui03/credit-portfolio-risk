# Challenge 07: The Logic That Left the Test Harness

> **Status:** resolved by explicit boundary, not eliminated · **Date logged:** 2026-07-16 · **Severity:** medium (structural, cannot be fixed, only bounded and declared)

---

## 1. TL;DR

Building the committee pack forced a real choice. A workbook of hardcoded numbers is a dead report a reviewer cannot trace. A workbook of formulas is traceable, **and it leaves the test harness**. Measured, not assumed: write `=A1/B1*100` with xlsxwriter, read it back with openpyxl, and the value is **`0`**, because no calculation engine ever ran. `verify_claims.py` can assert a formula's *text* and never its *result*. That is textbook EUC risk. I shipped both, source values asserted cell-by-cell against the verified CSVs, derived cells as live formulas, and drew the boundary explicitly on the Cover sheet rather than pretending it isn't there.

---

## 2. What happened

The JD names Excel first. So the pack has to be real Excel, not a CSV with a different extension. But "real Excel" means formulas, and that raised a question I decided to measure rather than assume:

```python
ws.write_number("A1", 13.275)
ws.write_number("B1", 12.0)
ws.write_formula("C1", "=A1/B1*100")
ws.write_formula("D1", '=IF(C1>100,"BREACH","PASS")')
```

Reading it back:

| Read mode | C1 | D1 |
|---|---|---|
| Formulas (`openpyxl.load_workbook`) | `'=A1/B1*100'` | `'=IF(C1>100,"BREACH","PASS")'` |
| **Values (`data_only=True`)** | **`0`** | **`0`** |

**The results are `0`.** Not wrong, *absent*. xlsxwriter writes the formula without a cached result; openpyxl does not evaluate formulas. **The only thing on this machine that can compute `=A1/B1*100` is Excel, and Excel is not in the pipeline.**

So the moment I move `utilisation = actual / threshold` out of Python and into a cell, it stops being covered by the 220 assertions in `verify_claims.py`. The harness can prove the formula *says* the right thing. It can never prove the formula *does* the right thing.

### The choice this forces

| Option | Traceable by a reviewer? | Covered by the harness? |
|---|---|---|
| All values, no formulas | ❌ dead report | ✅ every cell |
| All formulas | ✅ | ❌ nothing derived |
| **Hybrid, boundary declared** | ✅ | ✅ sources + formula text |

Neither pure option is defensible. A dead report fails the reviewer; an all-formula report fails the auditor. **The hybrid doesn't eliminate the risk, it bounds it and names it.**

### What shipped

- **Source values**, every `actual`, `threshold`, PD multiplier, loss rate, HHI, EWI reading, written as **values**, and asserted **cell-by-cell against `outputs/*.csv`** by the harness. 
- **Derived cells**, `Utilisation %` is `=E2/F2*100`; `Status` is `=IF(E2>F2,"BREACH","PASS")`. A reviewer can change a threshold in column F and watch the RAG recompute, which is the actual thing a committee does in the room.
- **The boundary**, stated on the Cover sheet, in the module docstring, and here.
- **The mitigation**, the pack is regenerated from the pipeline on every `make demo` and is **never hand-edited**. **The CSVs are the source of truth; the workbook is a rendering. If the two ever disagree, the workbook is wrong by definition.**

The harness now asserts, on the workbook itself:

| Assertion | Why |
|---|---|
| Source cells == CSV, cell by cell | the rendering cannot drift from the verified pipeline |
| `Utilisation` is `'=E2/F2*100'` | the formula text is what it should be |
| `Status` is `'=IF(E2>F2,"BREACH","PASS")'` | ditto |
| **Formula result reads `0`/`None`** | **the limitation itself is asserted, so nobody later assumes it's covered** |
| Exactly one `NO SIGNAL` row, rendering as an em-dash not `0` | Challenge 06's blind spot survives the trip into Excel |
| Cover contains all 5 caveat phrases | the pack cannot ship without its own warnings |

That fourth row is the one I care about. **The harness asserts its own blind spot.** If someone later "fixes" the pipeline so formulas cache values, that test fails and forces a conversation.

### Tested, not assumed: what happens when someone hand-edits the pack

The claim "the workbook can't drift from the pipeline" is worth nothing untested, so I simulated the exact thing that kills committee packs, *someone types a number in, just this once, for the meeting*:

```python
wb["Limits"].cell(2, 5).value = 99.999   # CA actual: 13.275 -> 99.999
wb.save("outputs/risk_committee_pack.xlsx")
```

```
FAIL  c07 Limits source cells match CSV: got 1, doc claims 0
220/221 claims verified                                  -> exit 1
```

Caught. Regenerating restored 221/221.

**So the source-cell assertion is a real control, not a convention**, stronger than I'd assumed before testing it. The residual gap is narrower and worth stating precisely: **the harness catches a hand-edit only if someone runs it.** A workbook that is edited and then emailed straight to the committee never meets the check. **The control is on the repo, not on the file**, and the file is what travels.

---

## 3. Why it matters

### (a) Technical reason

**A verification boundary you haven't located is a verification boundary you're standing on the wrong side of.**

Every other finding in this repo was a number that was wrong. This one is different: **no number is wrong. The coverage is.** `verify_claims.py` reports `220/221` and it is telling the truth, those 220 things are checked. What it cannot say, and what nobody reading a green build would think to ask, is that `Utilisation %` and `Status` on the Limits sheet are **not among them**.

That is the most dangerous property a test suite can have: **a green result whose scope is smaller than the reader assumes.** It is [Challenge 03](challenge-03-the-test-that-tested-nothing.md) again, one layer out. There, the test passed while testing nothing. Here, the test passes while testing *less than it appears to*. Both fail the same way, **by being believed beyond their reach.**

The fix is not technical. There is no way to evaluate an Excel formula from this pipeline without shipping a calculation engine. **The only honest move is to find the edge and mark it**, which is why the harness asserts the limitation as a test.

### (b) Business / regulatory reason

**This is EUC risk, and it is a named, examined category for a reason.**

- **The canonical failures are spreadsheet failures.** JPMorgan's London Whale VaR model was implemented in Excel and understated risk through a copy-paste and a divide-by-sum-instead-of-average error, a bank lost billions with a formula that no test suite covered. Reinhart-Rogoff's growth-vs-debt result, which shaped austerity policy across several countries, was a selected range that omitted rows. **Neither was a modelling failure. Both were cells nobody could test.**
- **The regulatory instinct follows directly:** spreadsheets in the risk and finance path get inventoried, version-controlled, access-restricted, and independently recalculated, precisely *because* the logic in them is invisible to normal controls. "It's in a spreadsheet" is a control finding on its own.
- **The specific danger here is that the pack is the only artifact anyone reads.** The committee never opens `outputs/limit_breaches.csv`. They open the workbook. So the artifact with the *least* test coverage in this entire repo is the one that reaches decision-makers, and that inversion is exactly why EUC risk is a category.
- **The mitigation that actually works is provenance, not testing.** I cannot test the formulas. What I can do is guarantee the workbook is **generated, never authored**: regenerated every run, never hand-edited, source of truth elsewhere. That converts an untestable artifact into a *derived* one. A hand-maintained pack has no such defence, and hand-maintained is what a committee pack becomes by month three, when someone types a number in "just this once".
- **This also puts a price on the Excel requirement itself.** The JD asks for Excel, and Excel earns its place, a reviewer can flex a threshold live in a way no CSV allows. But the honest framing in an interview is that **choosing Excel is choosing to move logic outside your controls**, and that trade should be made deliberately, with the boundary declared, rather than absorbed by default because a pack has always been a spreadsheet.

---

## 4. Analogy

**The one room in the house with no smoke detector, and it's the kitchen.**

You wire the whole house. Every bedroom, the hallway, the garage. The panel by the door glows green and it is telling the truth: every sensor reports, every one is clear.

There's no detector in the kitchen. Not because you were careless, the sensor **cannot be mounted there**, the extractor fan makes it impossible.

The panel still says **all clear**, and it still isn't lying. It's reporting on the rooms it covers.

**The kitchen is where fires start.**

The fix was never a better sensor. It's a sticker on the panel that says *"kitchen not covered"*, so nobody reads green as *"the house is safe"* when it only ever meant *"the rooms with sensors are safe."*

`verify_claims.py` reports 220/221. The kitchen is `Utilisation %` and `Status`, the two cells the committee actually looks at. **The sticker is the assertion that the formula result reads `0`.**

---

## 5. The fix / decision

**This one cannot be fixed. It can only be bounded, and the bounding is the work.**

1. **Hybrid by design, not by compromise.** Sources as values (asserted), derived as formulas (traceable). Neither pure option survives contact with both a reviewer and an auditor.

2. **The harness asserts its own blind spot.** `check("c07 formula RESULT is not verifiable (reads 0/None)", ...)`, the limitation is a *test*. If someone later changes the pipeline so formulas cache values, that assertion fails and forces the conversation rather than silently expanding coverage nobody noticed was missing.

3. **The workbook is generated, never authored.** `make demo` rebuilds it from `outputs/*.csv` every run. The CSVs are the source of truth. **If workbook and CSV disagree, the workbook is wrong by definition**, that's stated on the Cover, not just in code. This is the control that actually holds, because it converts an untestable artifact into a derived one.

4. **The caveats travel with the artifact.** The Cover sheet carries all five, thresholds ILLUSTRATIVE, `NO SIGNAL` ≠ green, the base case overstates loss, no macro model is fitted, formula results unverified, and the harness asserts every phrase is present. **The pack cannot ship without its own warnings**, because the pack is the only thing anyone reads and a caveat that lives in a repo the committee never opens is a caveat that doesn't exist.

5. **`NO SIGNAL` survives the rendering.** Challenge 06's finding is fragile in Excel: a null becomes a blank cell, and a blank cell reads as fine. The pack writes an em-dash with a distinct format, and the harness asserts it is **not** `0`.

**Why this was the right call:** the tempting move was values-only. Everything would be asserted, the harness would read 100%, and I'd never have had to write this document. **That number would have been honest about the file and dishonest about the deliverable**, a pack a reviewer can't trace isn't a risk pack, it's a screenshot. The other tempting move was formulas everywhere and silence about the coverage gap, which is what most spreadsheets in most banks actually are.

**The finding is that the artifact reaching the decision-maker has the least test coverage in the repo, and that inversion is structural rather than sloppy.** Naming it is the only available control.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `python/build_excel_pack.py` | The hybrid, with the measured `data_only=True -> 0` result in its docstring as the reason. |
| `outputs/risk_committee_pack.xlsx` | 5 sheets. Source values, live formulas, Cover carrying all 5 caveats. |
| `python/verify_claims.py` | Asserts source cells == CSV, formula text, `NO SIGNAL` renders as an em-dash not `0`, every Cover caveat present, **and asserts that the formula result is unverifiable**. |
| `outputs/concentration.csv` | Added so the pack reads only from verified artifacts rather than re-querying and risking divergence. |
| `Makefile` | `make demo` regenerates the pack every run, the provenance control that replaces the test I can't write. |
| `docs/challenge-07-the-logic-that-left-the-harness.md` | This file. |

