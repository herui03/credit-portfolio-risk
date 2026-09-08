"""
build_tableau_extracts.py - grain-separated extracts for Tableau Public.

WHY SEPARATE FILES AND NOT ONE JOINED EXTRACT
    The outputs sit at five different grains. Dropping them into one source and
    joining on a shared column is the classic fan trap, and it is silent. Measured:

        limits (7 rows, grain=limit_id) JOIN concentration (78 rows,
        grain=dimension x bucket) ON dimension  ->  192 rows

        True CA exposure            $1,262.5mm
        SUM(exposure_mm) after join $3,787.5mm     <- 3x overstated

    CA fans out to 3 rows because addr_state carries 3 limits. Tableau then
    aggregates the duplicates without complaint. No error, no warning, a plausible
    number. This is challenge-01's grain lesson relocated to the BI layer, where it
    is HARDER to see, because a spreadsheet shows you the duplicate rows and a bar
    chart does not.

    So: one extract per grain, grain declared in the filename and the dictionary.
    The build guide tells the user to keep them as separate data sources, or to use
    Tableau RELATIONSHIPS (which respect grain) rather than JOINS (which do not).

NULLS ARE LOAD-BEARING - DO NOT ZN() THEM
    extract_vintage carries mob12_default_pct = NULL for the 2018 vintage. That
    null is the challenge-01 gate: the cohort is not observed to MOB 12, and unknown
    is not zero. In Tableau, ZN() or "Show Missing Values as Zero" turns that null
    into a 0 and draws a line crashing to the floor - inventing the exact improving
    trend the whole project exists to disprove. The extract carries an explicit
    observability_status column so the null is self-documenting.

WHAT THIS SCRIPT CANNOT DO
    It cannot produce a .twbx. That is a binary Tableau writes, Tableau is not
    installed on this machine, and there is no way to drive it from here. The
    extracts below are verified; tableau/BUILD_GUIDE.md is NOT - it is untested
    instructions for software I do not have. That boundary is stated in the guide
    itself rather than left for the reader to discover.

Run:  .venv/bin/python python/build_tableau_extracts.py
"""

from pathlib import Path

import pandas as pd

OUT = Path("tableau")

# grain declared here, written into the dictionary, asserted in verify_claims.py
GRAINS = {
    "extract_vintage.csv": "one row per (vintage_yr, metric)",
    "extract_concentration.csv": "one row per (dimension, bucket)",
    "extract_ewi.csv": "one row per (ewi_id, scope, vintage_yr)",
    "extract_limits.csv": "one row per limit_id",
    "extract_stress.csv": "one row per scenario_id",
}


def main() -> None:
    OUT.mkdir(exist_ok=True)

    # ---------------------------------------------------------- vintage (headline)
    # Reshaped WIDE -> LONG. Tableau draws a multi-line chart from a long table
    # without Measure Names gymnastics, and long format is what makes the naive vs
    # MOB-matched divergence a single, obvious viz.
    v = pd.read_csv("outputs/vintage_naive_vs_matched.csv")
    long = v.melt(
        id_vars=["vintage_yr", "n_loans"],
        value_vars=["naive_default_pct", "still_current_pct", "mob12_default_pct"],
        var_name="metric", value_name="value",
    )
    label = {
        "naive_default_pct": "Naive default % (THE LIE)",
        "still_current_pct": "Still Current % (the tell)",
        "mob12_default_pct": "MOB-12 matched default % (the truth)",
    }
    long["metric_label"] = long.metric.map(label)
    # the null is a finding, not missing data - say so in the row itself
    long["observability_status"] = long.apply(
        lambda r: "NOT OBSERVED - cohort too young for MOB 12"
        if (r.metric == "mob12_default_pct" and pd.isna(r.value)) else "OBSERVED",
        axis=1,
    )
    long.to_csv(OUT / "extract_vintage.csv", index=False)

    # ---------------------------------------------------------------- the rest
    pd.read_csv("outputs/concentration.csv").to_csv(OUT / "extract_concentration.csv", index=False)
    pd.read_csv("outputs/ewi_panel.csv").to_csv(OUT / "extract_ewi.csv", index=False)
    pd.read_csv("outputs/limit_breaches.csv").to_csv(OUT / "extract_limits.csv", index=False)
    pd.read_csv("outputs/stress_results.csv").to_csv(OUT / "extract_stress.csv", index=False)

    # ------------------------------------------------------------- dictionary
    rows = []
    for fname, grain in GRAINS.items():
        df = pd.read_csv(OUT / fname)
        for c in df.columns:
            rows.append({
                "extract": fname, "grain": grain, "field": c,
                "dtype": str(df[c].dtype),
                "nulls": int(df[c].isna().sum()),
            })
    d = pd.DataFrame(rows)
    d.to_csv(OUT / "DATA_DICTIONARY.csv", index=False)

    print("TABLEAU EXTRACTS - one file per grain, never joined")
    for fname, grain in GRAINS.items():
        df = pd.read_csv(OUT / fname)
        print(f"  {fname:<30} {len(df):>3} rows  |  {grain}")
    nulls = pd.read_csv(OUT / "extract_vintage.csv")
    n_null = int(nulls.value.isna().sum())
    print(f"\n  extract_vintage carries {n_null} NULL value(s) - deliberate.")
    print("  They are the MOB-12 gate: 2018 is not observed to month 12.")
    print("  DO NOT ZN() or 'show missing as zero' - that reinstates the lie.")
    print(f"\n  written: {OUT}/DATA_DICTIONARY.csv ({len(d)} fields documented)")
    print("\n  NOT PRODUCED: a .twbx. Tableau is not installed and cannot be driven")
    print("  from here. tableau/BUILD_GUIDE.md is untested instructions - see its header.")


if __name__ == "__main__":
    main()
