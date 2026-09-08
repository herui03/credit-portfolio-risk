"""
limit_monitor.py - evaluate the live book against the risk limit framework.

Reads config/risk_limits.csv (limits + rationale + provenance) and emits a breach
report: every limit, its current utilisation, and PASS / BREACH.

DESIGN NOTES
  * Limits are evaluated on the LIVE book only (out_prncp > 0). Closed loans carry
    no exposure - including them would dilute every ratio toward zero.

  * Concentration limits are set on NORMALISED HHI, not raw HHI. Raw HHI's floor is
    10000/n, so DOJ merger bands (1500/2500) misfire on low-cardinality dimensions:
    `term` scores 5003 raw ("HIGH") while being a 51/49 split - three points above
    its own floor. See sql/concentration_hhi.sql and docs/challenge-02-hhi-cardinality.md.

  * Every limit carries a `provenance` field, and every one of them currently reads
    ILLUSTRATIVE. These thresholds are our judgement, calibrated to be plausible
    against the observed book. In a real institution they descend from a board-approved
    Risk Appetite Statement and are not fitted to the portfolio they police. The report
    prints provenance next to every breach so the number can never be mistaken for a
    regulatory threshold.

Run:  .venv/bin/python python/limit_monitor.py
"""

import duckdb
import pandas as pd
from pathlib import Path

DB = "data/processed/portfolio.duckdb"
LIMITS = "config/risk_limits.csv"
OUT = "outputs/limit_breaches.csv"
AS_OF = "2018-12-01"


def single_bucket_pct(con, dim):
    return con.execute(f"""
        SELECT {dim} AS bucket, 100.0*sum(out_prncp)/(SELECT sum(out_prncp) FROM loan_live) AS pct
        FROM loan_live WHERE {dim} IS NOT NULL GROUP BY 1 ORDER BY pct DESC LIMIT 1
    """).fetchone()


def group_pct(con, dim, members):
    lst = ",".join(f"'{m.strip()}'" for m in members.split(","))
    v = con.execute(f"""
        SELECT 100.0*sum(out_prncp)/(SELECT sum(out_prncp) FROM loan_live)
        FROM loan_live WHERE {dim} IN ({lst})
    """).fetchone()[0]
    return members, v


def top_n_pct(con, dim, n):
    # cumulative computed BEFORE filtering - WHERE runs before window functions
    v = con.execute(f"""
        WITH agg AS (
            SELECT {dim} AS b, sum(out_prncp) AS e FROM loan_live
            WHERE {dim} IS NOT NULL GROUP BY 1
        ), ranked AS (
            SELECT b, 100.0*e/sum(e) OVER () AS pct,
                   row_number() OVER (ORDER BY e DESC) AS rk
            FROM agg
        ), cum AS (
            SELECT rk, sum(pct) OVER (ORDER BY rk) AS cpct FROM ranked
        )
        SELECT cpct FROM cum WHERE rk = {int(n)}
    """).fetchone()[0]
    return f"top_{int(n)}", v


def hhi_normalised(con, dim):
    n, hhi = con.execute(f"""
        WITH agg AS (
            SELECT {dim} AS b, sum(out_prncp) AS e FROM loan_live
            WHERE {dim} IS NOT NULL GROUP BY 1
        ), sh AS (SELECT 100.0*e/sum(e) OVER () AS pct FROM agg)
        SELECT count(*), sum(pct*pct) FROM sh
    """).fetchone()
    floor = 10000.0 / n
    return f"n={n} raw={hhi:.1f} floor={floor:.1f}", (hhi - floor) / (10000.0 - floor)


def main() -> None:
    con = duckdb.connect(DB, read_only=True)
    limits = pd.read_csv(LIMITS)
    rows = []

    for _, L in limits.iterrows():
        m, dim = L["metric"], L["dimension"]
        if m == "single_bucket_pct":
            detail, val = single_bucket_pct(con, dim)
        elif m == "group_pct":
            detail, val = group_pct(con, dim, L["bucket"])
        elif m == "top_n_pct":
            detail, val = top_n_pct(con, dim, L["bucket"])
        elif m == "hhi_normalised":
            detail, val = hhi_normalised(con, dim)
        else:
            raise ValueError(f"unknown metric {m}")

        breach = val > L["threshold"]  # every limit is a <= ceiling
        rows.append({
            "limit_id": L["limit_id"], "dimension": dim, "metric": m,
            "driver": detail, "actual": round(val, 3),
            "threshold": L["threshold"], "unit": L["unit"],
            "utilisation_pct": round(100.0 * val / L["threshold"], 1),
            "status": "BREACH" if breach else "PASS",
            "provenance": L["provenance"].split(".")[0],
        })

    df = pd.DataFrame(rows)
    Path("outputs").mkdir(exist_ok=True)
    df.to_csv(OUT, index=False)

    # Concentration detail is emitted as its own artifact so the Excel pack reads
    # only from verified outputs/ rather than re-querying and risking divergence.
    import re as _re
    _sql = _re.sub(r"--[^\n]*", "", Path("sql/concentration_hhi.sql").read_text())
    _stmts = [x.strip() for x in _sql.split(";") if x.strip()]
    assert len(_stmts) == 1, "concentration_hhi.sql: expected 1 statement"
    con.execute(_stmts[0]).fetchdf().to_csv("outputs/concentration.csv", index=False)

    live_n, live_exp = con.execute(
        "SELECT count(*), sum(out_prncp) FROM loan_live").fetchone()
    n_breach = int((df.status == "BREACH").sum())

    print(f"LIMIT MONITOR - as of {AS_OF}")
    print(f"live book: {live_n:,} loans | ${live_exp/1e9:.3f}bn outstanding")
    print(f"limits evaluated: {len(df)} | BREACHES: {n_breach}\n")
    print(df[["limit_id", "dimension", "metric", "driver", "actual",
              "threshold", "utilisation_pct", "status"]].to_string(index=False))
    print(f"\nAll thresholds are ILLUSTRATIVE (see provenance in {LIMITS}).")
    print(f"written: {OUT}")
    con.close()


if __name__ == "__main__":
    main()
