-- =============================================================================
-- concentration_hhi.sql - portfolio concentration, cardinality-corrected
-- =============================================================================
-- TWO DECISIONS ENCODED HERE. Both were wrong in the original spec.
-- See docs/challenge-02-hhi-cardinality.md
--
-- DECISION 1 - HHI is computed on DIMENSIONS, not on obligors
--   The spec inherited "HHI + Top-10" from a corporate FI module, where HHI
--   measures single-name concentration. This is a CONSUMER book. Measured
--   obligor-level HHI on the live book (see python/verify_claims.py):
--
--       n_obligors = 907,904   HHI = 0.0179   largest single loan = 0.000421%
--
--   HHI ~ 0. Single-name concentration is structurally impossible when the
--   largest borrower is four ten-thousandths of a percent of the book. So we
--   measure where consumer concentration actually lives: correlated exposure
--   across geography, purpose, grade
--
-- DECISION 2 - Raw HHI bands are cardinality-dependent. We normalise
--   HHI's floor is 10000/n (perfectly even split across n buckets), so the
--   DOJ/FTC merger bands (1500 moderate / 2500 high) only mean anything when n is
--   large. On low-cardinality dimensions they produce false alarms:
--
--     dimension        n     HHI    floor    HHI*    raw band   truth
--     term             2   5003.0   5000.0   0.001   "HIGH"     most BALANCED dim in book
--     grade            7   2363.3   1428.6   0.109   "MODERATE" balanced
--     home_ownership   5   4270.0   2000.0   0.284   "HIGH"     moderate
--     purpose         14   4074.0    714.3   0.362   "HIGH"     genuinely concentrated
--     addr_state      50    507.1    200.0   0.031   "low"      balanced
--
--   `term` is a 51.23 / 48.77 split - three points above its theoretical floor -
--   and the raw band calls it the most concentrated dimension in the portfolio.
--   A limit built on raw HHI fires a permanent breach on a coin flip
--
--     HHI* = (HHI - 10000/n) / (10000 - 10000/n)
--            0.00 = perfectly balanced      1.00 = everything in one bucket
--
--   PROVENANCE: the 1500/2500 bands are US DOJ/FTC Horizontal Merger Guidelines -
--   an ANTITRUST standard for markets with many firms, not a banking regulation.
--   They are widely borrowed into credit, and the borrowing is exactly where the
--   "many participants" assumption gets silently dropped. HHI* thresholds are ours
--   and are labelled ILLUSTRATIVE in config/risk_limits.csv
--
-- WHY NO :dim PARAMETER
--   An earlier version took the dimension as a bind parameter. No SQL engine
--   substitutes an IDENTIFIER via a parameter - it parsed as a string literal and
--   the file did not run at all. Rather than push dimension injection into Python
--   f-strings and leave un-runnable SQL in the repo, this file evaluates every
--   dimension in one pass via UNION ALL. It runs as-is against the warehouse
--
-- Basis: LIVE book only (out_prncp > 0) - 907,904 loans, $9.510bn as of 2018-12-01.
-- Closed loans carry no exposure and are excluded
-- Grain: one row per (dimension, bucket)
-- =============================================================================

WITH unpivoted AS (
    SELECT 'addr_state'     AS dimension, addr_state     AS bucket, out_prncp FROM loan_live WHERE addr_state     IS NOT NULL
    UNION ALL SELECT 'purpose',           purpose,           out_prncp FROM loan_live WHERE purpose        IS NOT NULL
    UNION ALL SELECT 'grade',             grade,             out_prncp FROM loan_live WHERE grade          IS NOT NULL
    UNION ALL SELECT 'term',              term_clean,        out_prncp FROM loan_live WHERE term_clean     IS NOT NULL
    UNION ALL SELECT 'home_ownership',    home_ownership,    out_prncp FROM loan_live WHERE home_ownership IS NOT NULL
),

agg AS (
    SELECT dimension, bucket, sum(out_prncp) AS exposure, count(*) AS n_loans
    FROM unpivoted
    GROUP BY dimension, bucket
),

shares AS (
    SELECT
        dimension, bucket, exposure, n_loans,
        -- share is WITHIN its own dimension, hence PARTITION BY
        100.0 * exposure / sum(exposure) OVER (PARTITION BY dimension) AS pct_of_book,
        count(*)          OVER (PARTITION BY dimension)                AS n_buckets,
        row_number()      OVER (PARTITION BY dimension ORDER BY exposure DESC) AS rank_by_exposure
    FROM agg
),

-- Cumulation gets its own CTE for two separate reasons, both learned the hard way:
--   1. Window functions cannot be NESTED. Cumulating over a windowed pct_of_book
--      in the same SELECT is a binder error (caught by python/verify_claims.py)
--   2. WHERE runs BEFORE window functions. Filtering and cumulating in the same
--      SELECT silently sums only the surviving rows - that gave Top-10 = 28.55%
--      instead of 58.10%, understating concentration 2x with no error raised
-- Cumulate first, in full. Filter downstream, never here
cumulated AS (
    SELECT
        *,
        sum(pct_of_book) OVER (
            PARTITION BY dimension
            ORDER BY rank_by_exposure
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_pct
    FROM shares
),

hhi AS (
    SELECT
        dimension,
        any_value(n_buckets)                       AS n_buckets,
        sum(pct_of_book * pct_of_book)             AS hhi_raw,
        10000.0 / any_value(n_buckets)             AS hhi_floor
    FROM cumulated
    GROUP BY dimension
)

SELECT
    c.dimension,
    c.bucket,
    c.rank_by_exposure,
    c.n_loans,
    round(c.exposure / 1e6, 1)   AS exposure_mm,
    round(c.pct_of_book, 2)      AS pct_of_book,
    round(c.cumulative_pct, 2)   AS cumulative_pct,
    h.n_buckets,
    round(h.hhi_raw, 1)          AS hhi_raw,
    round(h.hhi_floor, 1)        AS hhi_floor,
    -- the only number a limit should be set against
    round((h.hhi_raw - h.hhi_floor) / (10000.0 - h.hhi_floor), 3) AS hhi_normalised
FROM cumulated c
JOIN hhi h USING (dimension)
ORDER BY c.dimension, c.rank_by_exposure;

-- =============================================================================
-- VERIFIED - Top-N by state, live book (asserted by python/verify_claims.py):
--     Top-1  (CA)   13.27%
--     Top-3         29.86%
--     Top-5         41.26%
--     Top-10        58.10%
--     Top-20        79.60%
-- =============================================================================
