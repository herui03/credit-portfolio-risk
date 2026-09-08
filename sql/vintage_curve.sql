-- =============================================================================
-- vintage_curve.sql - MOB-matched cumulative default by vintage
-- =============================================================================
-- WHY THIS FILE EXISTS
--   sql/naive_vintage_trap.sql reports default rate with the whole vintage as
--   denominator. On young vintages that is right-censored, and it fabricated a
--   90% "improvement" that was purely cohort age.
--
--     Measured naively      2015 18.00%  ->  2018 1.79%   (looks like improvement)
--     Measured MOB-matched  2011  3.86%  ->  2016 6.18%   (real deterioration, +60.1%)
--
--   Same data. Opposite sign. The only difference is holding the observation
--   window constant. See docs/challenge-01-maturity-bias.md
--
-- THE RULE THIS ENFORCES
--   A cohort not observed to $target_mob returns NO ROW. Not a small number, no
--   row. A gap in the chart is the honest output. An unobserved cohort is UNKNOWN,
--   and unknown is not zero
--
-- ASSUMPTION (see docs/assumptions_and_limitations.md)
--   MOB of default comes from mob_stopped_paying = last_pymnt_d - issue_d, i.e.
--   when the borrower STOPPED PAYING. Accounting charge-off typically follows
--   120-150 days later, so this curve sits ~4-5 months early versus a true
--   charge-off-date curve. Chosen deliberately: for an EWI the earliest observable
--   signal is the right anchor. Do NOT benchmark against a charge-off-date curve
--   without adjusting for the shift
--   Coverage: 2,325 of 269,320 charged-off loans lack last_pymnt_d (0.86%)
--
-- PARAMETERS (DuckDB named style)
--   $target_mob   e.g. 12
--   $term_filter  e.g. '36 months'   (term mixes 36/60mo maturities; curves are
--                                     only comparable within a single term)
-- Grain: one row per vintage_yr. Basis: table `loan` (all loans, not just live -
-- default is an outcome, and closed loans are exactly where outcomes are observed)
-- =============================================================================

WITH flagged AS (
    SELECT
        vintage_yr,
        mob_observed,
        -- Defaulted BY the target MOB. BOTH conditions are required:
        --   1. it charged off at all, AND
        --   2. it stopped paying on or before the target MOB.
        -- A loan that charges off at MOB 30 is NOT a default "by MOB 12" - it was
        -- healthy at month 12, and counting it would leak the future backwards
        -- into the cohort's month-12 state.
        CASE
            WHEN is_charged_off = 1
             AND mob_default <= $target_mob
            THEN 1 ELSE 0
        END AS defaulted_by_target_mob
    FROM loan
    WHERE term_clean = $term_filter
      AND loan_status IS NOT NULL
)

SELECT
    vintage_yr,
    count(*)                                                    AS n_loans,
    sum(defaulted_by_target_mob)                                AS n_defaulted,
    round(100.0 * sum(defaulted_by_target_mob) / count(*), 2)   AS cum_default_pct
FROM flagged
-- THE GATE. This is the whole point of the file.
-- Only cohorts old enough to have been watched for $target_mob months are
-- comparable. Everything younger is unknown, and unknown is not zero
WHERE mob_observed >= $target_mob
GROUP BY vintage_yr
ORDER BY vintage_yr;

-- =============================================================================
-- VERIFIED OUTPUT - $target_mob = 12, $term_filter = '36 months'
-- (asserted by python/verify_claims.py against this exact file)
--
--   vintage_yr   n_loans   cum_default_pct
--         2007       603              9.62
--         2008     2,393              9.03
--         2009     5,281              5.81
--         2010     9,156              4.17
--         2011    14,101              3.86   <- trough
--         2012    43,470              5.01
--         2013   100,422              4.15
--         2014   162,570              4.60
--         2015   283,173              5.20
--         2016   323,495              6.18   <- peak (+60.1% vs 2011)
--         2017   320,419              5.52
--
--   2018 is ABSENT. Not zero, not 1.79% - absent. The warehouse as-of date is
--   2018-12-01, so no 2018 vintage has been observed to MOB 12. That absence is
--   the gate working
-- =============================================================================
