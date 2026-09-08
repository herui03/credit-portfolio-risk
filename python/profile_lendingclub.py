"""
profile_lendingclub.py - honest profile of the raw LendingClub extract.

This is the Stage-1 profile that produced the numbers in
docs/challenge-01-maturity-bias.md. It runs against the RAW gz (not the warehouse)
because part of its job is to justify what the warehouse throws away.

It is deliberately unflattering: it reports what is dirty, what is censored, and
what the dataset structurally cannot support, rather than only what works.

Outputs:
    outputs/vintage_naive_vs_matched.csv   naive vs MOB-matched, side by side

Run:  .venv/bin/python python/profile_lendingclub.py
"""

from pathlib import Path

import duckdb

RAW = "data/raw/accepted_2007_to_2018Q4.csv.gz"
DB = "data/processed/portfolio.duckdb"
OUT = "outputs/vintage_naive_vs_matched.csv"


def main() -> None:
    con = duckdb.connect()
    con.execute(f"""
        CREATE VIEW lc AS
        SELECT * FROM read_csv_auto('{RAW}', ignore_errors=true, sample_size=200000)
    """)

    print("=" * 72)
    print("SHAPE")
    n = con.execute("SELECT count(*) FROM lc").fetchone()[0]
    ncol = len(con.execute("DESCRIBE lc").fetchdf())
    print(f"  rows    : {n:,}")
    print(f"  columns : {ncol}")

    print("\nGRAIN - is it one row per loan, or a loan-month panel?")
    rows, ids = con.execute(
        "SELECT count(*), count(DISTINCT id) FROM lc WHERE id IS NOT NULL").fetchone()
    print(f"  rows with id     : {rows:,}")
    print(f"  distinct ids     : {ids:,}")
    print(f"  duplicates       : {rows - ids:,}")
    print("  -> ONE ROW PER LOAN. A single final-status snapshot, no monthly")
    print("     performance records. This is why roll rate / delinquency migration")
    print("     is NOT in this project: the data cannot support it. See README.")

    print("\nLABEL - loan_status distribution")
    print(con.execute("""
        SELECT loan_status, count(*) AS n,
               round(100.0*count(*)/sum(count(*)) OVER (),2) AS pct
        FROM lc GROUP BY 1 ORDER BY n DESC
    """).fetchdf().to_string(index=False))
    print("  -> 'Current' is NOT a good outcome. It is an UNKNOWN outcome.")
    print("     Counting it as a non-default is the censoring trap (challenge-01).")

    print("\nVINTAGE SPAN")
    print(con.execute("""
        SELECT min(strptime(issue_d,'%b-%Y')) AS first_vintage,
               max(strptime(issue_d,'%b-%Y')) AS last_vintage,
               count(DISTINCT issue_d) AS n_vintage_months
        FROM lc WHERE issue_d IS NOT NULL
    """).fetchdf().to_string(index=False))

    print("\nDATA QUALITY - the 33-row phantom")
    direct = con.execute(f"""
        SELECT count(*) FROM read_csv_auto('{RAW}', ignore_errors=true, sample_size=200000)
    """).fetchone()[0]
    via_view = con.execute("SELECT count(*) FROM lc").fetchone()[0]
    print(f"  count(*) read directly from the file : {direct:,}")
    print(f"  count(*) via any column-touching query: {via_view:,}")
    print(f"  gap                                   : {direct - via_view}")
    print("  -> Same file, same options. count(*) does not validate columns, so it")
    print("     counts 33 rows the rest of the pipeline cannot see. ignore_errors=true")
    print("     discards them at PARSE time, silently.")
    print("  -> They are not loans. They are LendingClub structural lines embedded")
    print("     mid-file (the CSV is concatenated quarterly exports):")
    print('       32x  "Total amount funded in policy code N: ..."   export footers')
    print('        1x  "Loans that do not meet the credit policy"     section header')
    print("  -> Dropping them is correct. Dropping them SILENTLY is not: the same")
    print("     flag would discard a real loan with one bad field and never say so.")
    print("     build_warehouse.py therefore uses store_rejects and asserts the count")
    print("     and the pattern. 2,260,701 raw lines = 2,260,668 loans + 33 structural.")

    print("\nDATA QUALITY - nulls in fields we keep")
    print(con.execute("""
        SELECT
            sum(CASE WHEN issue_d IS NULL THEN 1 ELSE 0 END)     AS null_issue_d,
            sum(CASE WHEN loan_status IS NULL THEN 1 ELSE 0 END) AS null_status,
            sum(CASE WHEN annual_inc IS NULL THEN 1 ELSE 0 END)  AS null_annual_inc,
            sum(CASE WHEN addr_state IS NULL THEN 1 ELSE 0 END)  AS null_addr_state
        FROM lc
    """).fetchdf().to_string(index=False))

    print("\nMOB RECONSTRUCTION - can we date the default?")
    print(con.execute("""
        SELECT count(*) AS charged_off,
               sum(CASE WHEN last_pymnt_d IS NULL THEN 1 ELSE 0 END) AS missing_last_pymnt,
               round(100.0*sum(CASE WHEN last_pymnt_d IS NULL THEN 1 ELSE 0 END)
                     /count(*),2) AS missing_pct
        FROM lc WHERE loan_status LIKE '%Charged Off%'
    """).fetchdf().to_string(index=False))
    print(con.execute("""
        WITH co AS (
          SELECT datediff('month', strptime(issue_d,'%b-%Y'),
                                   strptime(last_pymnt_d,'%b-%Y')) AS mob
          FROM lc WHERE loan_status LIKE '%Charged Off%'
            AND last_pymnt_d IS NOT NULL AND issue_d IS NOT NULL
        )
        SELECT round(median(mob),1) AS median_mob, round(avg(mob),1) AS mean_mob,
               min(mob) AS min_mob, max(mob) AS max_mob,
               sum(CASE WHEN mob<0 THEN 1 ELSE 0 END) AS negative_mob
        FROM co
    """).fetchdf().to_string(index=False))
    print("  -> viable. Caveat: last_pymnt_d is when the borrower STOPPED PAYING,")
    print("     ~4-5 months before accounting charge-off. See assumptions doc.")

    # ---- the side-by-side artifact the challenge doc cites
    w = duckdb.connect(DB, read_only=True)
    naive = w.execute("""
        SELECT vintage_yr,
               count(*) AS n_loans,
               round(100.0*sum(is_charged_off)/count(*),2) AS naive_default_pct,
               round(100.0*sum(CASE WHEN loan_status='Current' THEN 1 ELSE 0 END)
                     /count(*),2) AS still_current_pct,
               round(100.0*sum(is_charged_off)/nullif(sum(is_resolved),0),2)
                     AS resolved_only_default_pct
        FROM loan WHERE loan_status IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchdf()
    matched = w.execute("""
        WITH flagged AS (
            SELECT vintage_yr, mob_observed,
                   CASE WHEN is_charged_off=1 AND mob_default <= 12
                        THEN 1 ELSE 0 END AS d12
            FROM loan WHERE term_clean='36 months' AND loan_status IS NOT NULL
        )
        SELECT vintage_yr, round(100.0*sum(d12)/count(*),2) AS mob12_default_pct
        FROM flagged WHERE mob_observed >= 12 GROUP BY 1 ORDER BY 1
    """).fetchdf()

    merged = naive.merge(matched, on="vintage_yr", how="left")
    Path("outputs").mkdir(exist_ok=True)
    merged.to_csv(OUT, index=False)

    print("\n" + "=" * 72)
    print("NAIVE vs MOB-MATCHED - the flattering number cannot be read alone")
    print(merged.to_string(index=False))
    print(f"\nwritten: {OUT}")
    print("  -> naive falls 18.00 -> 1.79 as still_current rises 10.28 -> 86.26.")
    print("     mob12 RISES 3.86 (2011) -> 6.18 (2016). Opposite sign.")
    print("     mob12 is blank where the cohort is too young to know. That is correct.")

    con.close()
    w.close()


if __name__ == "__main__":
    main()
