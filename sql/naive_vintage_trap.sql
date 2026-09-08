-- =============================================================================
-- naive_vintage_trap.sql - THE QUERY THAT LIED. Kept deliberately.
-- =============================================================================
-- This is the first portfolio metric I wrote, and it is wrong. It is committed
-- on purpose: the gap between this file and vintage_curve.sql IS the finding.
-- See docs/challenge-01-maturity-bias.md.
--
-- WHAT IT DOES WRONG
--   Denominator = the whole vintage. Numerator = loans that have ALREADY failed.
--   On a young vintage those are structurally mismatched: a 2018 loan on a 36- or
--   60-month term has not had time to default, and this counts it as a success.
--   That is right-censoring. Censored records are not negatives -
--   they are UNKNOWN, and treating unknown as "no" fabricates a trend.
--
-- WHY IT IS DANGEROUS RATHER THAN MERELY WRONG
--   Every number it returns is arithmetically correct. Nothing errors. The output
--   is a clean, plausible, *flattering* improving trend. The bug is in the
--   question, not the code.
--
-- THE TELL, VISIBLE IN ITS OWN OUTPUT
--   naive_default_pct falls in near-perfect lockstep with still_current_pct rising.
--   Any risk metric that moves monotonically with cohort age is measuring age.
--   still_current_pct is therefore selected here on purpose - it is the antidote,
--   and it must never be dropped from this output.
--
-- Run: see python/verify_claims.py (executes this file and asserts the numbers)
-- =============================================================================

SELECT
    vintage_yr,
    count(*)                                                        AS n_loans,
    -- WRONG: denominator includes loans that cannot yet have defaulted
    round(100.0 * sum(is_charged_off) / count(*), 2)                AS naive_default_pct,
    -- the tell - kept adjacent so the metric can never be read without it
    round(100.0 * sum(CASE WHEN loan_status = 'Current' THEN 1 ELSE 0 END)
                / count(*), 2)                                      AS still_current_pct,
    round(100.0 * sum(is_resolved) / count(*), 2)                   AS resolved_pct,
    -- the honest-ish alternative denominator (ALSO biased - see below)
    round(100.0 * sum(is_charged_off)
                / nullif(sum(is_resolved), 0), 2)                   AS resolved_only_default_pct
FROM loan
WHERE loan_status IS NOT NULL
GROUP BY vintage_yr
ORDER BY vintage_yr;

-- =============================================================================
-- NOTE ON resolved_only_default_pct - IT IS NOT THE FIX
--   Restricting to resolved loans does not remove the bias, it FLIPS it. Among
--   young loans the already-resolved population is selected for speed: charge-offs
--   land at a median of 14.0 months on book, while the good outcomes - full-term
--   payoffs - cannot resolve before month 36 or 60. So resolved-only OVERSTATES
--   default on recent vintages.
--
--   2018: naive 1.79%  |  resolved-only 15.75%  -> neither is 2018's default rate.
--   Both are artifacts of WHEN we looked. The fix is holding months-on-book
--   constant - see vintage_curve.sql.
-- =============================================================================
