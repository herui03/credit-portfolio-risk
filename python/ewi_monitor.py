"""
ewi_monitor.py - early warning indicator panel.

Three indicators, deliberately including one that CANNOT speak about the newest
vintage, because the point of the panel is the contrast:

    E-01  First-Payment Default    speaks from ~MOB 5    2018: 0.073%, highest ever
    E-02  Rating Drift             speaks from  MOB 12   2018: SILENT
    E-03  Vintage Deterioration    speaks from  MOB 12   2018: SILENT

The 2018 vintage is 495,242 loans. Two of the three indicators return nothing for
it - the cohort is not observed to MOB 12, and unknown is not zero (challenge-01).
FPD is the only one that can speak, and it is reading ~5x its baseline.

That contrast IS the deliverable. A committee shown only the slow indicators would
see a blank column for the newest, largest vintage in the book and read it as
"nothing to report".

WHY EACH INDICATOR EARNS ITS PLACE
    E-01 FPD          - earliest signal; measures the underwriting DECISION, since a
                        borrower who never pays once cannot be explained by anything
                        that happened after origination.
    E-02 Rating Drift - closes the gap under limits L-04 / L-07, which are
                        denominated in grade and assume the label's meaning is fixed.
                        Measured WITHIN grade against each grade's own baseline,
                        which is what removes the mix confound (challenge-04).
    E-03 Vintage       - the slow confirmatory one. Kept to make the lag visible.

Thresholds are ILLUSTRATIVE - see config/ewi_thresholds.csv. In a real institution
they descend from a risk appetite statement and are not fitted to the book they police.

Run:  .venv/bin/python python/ewi_monitor.py
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

DB = "data/processed/portfolio.duckdb"
THRESHOLDS = "config/ewi_thresholds.csv"
OUT = "outputs/ewi_panel.csv"
BASELINE_FROM, BASELINE_TO = 2013, 2015


def run_sql_file(con, path):
    """Execute a .sql file as committed - comments stripped before splitting, so a
    semicolon in prose cannot silently truncate the statement (challenge-03)."""
    stripped = re.sub(r"--[^\n]*", "", Path(path).read_text())
    stmts = [s.strip() for s in stripped.split(";") if s.strip()]
    assert len(stmts) == 1, f"{path}: expected 1 statement, found {len(stmts)}"
    return con.execute(stmts[0]).fetchdf()


def rag(value, amber, red):
    """Traffic-light a value against its thresholds.

    Ratios are reported to 3dp, not 2. At 2dp the 2017 vintage displayed as
    "1.20 GREEN" against an amber line of 1.20 - the raw value is 1.199, so the
    verdict was right and unreadable. A number whose displayed precision hides the
    basis of its own verdict invites the reader to think the panel is broken. Same
    class as the reverse-stress bug in stress_test.py: never let a rounded figure
    sit next to the inequality it was judged by.
    """
    if value >= red:
        return "RED"
    if value >= amber:
        return "AMBER"
    return "GREEN"


def main() -> None:
    con = duckdb.connect(DB, read_only=True)
    th = pd.read_csv(THRESHOLDS).set_index("ewi_id")
    rows = []

    # ---------------------------------------------------------------- E-01 FPD
    fpd = run_sql_file(con, "sql/ewi_fpd.sql").set_index("vintage_yr")
    fpd_base = fpd.loc[BASELINE_FROM:BASELINE_TO, "fpd_pct"].mean()
    t = th.loc["E-01"]
    for yr in range(2016, 2019):
        ratio = fpd.loc[yr, "fpd_pct"] / fpd_base
        rows.append({
            "ewi_id": "E-01", "indicator": "First-Payment Default", "scope": "portfolio",
            "vintage_yr": yr, "value": round(fpd.loc[yr, "fpd_pct"], 3),
            "baseline": round(fpd_base, 3), "ratio_or_drift": round(ratio, 3),
            "status": rag(ratio, t.amber, t.red),
        })

    # -------------------------------------------------------- E-02 rating drift
    dr = run_sql_file(con, "sql/ewi_rating_drift.sql")
    t = th.loc["E-02"]
    for _, r in dr[dr.vintage_yr == 2016].iterrows():
        if r.grade not in list("ABCD"):
            continue
        rows.append({
            "ewi_id": "E-02", "indicator": "Rating Drift", "scope": f"grade {r.grade}",
            "vintage_yr": 2016, "value": round(r.mob12_pct, 2),
            "baseline": round(r.baseline_pct, 2), "ratio_or_drift": round(r.drift_pct, 1),
            "status": rag(r.drift_pct, t.amber, t.red),
        })

    # -------------------------------------------------- E-03 vintage (the slow one)
    vc = con.execute(f"""
        WITH f AS (
            SELECT vintage_yr, mob_observed,
                   CASE WHEN is_charged_off=1 AND mob_default<=12 THEN 1 ELSE 0 END AS d12
            FROM loan WHERE term_clean='36 months' AND loan_status IS NOT NULL
        )
        SELECT vintage_yr, 100.0*sum(d12)/count(*) AS mob12_pct
        FROM f WHERE mob_observed >= 12 GROUP BY 1
    """).fetchdf().set_index("vintage_yr")
    vc_base = vc.loc[BASELINE_FROM:BASELINE_TO, "mob12_pct"].mean()
    t = th.loc["E-03"]
    for yr in range(2016, 2019):
        if yr not in vc.index:
            rows.append({
                "ewi_id": "E-03", "indicator": "Vintage Deterioration", "scope": "portfolio",
                "vintage_yr": yr, "value": None, "baseline": round(vc_base, 2),
                "ratio_or_drift": None, "status": "NO SIGNAL - cohort not observed to MOB 12",
            })
            continue
        ratio = vc.loc[yr, "mob12_pct"] / vc_base
        rows.append({
            "ewi_id": "E-03", "indicator": "Vintage Deterioration", "scope": "portfolio",
            "vintage_yr": yr, "value": round(vc.loc[yr, "mob12_pct"], 2),
            "baseline": round(vc_base, 2), "ratio_or_drift": round(ratio, 3),
            "status": rag(ratio, t.amber, t.red),
        })

    panel = pd.DataFrame(rows)
    Path("outputs").mkdir(exist_ok=True)
    panel.to_csv(OUT, index=False)

    n_2018 = con.execute(
        "SELECT count(*) FROM loan WHERE vintage_yr = 2018").fetchone()[0]

    print(f"EWI PANEL - as of 2018-12-01 | baseline window {BASELINE_FROM}-{BASELINE_TO}")
    print(panel.to_string(index=False))

    print(f"\n--- the point of the panel ---")
    print(f"The 2018 vintage is {n_2018:,} loans - the largest in the book.")
    print("E-02 and E-03 return NO SIGNAL for it: not observed to MOB 12, and")
    print("unknown is not zero. Only E-01 can speak, and it reads "
          f"{fpd.loc[2018,'fpd_pct']}% - {fpd.loc[2018,'fpd_pct']/fpd_base:.1f}x its baseline "
          "and the highest in the book's history.")
    print("A panel of slow indicators alone shows a blank column for the newest,")
    print("largest vintage and reads as 'nothing to report'.")
    print("\nAll thresholds are ILLUSTRATIVE (see provenance in config/ewi_thresholds.csv).")
    print(f"written: {OUT}")
    con.close()


if __name__ == "__main__":
    main()
