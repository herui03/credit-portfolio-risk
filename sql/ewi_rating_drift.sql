-- =============================================================================
-- ewi_rating_drift.sql - does "grade B" still mean what it used to?
-- =============================================================================
-- WHY THIS EXISTS: it closes a control gap I found in my own limit framework.
--
--   config/risk_limits.csv L-04 caps grade E/F/G at 8% of the book.
--   config/risk_limits.csv L-07 caps grade HHI*.
--   BOTH are denominated in "grade" and both assume the label means a constant
--   thing over time.
--
--   It doesn't. Within-grade MOB-12 default, 2013 -> 2016:
--       A  1.16 -> 1.75   (+51%)
--       B  2.88 -> 4.15   (+44%)
--       C  5.25 -> 7.90   (+50%)
--       D  7.96 -> 12.62  (+59%)
--
--   Every grade deteriorated INTERNALLY. A 2016 "grade B" defaulted 44% more than
--   a 2013 "grade B". So across 2013-2016 the grade MIX was roughly stable while
--   the risk inside every bucket rose 44-59%, and L-04 / L-07 would have read
--   GREEN through the entire deterioration. The limit was measuring a label, not
--   a risk. See docs/challenge-04-the-recession-that-helped.md.
--
--   A limit denominated in an internal rating requires the rating's MEANING to be
--   monitored separately. This file is that monitor.
--
-- METHOD
--   Compare each grade's MOB-12 cumulative default against its OWN baseline -
--   the mean of the 2013-2015 vintages. Baseline choice is a judgement and is
--   declared in config/ewi_thresholds.csv: 2013-2015 are the earliest three
--   vintages that are both fully observed to MOB 12 and drawn from the
--   post-GFC, at-scale business (2012 and earlier are a different company -
--   the 2007 vintage is 603 loans against 2017's 320,419).
--
--   Drift is measured WITHIN grade, which is what removes the mix confound that
--   inverted the macro correlation in challenge-04.
--
-- Grain: one row per (grade, vintage_yr). 36-month loans only - 36s and 60s have
-- structurally different hazard profiles and must never be pooled.
-- =============================================================================

WITH flagged AS (
    SELECT
        grade,
        vintage_yr,
        mob_observed,
        -- mob_default, NOT mob_stopped_paying: the latter is NULL for the 2,325
        -- zero-principal defaults and NULL <= 12 silently becomes "no". See
        -- docs/challenge-05-unknown-is-not-zero-again.md
        CASE WHEN is_charged_off = 1 AND mob_default <= 12 THEN 1 ELSE 0 END AS d12
    FROM loan
    WHERE term_clean = '36 months'
      AND grade IS NOT NULL
      AND loan_status IS NOT NULL
),

by_vintage AS (
    SELECT
        grade,
        vintage_yr,
        count(*)                            AS n_loans,
        100.0 * sum(d12) / count(*)         AS mob12_pct
    FROM flagged
    -- same gate as vintage_curve.sql: a cohort not observed to MOB 12 is UNKNOWN,
    -- and unknown is not zero. It gets no row rather than a flattering number.
    WHERE mob_observed >= 12
    GROUP BY grade, vintage_yr
),

baseline AS (
    SELECT
        grade,
        avg(mob12_pct) AS baseline_pct
    FROM by_vintage
    WHERE vintage_yr BETWEEN 2013 AND 2015
    GROUP BY grade
)

SELECT
    v.grade,
    v.vintage_yr,
    v.n_loans,
    round(v.mob12_pct, 2)                                   AS mob12_pct,
    round(b.baseline_pct, 2)                                AS baseline_pct,
    round(100.0 * (v.mob12_pct / b.baseline_pct - 1), 1)    AS drift_pct
FROM by_vintage v
JOIN baseline b USING (grade)
ORDER BY v.grade, v.vintage_yr;

-- =============================================================================
-- VERIFIED OUTPUT - drift vs each grade's own 2013-2015 baseline
-- (asserted by python/verify_claims.py against this exact file)
--
--   The 2016 vintage, every grade:
--     grade   n_loans   baseline   2016    drift
--       A      66,862     1.27      1.75   +36.9%
--       B     114,783     3.12      4.15   +33.0%
--       C      92,317     5.99      7.90   +31.8%
--       D      36,707     9.22     12.62   +36.8%
--
--   Four independent grades, drifting +31.8% to +36.9% in the same direction, in
--   the same year, on 310,669 loans. That is not noise in a grade - it is the
--   scale itself moving.
--
-- NOTE ON THIS BLOCK: the first version of this comment carried numbers I had
-- estimated before running the file - baselines of 3.05 / 5.85 / 9.03 and drifts
-- of +35% to +40%. They were wrong, and they were sitting under a heading that
-- said "VERIFIED". Nothing is verified because a comment says so. These figures
-- are pasted from an actual run and asserted in verify_claims.py, which is the
-- only reason the word belongs here.
-- =============================================================================
