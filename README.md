# Credit Portfolio Risk Monitor

Exposure limits, concentration, early warning indicators and stress testing on 2,260,668 US consumer loans from the public LendingClub dataset (2007-06 to 2018-12). Every figure below is re-derived from a live run by `make verify`, and the build fails if a document and the data disagree.

Stack: SQL (DuckDB), Python (pandas, xlsxwriter), Excel, Tableau.

```bash
make setup && make data && make demo    # about 60 seconds after the download
```

## The main finding

Default rate by vintage year is the first chart in any portfolio pack. Computed the obvious way, it shows a strong improving trend:

| Vintage | Naive default % | Still `Current` % |
|---|---|---|
| 2015 | 18.00 | 10.28 |
| 2016 | 15.71 | 30.86 |
| 2017 | 8.83 | 59.03 |
| 2018 | 1.79 | 86.26 |

Default fell 90% in three years. Except that 86.26% of 2018 loans were still open, 0 to 12 months into 36- and 60-month terms. They had not had time to default, and the denominator counted every one of them as a success. That is right-censoring.

Measuring every vintage at a matched 12 months on book reverses the picture:

| Vintage | 2011 | 2013 | 2015 | 2016 | 2017 | 2018 |
|---|---|---|---|---|---|---|
| MOB-12 matched default % | 4.03 | 4.23 | 5.27 | 6.31 | 5.66 | no row (cohort too young) |

Credit quality did not improve. It deteriorated 56.6% from 2011 to 2016, and 2018 gets no number at all because it cannot be known yet. Through 2015 and 2016, while the book was moving to its worst point, the naive dashboard showed it improving. An early warning indicator with the wrong sign is worse than no indicator: it argues for loosening at the top of the cycle.

That is finding 1 of 8. The rest are in [`docs/`](docs/).

## What is in it

| Module | What it does | Output |
|---|---|---|
| Warehouse | 2,260,668 loans into DuckDB. Grain, reject-pattern and live-book-leak assertions fail the build rather than ship a bad table | `data/processed/portfolio.duckdb` |
| Exposure and limits | 7 limits on the live book (907,904 loans, $9.510bn); 4 breaches | `outputs/limit_breaches.csv` |
| Concentration | HHI and Top-N across 5 dimensions, cardinality-normalised | `outputs/concentration.csv` |
| EWI panel | First-payment default, rating drift, vintage deterioration | `outputs/ewi_panel.csv` |
| Stress testing | 3 scenarios plus a reverse stress test on $9.510bn | `outputs/stress_results.csv` |
| Excel pack | 5-sheet risk committee pack with live formulas | `outputs/risk_committee_pack.xlsx` |
| Tableau extracts | 5 grain-separated extracts plus a data dictionary | `tableau/` |
| Verification | Re-derives every figure in `docs/`; mutation-tested | `python/verify_claims.py` |

Selected results:

```
Live book        907,904 loans | $9.510bn outstanding (as of 2018-12-01)
Limits           7 evaluated | 4 BREACH
  L-02 purpose   debt_consolidation 58.42% vs 50.0% limit
  L-03 top-10    58.10% of book in 10 states vs 55.0% limit
EWI
  E-01 FPD       2018: 0.073%, 5.093x baseline, highest in the book's history   RED
  E-02 drift     2016: every grade +31.8% to +36.9% vs its own baseline         RED
  E-03 vintage   2018: NO SIGNAL, cohort not observed to MOB 12
Stress           Base 5.76% | Adverse 8.65% | Severe 13.43% loss on the live book
```

The Excel pack keeps source cells as values (asserted) and derived cells as live formulas, so a reviewer can change a threshold and watch the RAG status recompute. The Tableau folder contains verified extracts and a written build guide; the dashboard is not built yet, because Tableau is not installed on the build machine and the guide has not been executed.

## Verification

Three findings on this project were plausible numbers with no error attached. Then the test I wrote to check the SQL turned out to be broken too: it split statements on `;`, hit a semicolon inside a comment, executed a comment-only string, and printed `RUNS OK` ([challenge 03](docs/challenge-03-the-test-that-tested-nothing.md)).

So `make verify` re-derives every figure quoted anywhere in `docs/` from a live run, executes the `.sql` files as committed, asserts that every file named in an Evidence table exists, and exits non-zero on any disagreement. It is mutation-tested, because a green light that has never been seen red proves nothing:

| Mutation | Result |
|---|---|
| Corrupt a published figure | FAIL, exit 1 |
| Cite an evidence file that does not exist | FAIL, exit 1 |
| Point a committed `.sql` at a missing table | FAIL, exit 1 |
| Hand-edit a cell in the Excel pack (`13.275` to `99.999`) | FAIL, exit 1 |
| Ship a fan-trapped Tableau extract (192 rows instead of 78) | FAIL, exit 1 |
| Fill the 2018 MOB-12 NULL with `0` | FAIL, exit 1 |
| Unmodified | all claims verified, exit 0 |

It also records its own blind spot: Excel formula results cannot be verified from this pipeline, and there is a test that says so ([challenge 07](docs/challenge-07-the-logic-that-left-the-harness.md)).

## The eight findings

All eight are the same shape: a plausible number with no error attached, and every one erred toward the flattering answer.

| # | Finding | The plausible number | The reality |
|---|---|---|---|
| [01](docs/challenge-01-maturity-bias.md) | Right-censoring | default falling from 18.00% to 1.79% | censored denominator; the truth was rising |
| [02](docs/challenge-02-hhi-cardinality.md) | HHI cardinality | `term` HHI 5003 = "highly concentrated" | a 51/49 split, 3 points above its own floor |
| [03](docs/challenge-03-the-test-that-tested-nothing.md) | The false pass | `RUNS OK` | a comment executed against a missing table |
| [04](docs/challenge-04-the-recession-that-helped.md) | Confounding | unemployment up, defaults down (r = −0.521) | the lender's own response is inside the correlation |
| [05](docs/challenge-05-unknown-is-not-zero-again.md) | `NULL` is not zero | "0.86% missing, tolerable" | the fastest defaults in the book, counted as healthy |
| [06](docs/challenge-06-the-silent-panel.md) | Observability lag | a blank EWI cell | a structural blind spot on 495,242 loans |
| [07](docs/challenge-07-the-logic-that-left-the-harness.md) | EUC risk | "220/221 verified" | true, and narrower than it reads |
| [08](docs/challenge-08-the-fan-trap.md) | The fan trap | CA at $3,787.5mm | the same state, counted three times |

Each document covers what happened, why it matters technically and to a risk committee, the fix, and the files that prove it.

Finding 05 is the one worth reading first. Challenge 01 is a whole document about how treating unknown as "no" fabricates trends. My fix for it then did exactly that: `NULL <= 12` evaluates to `NULL`, falls through to `ELSE 0`, and 2,325 loans that never repaid a dollar of principal were counted as "did not default by month 12". I made the error inside the remedy for it, about ninety minutes after writing it up. Understanding the bias gave me no protection against committing it; only the check caught it. That is the practical argument for model validation being independent of the person who built the model.

## What this project does not do

| Not done | Why |
|---|---|
| Roll rate / delinquency migration | Needs a loan-month panel; this dataset is one row per loan with a single final-status snapshot. Cut once the schema was checked. |
| Macro stress testing | Not estimable here. `corr(default, unemployment) = −0.521` across 11 vintages is negative because the lender tightened underwriting as unemployment peaked (`corr(default, % grade A/B) = −0.908`). Fitting it would forecast that recessions reduce losses. |
| PD / ECL / IFRS 9 provisioning | Out of scope. The censoring work is a precondition for an unbiased lifetime PD, not a PD model. |
| Survival analysis | The MOB-matched curve is a crude discrete-time cumulative incidence that discards incomplete cohorts rather than using them as censored observations. Kaplan-Meier is the next step. |
| A default prediction model | Deliberately not fitted. This dataset makes target leakage very easy, and a leaky AUC of 0.95 is worth less than nothing. |
| The Tableau dashboard | Extracts and guide only. |

The biggest caveat: the limits are mine. Every threshold in `config/` is my judgement, and the `provenance` column reads `ILLUSTRATIVE` on every row. In a real institution limits come top-down from a board-approved risk appetite statement and are not fitted to the portfolio they police. Mine were set to be plausible against the observed book, which is circular. Read the 4 breaches as "this is how a diversification-minded lender would constrain this book", not as a violation of anything real. They are not uniformly tight: three limits pass with real headroom (L-06 at 21% utilisation, L-07 at 44%, L-04 at 81%). Full detail in [`docs/assumptions_and_limitations.md`](docs/assumptions_and_limitations.md).

## Data

LendingClub accepted loans, `wordsforthewise/lending-club` on Kaggle (392 MB gz). Real US consumer loans with real outcomes.

```
2,260,701 raw lines  =  2,260,668 loans  +  33 structural lines
```

The 33 extra lines are LendingClub export scaffolding embedded mid-file (32 export footers and 1 section header, because the published CSV is concatenated quarterly exports). The build uses `store_rejects` and asserts both the count and the pattern, because `ignore_errors=true` would drop a real loan with one bad field just as silently.

`make data` needs a Kaggle API token at `~/.kaggle/kaggle.json` (`chmod 600`). The token is read by the Kaggle CLI, never by this repo.

## Repo layout

```
Makefile                  make demo: build, profile, limits, ewi, stress, excel, tableau, verify
config/                   limits, stress scenarios, EWI thresholds; every row carries `provenance`
data/seed/                FRED unemployment, committed for reproducibility, used by no calculation
docs/                     8 challenge write-ups plus assumptions_and_limitations.md
python/                   8 modules: pipeline, monitors, verification harness
sql/                      5 files, executed as committed by the harness
tableau/                  5 grain-separated extracts, dictionary, build guide (guide unverified)
outputs/                  every artifact, regenerated on each run, never hand-edited
```

The CSVs in `outputs/` are the source of truth. The Excel pack and the Tableau extracts are renderings of them, and the harness checks that they agree.

Personal project. The data is real and public; the institution, the limits and the scenarios are not.

Herui Dou, MSc Business Analytics, NTU. [LinkedIn](https://www.linkedin.com/in/heruidou)
