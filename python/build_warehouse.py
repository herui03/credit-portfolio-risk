"""
build_warehouse.py - materialise the curated credit portfolio warehouse.

Reads the raw LendingClub gz (392 MB, 151 columns, 2.26M rows) once and writes a
DuckDB file with two tables:

    loan            one row per loan  (grain verified: id is unique, 0 duplicates)
    loan_live       the LIVE book only (out_prncp > 0) - the book a risk team monitors

WHY A CURATED SUBSET
    Of 151 raw columns we keep 26. The rest are either post-origination payment
    detail (leakage risk if a model is ever fitted here) or secondary-applicant /
    hardship fields that are >90% null. Dropping them is a documented decision,
    not convenience - see docs/assumptions_and_limitations.md.

WHY "LIVE BOOK" = out_prncp > 0
    Fully Paid and Charged Off loans carry out_prncp = 0 - they are closed. Exposure
    monitoring and limits apply to money currently at risk, so the live book is the
    correct basis. Verified: every out_prncp > 0 loan has status Current / Late /
    In Grace Period / Default, and no closed loan leaks in.

THE 33 ROWS - why store_rejects, not ignore_errors
    The raw file reports 2,260,701 rows to count(*) but only 2,260,668 to any query
    that touches a column. The gap is 33 rows that `ignore_errors=true` discards at
    PARSE time - count(*) never validates the columns, so it counts rows the rest of
    the pipeline cannot see.

    Those 33 rows are LendingClub structural lines embedded mid-file - the published
    CSV is a concatenation of quarterly exports, and each export's scaffolding came
    along for the ride. Two kinds, both non-loans, both correctly dropped:
        32x  "Total amount funded in policy code 1: 6417608175"   (export footers)
         1x  "Loans that do not meet the credit policy"           (section header,
             the divider preceding the 2,749 "Does not meet the credit policy" loans)
    The first version of this gate asserted all 33 were footers. It failed on the
    section header - which is the gate doing its job on its own author.

    But `ignore_errors=true` drops them SILENTLY - it would equally silently drop a
    genuine loan record with one bad field, and nothing would ever say so. So we use
    store_rejects instead: every discarded row is captured, counted, and asserted to
    match the known footer pattern. An unexpected reject fails the build.

    2,260,701 raw lines = 2,260,668 loans + 33 embedded footers.

Run:  .venv/bin/python python/build_warehouse.py
"""

import duckdb
from pathlib import Path

RAW = "data/raw/accepted_2007_to_2018Q4.csv.gz"
DB = "data/processed/portfolio.duckdb"
AS_OF = "2018-12-01"  # data cutoff - every point-in-time metric is as of this date
EXPECTED_REJECTS = 33  # LendingClub footer lines - see module docstring

KEEP = """
    id, issue_d, loan_status, term, grade, sub_grade, addr_state, purpose,
    home_ownership, application_type, emp_length, verification_status,
    loan_amnt, funded_amnt, out_prncp, installment, int_rate,
    annual_inc, dti, fico_range_low, fico_range_high,
    last_pymnt_d, last_fico_range_low, last_fico_range_high,
    total_pymnt, total_rec_prncp, recoveries
"""


def main() -> None:
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    Path(DB).unlink(missing_ok=True)
    con = duckdb.connect(DB)

    con.execute(f"""
        CREATE TABLE loan AS
        SELECT {KEEP}
             , strptime(issue_d, '%b-%Y')                            AS issue_dt
             , strptime(last_pymnt_d, '%b-%Y')                       AS last_pymnt_dt
             , year(strptime(issue_d, '%b-%Y'))                      AS vintage_yr
             , date_trunc('month', strptime(issue_d, '%b-%Y'))       AS vintage_month
             , trim(term)                                            AS term_clean
             , datediff('month', strptime(issue_d, '%b-%Y'), DATE '{AS_OF}') AS mob_observed
             -- RAW: months on book at which the borrower stopped paying.
             -- NULL when last_pymnt_d is absent. Kept raw and unpatched so the
             -- distribution can be quoted honestly; do NOT use it for curves.
             , CASE WHEN loan_status LIKE '%Charged Off%'
                    THEN datediff('month', strptime(issue_d, '%b-%Y'),
                                           strptime(last_pymnt_d, '%b-%Y'))
               END                                                   AS mob_stopped_paying
             -- BUSINESS RULE: the MOB at which the loan defaulted. Use THIS for
             -- vintage curves.
             --
             -- 2,325 charged-off loans have no last_pymnt_d, and every one of them
             -- repaid EXACTLY zero principal (verified: max(total_rec_prncp) = 0.00
             -- across all 2,325; 848 never paid a cent at all). They are not missing
             -- data - they are the fastest defaults in the book, and they are dated
             -- by the column next door.
             --
             -- Without the coalesce, `mob_stopped_paying <= 12` evaluates NULL <= 12
             -- -> NULL -> ELSE 0, and a loan that never repaid a dollar of principal
             -- is counted as "did not default by month 12". That is the exact error
             -- challenge-01 is about - treating unknown as no - committed inside the
             -- fix for it. Here it isn't even unknown: it's knowable and I hadn't looked.
             --
             -- Assigning MOB 0 is the earliest-possible treatment, which is what zero
             -- principal repayment implies. See challenge-05.
             , CASE WHEN loan_status LIKE '%Charged Off%'
                    THEN coalesce(
                           datediff('month', strptime(issue_d, '%b-%Y'),
                                             strptime(last_pymnt_d, '%b-%Y')),
                           0)
               END                                                   AS mob_default
             , CASE WHEN loan_status LIKE '%Charged Off%' THEN 1 ELSE 0 END AS is_charged_off
             , CASE WHEN loan_status LIKE '%Fully Paid%'  THEN 1 ELSE 0 END AS is_fully_paid
             , CASE WHEN loan_status LIKE '%Fully Paid%'
                      OR loan_status LIKE '%Charged Off%' THEN 1 ELSE 0 END AS is_resolved
        -- store_rejects, NOT ignore_errors: discards are captured and asserted below.
        -- No WHERE id IS NOT NULL here - an earlier version had one and it filtered
        -- exactly zero rows, while the docstring credited it with the 33-row drop.
        -- The parser had already removed them. Don't take credit for a filter that
        -- isn't firing; make the real mechanism visible instead.
        FROM read_csv_auto('{RAW}', sample_size=200000, store_rejects=true)
    """)

    # ---- data-quality gate: every discarded row must be a known footer line
    rejects = con.execute("SELECT count(DISTINCT line) FROM reject_errors").fetchone()[0]
    assert rejects == EXPECTED_REJECTS, (
        f"REJECT COUNT CHANGED: expected {EXPECTED_REJECTS} footer lines, got {rejects}. "
        "Inspect reject_errors before trusting this build."
    )
    # Both known non-loan line types are allowed; anything else fails the build,
    # because an unrecognised reject may be a real loan record going missing.
    unexpected = con.execute("""
        SELECT count(*) FROM reject_errors
        WHERE column_name <> 'id'
           OR NOT (error_message LIKE '%Total amount funded in policy code%'
                OR error_message LIKE '%Loans that do not meet the credit policy%')
    """).fetchone()[0]
    assert unexpected == 0, (
        f"UNEXPECTED REJECT: {unexpected} discarded rows match no known non-loan "
        "pattern. A real loan record may be being dropped silently. "
        "Inspect reject_errors before trusting this build."
    )

    con.execute("""
        CREATE TABLE loan_live AS
        SELECT * FROM loan WHERE out_prncp > 0
    """)

    # ---- grain + integrity assertions: fail loudly rather than ship a bad warehouse
    rows, ids = con.execute(
        "SELECT count(*), count(DISTINCT id) FROM loan").fetchone()
    assert rows == ids, f"GRAIN VIOLATION: {rows:,} rows but {ids:,} distinct ids"

    leaked = con.execute("""
        SELECT count(*) FROM loan_live
        WHERE loan_status LIKE '%Fully Paid%' OR loan_status LIKE '%Charged Off%'
    """).fetchone()[0]
    assert leaked == 0, f"LIVE BOOK LEAK: {leaked:,} closed loans have out_prncp > 0"

    # The mob_default rule rests on "no last_pymnt_d => zero principal repaid".
    # Assert it rather than trust it - if it ever breaks, the curves are wrong.
    bad = con.execute("""
        SELECT count(*) FROM loan
        WHERE is_charged_off = 1 AND last_pymnt_dt IS NULL AND total_rec_prncp > 0
    """).fetchone()[0]
    assert bad == 0, (
        f"MOB_DEFAULT RULE BROKEN: {bad:,} charged-off loans have no last_pymnt_d but "
        "DID repay principal. They cannot be dated as MOB-0 defaults. Re-derive the rule."
    )
    null_dated = con.execute("""
        SELECT count(*) FROM loan WHERE is_charged_off = 1 AND last_pymnt_dt IS NULL
    """).fetchone()[0]

    live_n, live_exp = con.execute(
        "SELECT count(*), sum(out_prncp) FROM loan_live").fetchone()

    print(f"warehouse : {DB}")
    print(f"as-of     : {AS_OF}")
    print(f"rejects   : {rejects} non-loan structural lines discarded "
          f"(32 export footers + 1 section header, asserted)")
    print(f"loan      : {rows:,} rows  (grain OK - {ids:,} distinct ids, 0 dups)")
    print(f"loan_live : {live_n:,} rows  |  outstanding ${live_exp/1e9:,.3f}bn")
    print(f"leak check: {leaked} closed loans in live book (must be 0)")
    print(f"mob_default: {null_dated:,} charged-off loans dated MOB-0 "
          f"(no last_pymnt_d, zero principal repaid - asserted)")
    print(f"reconcile : 2,260,701 raw lines = {rows:,} loans + {rejects} structural lines")
    con.close()


if __name__ == "__main__":
    main()
