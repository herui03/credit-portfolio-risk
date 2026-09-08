# Challenge 04: The Stress Test That Said Recessions Are Good For You

> **Status:** resolved · **Date logged:** 2026-07-16 · **Severity:** critical (the spec's stress test would have produced a sign-flipped scenario)

---

## 1. TL;DR

My own spec called for unemployment and interest-rate shock scenarios. Before building it I measured whether the relationship was estimable. It isn't: `corr(MOB-12 default, unemployment at origination) = −0.521`, **negative**. A naive macro stress test would forecast that doubling unemployment *reduces* losses. The cause is `corr(default, % grade A/B) = −0.908`: LendingClub tightened underwriting exactly as unemployment peaked. With n = 11 vintages and 531× volume growth, the macro effect is not identified. I built PD shocks anchored to observed within-grade variation instead, and documented why the specified version was refused.

---

## 2. What happened

Stage 3 of the spec: *" + "*, interest-rate and unemployment shocks. I wrote that line myself.

Before building it I checked whether the relationship could be estimated at all. First I verified my own claim that FRED needed no registration, half right, worth recording:

| Endpoint | Result |
|---|---|
| `fredgraph.csv?id=UNRATE` | HTTP 200, **no key**, the claim holds here |
| `api.stlouisfed.org/fred/...` | `Variable api_key is not set`, **registration required** |

Then I joined unemployment at origination to the MOB-12 vintage curve from [Challenge 01](challenge-01-maturity-bias.md):

| Vintage | Loans | MOB-12 default % | Unemployment % | % grade A/B | % grade E/F/G |
|---|---|---|---|---|---|
| 2007 | 603 | **9.62** | **4.62** | **29.2** | **31.0** |
| 2008 | 2,393 | 9.15 | 5.80 | 38.1 | 20.1 |
| 2009 | 5,281 | 6.12 | 9.28 | 50.1 | 8.9 |
| 2010 | 9,156 | 4.41 | **9.61** | 58.7 | 5.0 |
| 2011 | 14,101 | **4.03** | 8.93 | **73.1** | **2.4** |
| 2012 | 43,470 | 5.13 | 8.07 | 63.4 | 2.1 |
| 2013 | 100,422 | 4.23 | 7.36 | 57.1 | 3.8 |
| 2014 | 162,570 | 4.66 | 6.16 | 54.6 | 5.7 |
| 2015 | 283,173 | 5.27 | 5.28 | 57.2 | 3.9 |
| 2016 | 323,495 | **6.31** | 4.88 | 56.2 | 4.0 |
| 2017 | 320,419 | 5.66 | **4.36** | 57.8 | 3.8 |

```
observations available                        = 11
corr(MOB-12 default, unemployment at orig.)   = -0.521     <-- NEGATIVE
corr(MOB-12 default, % grade A/B at orig.)    = -0.908
loan volume 2007 -> 2017                      = 603 -> 320,419   (531x)
```

**The correlation with unemployment is negative.** Fit that and the model says: *unemployment rises, defaults fall.* An "unemployment doubles" scenario would show the portfolio **improving under stress**. Not merely imprecise, **the sign is inverted**, and the scenario intended to reveal risk would have concealed it.

### Why the sign inverts

Read the 2007 and 2011 rows against each other. The **worst** macro years (2009–2011, unemployment 8.93–9.61%) are exactly when LendingClub's book was **cleanest** (50.1–73.1% grade A/B). The **best** macro year in the window (2007, unemployment 4.62%) had the **dirtiest** book (29.2% A/B, 31.0% E/F/G).

**LendingClub tightened underwriting in response to the crisis.** The mitigant is inside the correlation. Unemployment and the underwriting change are near-perfectly anti-collinear, `n = 11`, and the business grew 531× across the same window, the 2007 vintage is 603 loans of a different company. There is no way to separate the macro effect from the credit-policy effect with 11 confounded points. **The macro coefficient is not identified.**

### The second finding, which fell out of the fix

Holding grade constant to strip the mix confound produced something I wasn't looking for:

| Vintage | A | B | C | D |
|---|---|---|---|---|
| 2013 | 1.16 | 2.88 | 5.25 | 7.96 |
| **2016** | **1.75** | **4.15** | **7.90** | **12.62** |
| Change | **+51%** | **+44%** | **+50%** | **+59%** |

**Every grade deteriorated internally.** A 2016 "grade B" loan defaulted **44% more** than a 2013 "grade B" loan. The label drifted, **grade inflation / rating drift**.

This falsifies an assumption underneath my own Stage 2 limits. `L-04` caps E/F/G at 8% of book; `L-07` caps grade HHI\*. **Both assume "grade" means a constant thing over time.** It doesn't. A portfolio monitored purely on grade mix would have reported a stable book across 2013–2016 while the risk inside every bucket rose 44–59%.

It also deepens Challenge 01: the 2011→2016 deterioration is **not** a mix artifact. The book got worse *within* every grade.

---

## 3. Why it matters

### (a) Technical reason

This is **confounding by the response to the exposure**, the nastiest kind, because the confounder is *caused by* the variable you're studying. Unemployment didn't just correlate with underwriting tightness; **it caused it**. You cannot control for a mediator by adding it as a regressor and reading the macro coefficient as causal.

And the identification problem is not fixable with technique. `n = 11`. Two near-perfectly anti-collinear regressors. A 531× scale change spanning a business model shift. **No specification rescues this**, no fixed effects, no lags, no instrument available in this dataset. The correct output is not a better model; it is **the decision not to fit one.**

Fourth in the project's running pattern, and the most dangerous instance:

| # | The plausible number | The reality |
|---|---|---|
| 01 | default falling 18.00% → 1.79% | censored denominator; truth was rising |
| 02 | `term` HHI 5003 = "highly concentrated" | a 51/49 coin flip |
| 03 | "RUNS OK" | a comment executed against a missing table |
| **04** | **unemployment ↑ → defaults ↓** | **confounded by the lender's own response** |

Numbers 01–03 produced wrong magnitudes. **04 produces the wrong sign**, and a stress test with an inverted sign is not a weak control, it is an argument for taking more risk into a downturn.

### (b) Business / regulatory reason

**A stress test exists to be believed at the worst possible moment.** This one would have told a committee that the recession scenario is the benign scenario.

- **The scenario silently assumes its own mitigant.** "Recession improves the book" is only true *if you also tighten underwriting, immediately, as LendingClub did.* The naive model bakes in management action that has not been approved, funded, or committed to, and presents the post-mitigation outcome as the risk. This is precisely what stress-testing governance forbids: **you stress the book you have, not the book you would have after reacting.**
- **Regulatory framing:** supervisory stress testing requires scenarios to be severe *and plausible*, with a documented, defensible transmission from macro to loss. "Unemployment doubles, losses fall, because we'd have lent to better people" is not a transmission, it's an assumption of competence under stress. It would not survive first challenge from validation.
- **Rating drift is a live control failure, not a curiosity.** My own limits (L-04, L-07) monitor grade *mix*. Across 2013–2016 the mix was roughly stable while within-grade default rose 44–59%. **The control would have shown green through the entire deterioration**, the same failure shape as Challenge 01's EWI, arrived at by a different route. Any limit denominated in an internal rating requires the rating's meaning to be monitored *separately*, or the limit is measuring a label, not a risk.
- **Small-n honesty:** eleven annual observations is not a dataset, it is an anecdote with decimal places. The regulatory instinct, long-run averages across a full cycle, with cohorts matched, exists because 11 points will always produce *a* coefficient, and it will always look like a finding.

---

## 4. Analogy

**"Rain makes driving safer."**

Pull the accident data. Wet days have **fewer** crashes per mile than dry days. The correlation is real, robust, and negative.

Now forecast: *"heavy rain is coming, expect fewer accidents."*

**Catastrophically wrong.** Rain doesn't make driving safer. **Drivers slowing down makes driving safer.** The rain caused the caution, the caution cut the crashes, and the raw correlation credited the rain. For the one driver who doesn't slow down, rain is exactly as dangerous as physics says.

That is my dataset. The recession is the rain. LendingClub tightening underwriting is the driver slowing down. Defaults fell. The correlation credited the recession.

**And the forecast is the dangerous part**: "unemployment doubles → losses fall" is only true if you also promise to slam on the brakes. **The stress test would have assumed the mitigant and reported it as the risk.**

---

## 5. The fix / decision

**Refuse the specified build. Document the refusal. Ship the honest alternative.**

1. **No macro model.** `stress_test.py` fits nothing to unemployment. The module docstring carries the −0.521 and −0.908 figures and the reasoning, so the absence reads as a decision rather than an omission.

2. **FRED is committed as context, never as an input.** `data/seed/fred_unrate.csv` is in the repo, it explains *why* the 2009–2011 vintages sit where they do, and **no calculation touches it**. Committing the extract also keeps `make demo` reproducible offline rather than dependent on a live endpoint.

3. **Scenarios are within-grade PD shocks with data-anchored magnitudes.** Working inside grade removes the mix confound. Magnitudes come from what this book has actually demonstrated at constant grade, not from an invented multiplier:

   | Scenario | Multiplier | Anchor | Loss rate |
   |---|---|---|---|
   | S-00 Base | 1.00× | 2017 observed MOB-12 by grade | **5.76%** ($548.1mm) |
   | S-01 Adverse | 1.50× | within observed 2013→2016 deterioration (+44% to +59%) | **8.65%** ($822.2mm) |
   | S-02 Severe | 2.33× | largest observed within-grade swing (grade A, 1.16%→2.70%) | **13.43%** ($1,277.1mm) |

   The scenarios remain **hypothetical**, that is stated in `provenance`. What is data-anchored is the *magnitude*, not the claim that it will happen.

4. **A reverse stress test, which needs no macro model at all.** Invert the question, *what shock reaches a given loss?*, and the identification problem disappears:

   | Target loss rate | Required PD shock | Verdict |
   |---|---|---|
   | 8.00% | 1.43× | within observed experience |
   | 10.00% | 1.78× | within observed experience |
   | 13.43% | **2.33×** | within observed experience |
   | 15.00% | 2.67× | **beyond anything this book has demonstrated** |
   | 20.00% | 3.56× | **beyond anything this book has demonstrated** |

   The 13.43% row returns exactly 2.33×, the Severe scenario reached from the opposite direction. That is a deliberate consistency check, and it passes.

5. **Rating drift is now a documented control gap.** `L-04` and `L-07` are flagged in `docs/assumptions_and_limitations.md` as resting on an assumption this stage falsified.

### Two further errors caught while building this

- **The reverse stress test was meaningless on its first run.** I set targets of 1–5% loss. Base is **5.76%**, so every target sat *below* the base case and returned multipliers under 1.0, i.e. *"defaults would have to improve."* If a reverse stress test asks for a shock smaller than today, the threshold is wrong, not the book.
- **LGD was on the wrong basis.** Computed against original `funded_amnt` it is **64.02%**; against **EAD** (balance still owed at default) it is **89.17%**. The live book is measured in `out_prncp`, so LGD must be too, the funded basis would have **understated stressed loss by 39%**. The apparent grade gradient on the funded basis (53.0% A → 76.0% G) is a **seasoning artifact**: worse grades default earlier, so more principal is still outstanding. On the correct EAD basis LGD is nearly flat (**90.0% A → 88.7% G**), in unsecured consumer lending, risk differentiation lives in PD, not LGD.

**Why this was the right call:** the spec was mine. The easy path was to fit the regression, get a coefficient, produce a chart, and satisfy the line item. It would have looked like the most quantitative module in the project. **The finding is that I specified something the data cannot support, and the honest deliverable is the refusal plus a defensible substitute**, not a model with an inverted sign wearing econometric costume.

---

## 6. Evidence

| File | What it proves |
|---|---|
| `python/stress_test.py` | The refusal, documented in code: docstring carries −0.521 / −0.908 and the reasoning. Scenarios, reverse stress test, and the declared seasoning bias. |
| `config/stress_scenarios.csv` | 3 scenarios with `rationale` **and** `provenance`, S-00 marked OBSERVED, S-01/S-02 DATA-ANCHORED with the observed swing each magnitude comes from. |
| `outputs/stress_results.csv` | Base 5.76% / Adverse 8.65% / Severe 13.43% on $9.510bn. |
| `data/seed/fred_unrate.csv` | FRED unemployment, committed for reproducibility, **used by no calculation**. |
| `python/verify_claims.py` | Re-derives every figure above from a live run; exits non-zero on disagreement. |
| `docs/assumptions_and_limitations.md` | Rating drift logged as a control gap in L-04 / L-07; survival analysis listed as out of scope. |
| `docs/challenge-04-the-recession-that-helped.md` | This file. |

