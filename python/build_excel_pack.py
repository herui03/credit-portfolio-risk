"""
build_excel_pack.py - monthly risk committee pack.

Assembles outputs/*.csv into outputs/risk_committee_pack.xlsx.

THE DESIGN DECISION THAT MATTERS: values vs formulas
    A pack that hardcodes every number is a dead report - a reviewer cannot trace
    anything, cannot flex a threshold, cannot see how a verdict was reached. A real
    committee pack is traceable.

    But logic in a formula LEAVES THE TEST HARNESS. Measured, not assumed:

        ws.write_formula("C1", "=A1/B1*100")
        openpyxl.load_workbook(path, data_only=True)["t"]["C1"].value  ->  0

    The result reads as 0 because no calculation engine ever ran. xlsxwriter writes
    the formula without a cached value; openpyxl does not evaluate. verify_claims.py
    can assert the formula STRING and can never assert its RESULT. Only Excel can
    compute it, and Excel is not in this pipeline.

    That is textbook EUC (End User Computing) risk - the category behind the
    JPMorgan London Whale VaR spreadsheet and the Reinhart-Rogoff range error.

    So the boundary is drawn explicitly:
      * SOURCE values  -> written as VALUES, asserted cell-by-cell against the
                          verified outputs/*.csv by verify_claims.py
      * DERIVED cells  -> written as FORMULAS, so a reviewer can trace and flex them
      * Formula RESULTS-> outside the harness. Stated on the Cover sheet, in this
                          docstring, and in docs/challenge-07-*.md. Not hidden.

    Mitigation: this pack is REGENERATED from the pipeline on every run and is never
    hand-edited. The CSVs are the source of truth; the workbook is a rendering. If
    the two ever disagree, the workbook is wrong by definition.

THRESHOLDS ARE LIVE
    Limit thresholds and EWI thresholds are written as values into their own cells
    and referenced by the formulas. Change a threshold in the sheet and utilisation
    and RAG recompute - which is the actual thing a committee does in the room.

Run:  .venv/bin/python python/build_excel_pack.py
"""

from pathlib import Path

import pandas as pd
import xlsxwriter

OUT = "outputs/risk_committee_pack.xlsx"
AS_OF = "2018-12-01"


def main() -> None:
    limits = pd.read_csv("outputs/limit_breaches.csv")
    conc = pd.read_csv("outputs/concentration.csv")
    ewi = pd.read_csv("outputs/ewi_panel.csv")
    stress = pd.read_csv("outputs/stress_results.csv")
    ewi_th = pd.read_csv("config/ewi_thresholds.csv")

    Path("outputs").mkdir(exist_ok=True)
    wb = xlsxwriter.Workbook(OUT)

    # ---- formats
    f = {
        "title": wb.add_format({"bold": True, "font_size": 16, "font_color": "#1F3554"}),
        "h1": wb.add_format({"bold": True, "font_size": 12, "bg_color": "#1F3554",
                             "font_color": "white", "align": "left"}),
        "hdr": wb.add_format({"bold": True, "bg_color": "#EEF1F5", "border": 1,
                              "text_wrap": True, "valign": "top"}),
        "txt": wb.add_format({"border": 1}),
        "num2": wb.add_format({"border": 1, "num_format": "0.00"}),
        "num3": wb.add_format({"border": 1, "num_format": "0.000"}),
        "pct1": wb.add_format({"border": 1, "num_format": "0.0"}),
        "mm": wb.add_format({"border": 1, "num_format": "#,##0.0"}),
        "int": wb.add_format({"border": 1, "num_format": "#,##0"}),
        "caveat": wb.add_format({"text_wrap": True, "valign": "top", "font_color": "#9E2A2B",
                                 "bg_color": "#FDF3F2", "border": 1}),
        "note": wb.add_format({"text_wrap": True, "valign": "top", "font_color": "#4A463E"}),
        "red": wb.add_format({"bg_color": "#FDECEA", "font_color": "#B42318", "bold": True, "border": 1}),
        "amber": wb.add_format({"bg_color": "#FEF6E7", "font_color": "#B25E09", "bold": True, "border": 1}),
        "green": wb.add_format({"bg_color": "#E8F1ED", "font_color": "#0F766E", "border": 1}),
        "nosig": wb.add_format({"bg_color": "#EEF1F5", "font_color": "#475467", "italic": True, "border": 1}),
    }

    # ================================================================== COVER
    ws = wb.add_worksheet("Cover")
    ws.set_column("A:A", 22)
    ws.set_column("B:B", 96)
    ws.write("A1", "Credit Portfolio Risk - Committee Pack", f["title"])
    rows = [
        ("As of", AS_OF),
        ("Portfolio", "LendingClub accepted loans 2007-06 to 2018-12 (real, public data)"),
        ("Live book", "907,904 loans | $9.510bn outstanding (out_prncp > 0)"),
        ("Limits", f"{len(limits)} evaluated | {int((limits.status=='BREACH').sum())} BREACH"),
        ("EWI panel", "E-01 FPD RED (5.093x baseline) | E-02 Rating Drift RED (4 grades) | "
                      "E-03 Vintage NO SIGNAL for 2018"),
        ("Stress", "Base 5.76% | Adverse 8.65% | Severe 13.43% loss on live book"),
    ]
    for i, (k, v) in enumerate(rows, start=3):
        ws.write(f"A{i}", k, f["hdr"])
        ws.write(f"B{i}", v, f["txt"])

    ws.merge_range("A11:B11", "READ THIS FIRST", f["h1"])
    caveats = [
        "ALL THRESHOLDS IN THIS PACK ARE ILLUSTRATIVE. Every limit and EWI threshold was set by the "
        "analyst and calibrated against the observed book. In a real institution they descend from a "
        "board-approved Risk Appetite Statement and are NOT fitted to the portfolio they police. "
        "Read the 4 breaches as 'how a diversification-minded lender would constrain this book', "
        "never as 'this book is in violation'.",

        "'NO SIGNAL' IS NOT 'GREEN'. E-02 and E-03 return nothing for the 2018 vintage - 495,242 loans, "
        "the largest in the book. They require 12 months on book and the cohort is 0-11 months old. "
        "A blank is not reassurance; it is a structural blind spot, and it sits on the freshest exposure "
        "by construction. Only E-01 (first-payment default) can speak, and it reads 5.093x baseline.",

        "THE BASE STRESS CASE OVERSTATES LOSS. PD is an origination-cohort MOB-12 rate applied to a book "
        "whose median loan is already at MOB 12.0 (51.8% past MOB 12). The median default lands at MOB 14, "
        "so the median live loan has survived the peak-hazard window. The bias is conservative and declared.",

        "NO MACRO MODEL IS FITTED. corr(default, unemployment) = -0.521 on 11 vintages - negative, because "
        "the lender tightened underwriting as unemployment peaked. Fitting it would forecast that recessions "
        "REDUCE losses. Scenarios are within-grade PD shocks anchored to observed variation instead.",

        "FORMULA RESULTS IN THIS WORKBOOK ARE NOT VERIFIED BY THE PIPELINE. Source values are asserted "
        "cell-by-cell against outputs/*.csv. Derived cells are Excel formulas, and no calculation engine "
        "runs in the pipeline - verify_claims.py can assert a formula's text, never its result. That is EUC "
        "risk and it is stated rather than hidden. This pack is regenerated every run and never hand-edited; "
        "the CSVs are the source of truth. If workbook and CSV disagree, the workbook is wrong.",
    ]
    r = 12
    for c in caveats:
        ws.merge_range(r, 0, r, 1, c, f["caveat"])
        ws.set_row(r, 58)
        r += 1

    # ============================================================== LIMITS
    ws = wb.add_worksheet("Limits")
    ws.freeze_panes(1, 0)
    for i, w in enumerate([9, 15, 19, 30, 11, 11, 14, 11, 46]):
        ws.set_column(i, i, w)
    hdrs = ["Limit", "Dimension", "Metric", "Driver", "Actual", "Threshold",
            "Utilisation %", "Status", "Provenance"]
    for c, h in enumerate(hdrs):
        ws.write(0, c, h, f["hdr"])
    for i, row in limits.iterrows():
        r = i + 1
        ws.write(r, 0, row.limit_id, f["txt"])
        ws.write(r, 1, row.dimension, f["txt"])
        ws.write(r, 2, row.metric, f["txt"])
        ws.write(r, 3, str(row.driver), f["txt"])
        ws.write_number(r, 4, float(row.actual), f["num3"])      # SOURCE - asserted
        ws.write_number(r, 5, float(row.threshold), f["num3"])   # SOURCE - live, editable
        # DERIVED - formulas, so a reviewer can flex the threshold and watch it move
        ws.write_formula(r, 6, f"=E{r+1}/F{r+1}*100", f["pct1"])
        ws.write_formula(r, 7, f'=IF(E{r+1}>F{r+1},"BREACH","PASS")', f["txt"])
        ws.write(r, 8, str(row.provenance), f["txt"])
    ws.conditional_format(1, 7, len(limits), 7,
                          {"type": "cell", "criteria": "==", "value": '"BREACH"', "format": f["red"]})
    ws.conditional_format(1, 7, len(limits), 7,
                          {"type": "cell", "criteria": "==", "value": '"PASS"', "format": f["green"]})
    ws.write(len(limits) + 2, 0,
             "Utilisation and Status are FORMULAS (=E/F*100 and IF(E>F,...)). Edit a threshold in "
             "column F and both recompute. Their results are not asserted by the pipeline - see Cover.",
             f["note"])

    # ======================================================== CONCENTRATION
    ws = wb.add_worksheet("Concentration")
    ws.freeze_panes(1, 0)
    for i, w in enumerate([16, 20, 7, 10, 13, 12, 14, 10, 10, 10, 14]):
        ws.set_column(i, i, w)
    for c, h in enumerate(["Dimension", "Bucket", "Rank", "Loans", "Exposure $mm",
                           "% of book", "Cumulative %", "n buckets", "HHI raw",
                           "HHI floor", "HHI normalised"]):
        ws.write(0, c, h, f["hdr"])
    top = conc[conc.rank_by_exposure <= 10]
    for i, (_, row) in enumerate(top.iterrows()):
        r = i + 1
        ws.write(r, 0, row.dimension, f["txt"])
        ws.write(r, 1, str(row.bucket), f["txt"])
        ws.write_number(r, 2, int(row.rank_by_exposure), f["int"])
        ws.write_number(r, 3, int(row.n_loans), f["int"])
        ws.write_number(r, 4, float(row.exposure_mm), f["mm"])
        ws.write_number(r, 5, float(row.pct_of_book), f["num2"])
        ws.write_number(r, 6, float(row.cumulative_pct), f["num2"])
        ws.write_number(r, 7, int(row.n_buckets), f["int"])
        ws.write_number(r, 8, float(row.hhi_raw), f["num2"])
        ws.write_number(r, 9, float(row.hhi_floor), f["num2"])
        ws.write_number(r, 10, float(row.hhi_normalised), f["num3"])
    ws.write(len(top) + 2, 0,
             "HHI floor = 10000/n. Raw HHI is meaningless without n: 'term' scores 5003 raw ('highly "
             "concentrated' on DOJ bands) while being a 51/49 split - 3 points above its own floor. "
             "Limits are set on HHI normalised. The 1500/2500 bands are a US antitrust standard, not "
             "a banking regulation.", f["note"])

    # ================================================================= EWI
    ws = wb.add_worksheet("EWI Panel")
    ws.freeze_panes(1, 0)
    for i, w in enumerate([8, 24, 12, 10, 11, 11, 15, 42]):
        ws.set_column(i, i, w)
    for c, h in enumerate(["EWI", "Indicator", "Scope", "Vintage", "Value",
                           "Baseline", "Ratio / Drift", "Status"]):
        ws.write(0, c, h, f["hdr"])
    for i, row in ewi.iterrows():
        r = i + 1
        ws.write(r, 0, row.ewi_id, f["txt"])
        ws.write(r, 1, row.indicator, f["txt"])
        ws.write(r, 2, row.scope, f["txt"])
        ws.write_number(r, 3, int(row.vintage_yr), f["int"])
        if pd.isna(row.value):
            ws.write(r, 4, "-", f["nosig"])
            ws.write_number(r, 5, float(row.baseline), f["num3"])
            ws.write(r, 6, "-", f["nosig"])
        else:
            ws.write_number(r, 4, float(row.value), f["num3"])
            ws.write_number(r, 5, float(row.baseline), f["num3"])
            ws.write_number(r, 6, float(row.ratio_or_drift), f["num3"])
        fmt = (f["nosig"] if "NO SIGNAL" in str(row.status)
               else f["red"] if row.status == "RED"
               else f["amber"] if row.status == "AMBER" else f["green"])
        ws.write(r, 7, str(row.status), fmt)
    r = len(ewi) + 2
    ws.write(r, 0,
             "'NO SIGNAL' IS NOT 'GREEN'. E-03 cannot speak about the 2018 vintage (495,242 loans) - "
             "it needs MOB 12 and the cohort is 0-11 months old. Unknown is not zero, so it returns no "
             "row rather than a flattering number. E-01 (first-payment default) is observable from ~MOB 5 "
             "and reads 5.093x its 2013-2015 baseline - the highest in the book's history.", f["note"])
    ws.write(r + 2, 0, "EWI thresholds (AMBER / RED) and their provenance:", f["hdr"])
    for j, (_, t) in enumerate(ewi_th.iterrows()):
        ws.write(r + 3 + j, 0, t.ewi_id, f["txt"])
        ws.write(r + 3 + j, 1, t.indicator, f["txt"])
        ws.write_number(r + 3 + j, 2, float(t.amber), f["num2"])
        ws.write_number(r + 3 + j, 3, float(t.red), f["num2"])
        ws.write(r + 3 + j, 4, str(t.provenance)[:60], f["txt"])

    # ============================================================== STRESS
    ws = wb.add_worksheet("Stress")
    ws.freeze_panes(1, 0)
    for i, w in enumerate([10, 12, 14, 18, 14, 14, 16]):
        ws.set_column(i, i, w)
    for c, h in enumerate(["Scenario", "Name", "PD multiplier", "Expected loss $mm",
                           "Loss rate %", "vs Base $mm", "Provenance"]):
        ws.write(0, c, h, f["hdr"])
    for i, row in stress.iterrows():
        r = i + 1
        ws.write(r, 0, row.scenario_id, f["txt"])
        ws.write(r, 1, row.scenario, f["txt"])
        ws.write_number(r, 2, float(row.pd_multiplier), f["num2"])
        ws.write_number(r, 3, float(row.expected_loss_mm), f["mm"])
        ws.write_number(r, 4, float(row.loss_rate_pct), f["num2"])
        ws.write_number(r, 5, float(row.vs_base_mm), f["mm"])
        ws.write(r, 6, str(row.provenance), f["txt"])
    r = len(stress) + 2
    ws.write(r, 0,
             "No macro model is fitted. corr(MOB-12 default, unemployment at origination) = -0.521 across "
             "11 vintages - NEGATIVE, because the lender tightened underwriting as unemployment peaked "
             "(corr with % grade A/B = -0.908). Fitting it would forecast that a recession IMPROVES the "
             "book, i.e. the scenario would assume its own mitigant. Multipliers are within-grade PD "
             "shocks anchored to observed variation: 1.50x sits inside the observed 2013->2016 "
             "deterioration (+44% to +59%); 2.33x is the largest within-grade swing this book has shown "
             "(grade A, 1.16% -> 2.70%). The scenarios are hypothetical; only the magnitudes are anchored.",
             f["note"])

    wb.close()
    print(f"written: {OUT}")
    print(f"  sheets   : Cover, Limits, Concentration, EWI Panel, Stress")
    print(f"  values   : source figures written as VALUES, asserted against outputs/*.csv")
    print(f"  formulas : Utilisation and Status on the Limits sheet are live formulas")
    print(f"  boundary : formula RESULTS are outside verify_claims.py - stated on Cover")


if __name__ == "__main__":
    main()
