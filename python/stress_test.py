"""
stress_test.py - scenario analysis and reverse stress test on the live book.

WHAT THIS DELIBERATELY DOES NOT DO: fit a macro model.
    The original spec called for interest-rate and unemployment shocks. That is not
    estimable from this data, and building it would produce a sign-flipped scenario.
    Measured on the 11 vintages available:

        corr(MOB-12 default, unemployment at origination) = -0.521
        corr(MOB-12 default, % grade A/B at origination)   = -0.908

    A naive macro regression concludes higher unemployment REDUCES defaults, because
    LendingClub tightened underwriting exactly as unemployment peaked (2007 vintage:
    29.2% grade A/B at 4.62% unemployment, 9.62% default; 2011 vintage: 73.1% A/B at
    8.93% unemployment, 3.86% default). The macro variable is anti-collinear with the
    underwriting change, n = 11, and volume grew 531x across the window. The macro
    effect is not identified. See docs/challenge-04-the-recession-that-helped.md.

    So scenarios are multiplicative PD shocks, applied WITHIN grade, with magnitudes
    anchored to observed within-grade deterioration. FRED unemployment is carried as
    context in data/seed/fred_unrate.csv and is NOT used in any calculation.

METHOD
    EL = SUM over grades of [ EAD_g x PD_g x multiplier x LGD_g ]

    EAD_g   out_prncp of the live book by grade (money currently at risk)
    PD_g    2017 vintage MOB-12 cumulative default by grade - the most recent
            vintage fully observed to MOB 12 in data ending 2018-12
    LGD_g   observed, computed vs EAD not vs funded (see below)

DECLARED BIAS: this OVERSTATES loss, on purpose but not by design
    PD_g is an ORIGINATION-COHORT rate: "of loans at month 0, how many defaulted by
    month 12". The live book is not at month 0 - median mob_observed = 12.0, mean
    14.6, and 51.8% of it is already past MOB 12. Meanwhile 42.8% of all defaults
    occur by MOB 12 and the median default lands at MOB 14.0, so the median live
    loan has already survived the peak-hazard window. Its forward 12-month risk is
    lower than a fresh loan's.
    Applying an origination PD to a seasoned book therefore overstates expected loss.
    The direction is conservative, which is tolerable in a stress test - but it is a
    known bias and it is declared here rather than left for a committee to find.
    The correct fix is a marginal hazard rate conditioned on current MOB. That needs
    survival analysis, which is out of scope and is listed as such in
    docs/assumptions_and_limitations.md.

WHY LGD IS COMPUTED vs EAD, NOT vs FUNDED
        LGD vs funded_amnt : 64.02%     <- WRONG for stressing out_prncp
        LGD vs EAD         : 89.17%     <- correct
    A loan that charges off at MOB 30 has already repaid principal, so loss as a
    share of the ORIGINAL amount is much smaller than loss as a share of the balance
    still owed. The live book is measured in out_prncp, so LGD must be on the same
    basis. Using 64% would understate stressed loss by 39%.
    EAD  = funded_amnt - total_rec_prncp
    loss = EAD - recoveries
    Note LGD vs EAD is nearly FLAT across grades (90.0% A -> 88.7% G): risk
    differentiation in unsecured consumer lending lives in PD, not LGD. The apparent
    53%->76% gradient on the funded basis is a seasoning artifact - worse grades
    default earlier, so more principal is still outstanding.

Run:  .venv/bin/python python/stress_test.py
"""

from pathlib import Path

import duckdb
import pandas as pd

DB = "data/processed/portfolio.duckdb"
SCENARIOS = "config/stress_scenarios.csv"
OUT = "outputs/stress_results.csv"
BASE_VINTAGE = 2017  # most recent vintage fully observed to MOB 12 as of 2018-12


def grade_inputs(con) -> pd.DataFrame:
    """PD (2017 vintage, MOB-12, by grade), EAD and LGD (observed, vs EAD)."""
    pd_by_grade = con.execute(f"""
        WITH f AS (
            SELECT grade, mob_observed,
                   CASE WHEN is_charged_off = 1 AND mob_default <= 12
                        THEN 1 ELSE 0 END AS d12
            FROM loan
            WHERE term_clean = '36 months' AND grade IS NOT NULL
              AND loan_status IS NOT NULL AND vintage_yr = {BASE_VINTAGE}
        )
        SELECT grade, 100.0*sum(d12)/count(*) AS pd_pct
        FROM f WHERE mob_observed >= 12
        GROUP BY grade
    """).fetchdf()

    ead = con.execute("""
        SELECT grade, count(*) AS n_loans, sum(out_prncp) AS ead
        FROM loan_live WHERE grade IS NOT NULL GROUP BY grade
    """).fetchdf()

    lgd = con.execute("""
        SELECT grade,
               100.0*(sum(funded_amnt) - sum(total_rec_prncp) - sum(recoveries))
                   / (sum(funded_amnt) - sum(total_rec_prncp)) AS lgd_pct
        FROM loan WHERE is_charged_off = 1 AND grade IS NOT NULL
        GROUP BY grade
    """).fetchdf()

    return ead.merge(pd_by_grade, on="grade").merge(lgd, on="grade").sort_values("grade")


def expected_loss(g: pd.DataFrame, mult: float) -> float:
    return float((g.ead * (g.pd_pct * mult / 100.0) * (g.lgd_pct / 100.0)).sum())


def main() -> None:
    con = duckdb.connect(DB, read_only=True)
    g = grade_inputs(con)
    total_ead = float(g.ead.sum())

    print("INPUTS - live book by grade")
    show = g.assign(
        ead_mm=(g.ead / 1e6).round(1),
        pd_pct=g.pd_pct.round(2),
        lgd_pct=g.lgd_pct.round(1),
    )[["grade", "n_loans", "ead_mm", "pd_pct", "lgd_pct"]]
    print(show.to_string(index=False))
    print(f"\n  PD  = {BASE_VINTAGE} vintage, MOB-12 cumulative, 36-month loans")
    print(f"  EAD = ${total_ead/1e9:.3f}bn outstanding across {int(g.n_loans.sum()):,} loans")
    print("  LGD = observed vs EAD (see module docstring - NOT the 64% funded-basis figure)")

    # ------------------------------------------------------------- scenarios
    scen = pd.read_csv(SCENARIOS)
    rows = []
    base_el = expected_loss(g, 1.0)
    for _, s in scen.iterrows():
        el = expected_loss(g, s.pd_multiplier)
        rows.append({
            "scenario_id": s.scenario_id,
            "scenario": s.scenario,
            "pd_multiplier": s.pd_multiplier,
            "expected_loss_mm": round(el / 1e6, 1),
            "loss_rate_pct": round(100.0 * el / total_ead, 2),
            "vs_base_mm": round((el - base_el) / 1e6, 1),
            "provenance": s.provenance.split(" - ")[0],
        })
    res = pd.DataFrame(rows)

    print("\n\nSCENARIO ANALYSIS - 12-month expected loss on the live book")
    print(res.to_string(index=False))

    # -------------------------------------------------- reverse stress test
    # No macro model needed: invert the question. What shock reaches a given loss?
    base_rate = 100.0 * base_el / total_ead
    print("\n\nREVERSE STRESS TEST - what PD shock reaches a given loss rate?")
    print("  (asks 'what breaks us', which needs no macro model at all)")
    print(f"  Base loss rate is {base_rate:.2f}%, so targets must sit ABOVE it.")
    print("  A first version of this used targets of 1-5% and returned multipliers")
    print("  below 1.0 - i.e. 'defaults would have to improve'. Meaningless. If your")
    print("  reverse stress test asks for a shock smaller than today, the threshold")
    print("  is wrong, not the book.")
    # The severe scenario's own loss rate is included as a self-check row. It is taken
    # UNROUNDED from the scenario calculation, not hardcoded: a first version pasted in
    # the displayed "13.43" and inverting that rounded figure returned 2.3302, which
    # tripped the <= 2.33 verdict and reported the Severe anchor itself as "beyond
    # observed experience". Never round-trip a rounded number through an inequality.
    severe_mult = float(scen.loc[scen.scenario_id == "S-02", "pd_multiplier"].iloc[0])
    severe_rate = 100.0 * expected_loss(g, severe_mult) / total_ead

    rev = []
    for target_pct in sorted([8.0, 10.0, severe_rate, 15.0, 20.0]):
        # EL is linear in the multiplier, so invert directly
        mult = (target_pct / 100.0 * total_ead) / base_el
        is_severe_row = abs(target_pct - severe_rate) < 1e-9
        rev.append({
            "target_loss_rate_pct": round(target_pct, 2),
            "required_pd_multiplier": round(mult, 2),
            "verdict": ("within observed experience" if mult <= severe_mult + 1e-9
                        else "BEYOND anything this book has demonstrated"),
            "note": "<- Severe scenario, inverted" if is_severe_row else "",
        })
    rdf = pd.DataFrame(rev)
    print(rdf.to_string(index=False))
    print(f"\n  Consistency check: the {severe_rate:.2f}% row must return {severe_mult}x -")
    print("  it is the Severe scenario approached from the opposite direction.")
    recovered = (severe_rate / 100.0 * total_ead) / base_el
    assert abs(recovered - severe_mult) < 1e-6, (
        f"REVERSE STRESS INCONSISTENT: inverting the severe loss rate gave "
        f"{recovered:.6f}x, but the scenario is defined at {severe_mult}x."
    )
    print("  Asserted, not eyeballed.")
    print("\n  2.33x is the largest within-grade deterioration observed 2012-2017")
    print("  (grade A: 1.16% in 2013 -> 2.70% in 2012). Anything past it is")
    print("  extrapolation beyond this book's demonstrated range, and should be")
    print("  presented to a committee as such.")

    Path("outputs").mkdir(exist_ok=True)
    res.to_csv(OUT, index=False)
    print(f"\nwritten: {OUT}")
    print("\nAll scenarios are PD shocks anchored to observed within-grade variation.")
    print("No macro model is fitted - see docs/challenge-04-the-recession-that-helped.md")
    con.close()


if __name__ == "__main__":
    main()
