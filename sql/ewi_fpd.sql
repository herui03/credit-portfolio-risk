-- =============================================================================
-- ewi_fpd.sql - First-Payment Default by vintage
-- =============================================================================
-- WHAT FPD IS
--   A loan that charges off having NEVER made a payment. It is the canonical
--   earliest warning indicator in consumer lending, because it cannot be explained
--   by anything that happened to the borrower AFTER origination. A borrower who
--   never pays once was either mis-underwritten, misrepresented, or fraudulent at
--   the point of sale. FPD measures the quality of the decision, not the economy.
--
-- DEFINITION USED HERE
--   total_pymnt = 0 AND charged off.
--   Clean in this data: 949 loans have total_pymnt = 0; ZERO of them have a
--   last_pymnt_d, so the definition is internally consistent. 848 are charged off;
--   the other 101 are still labelled "Late (31-120 days)" - see the gate below.
--
-- THE GATE, AND AN HONEST NOTE ABOUT IT
--   A never-paying loan takes ~5 months to be LABELLED charged off (30/60/90/120
--   days past due, then charge-off). So recent vintages are censored: the loan has
--   already failed but the label hasn't caught up. The 101 un-labelled never-payers
--   sit at mob_observed 0-2, confirming exactly that.
--
--   So this file gates on mob_observed >= 6.
--
--   BUT: measured, the gate barely does anything.
--       2018 ungated  : 0.070%
--       2018 mob >= 6 : 0.073%   (+0.003pp)
--   FPD is a ~0.07% event and the un-labelled population is 101 loans against a
--   495,242-loan vintage. The gate is PROTECTIVE, not MATERIAL, and saying
--   otherwise would be dressing up a cosmetic control as rigour. It is kept
--   because the principle generalises to a live feed where the cut-off is today
--   and the censored share is much larger - not because it rescued this number.
--
-- WHY THIS INDICATOR EARNS ITS PLACE
--   Observability is the entire point:
--       FPD                  speaks from ~MOB 5
--       MOB-12 vintage curve speaks from  MOB 12
--   For the 2018 vintage the MOB-12 curve returns NO ROW - the cohort is too young
--   to know (see vintage_curve.sql's gate). FPD returns 0.073%, the highest in the
--   book's history. The slow indicator is silent exactly when the fast one is
--   screaming. That is what an early warning indicator is for.
--
-- Grain: one row per vintage_yr. Basis: all loans (FPD is an outcome, so closed
-- loans are where it is observed).
-- =============================================================================

SELECT
    vintage_yr,
    count(*)                                                    AS n_loans,
    sum(CASE WHEN total_pymnt = 0 AND is_charged_off = 1
             THEN 1 ELSE 0 END)                                 AS n_fpd,
    round(100.0 * sum(CASE WHEN total_pymnt = 0 AND is_charged_off = 1
                           THEN 1 ELSE 0 END) / count(*), 3)    AS fpd_pct
FROM loan
WHERE loan_status IS NOT NULL
  -- the gate: only loans old enough for a never-payer to have been LABELLED.
  -- Empirically the un-labelled never-payers max out at mob_observed = 2; 6 is the
  -- principled floor from the 120-150 day charge-off process.
  AND mob_observed >= 6
GROUP BY vintage_yr
ORDER BY vintage_yr;

-- =============================================================================
-- VERIFIED OUTPUT (asserted by python/verify_claims.py)
--
--   vintage_yr   n_loans     n_fpd   fpd_pct
--         2013   134,814        16     0.012
--         2014   235,629        36     0.015
--         2015   421,095        68     0.016
--         2016   434,407       140     0.032
--         2017   443,579       210     0.047
--         2018   238,636       175     0.073   <- highest in the book's history
--
--   FPD rose ~5x from its 2013-2015 baseline of 0.014%. It is monotonic from 2014.
--   This corroborates the rating drift in challenge-04 (within-grade MOB-12 default
--   up 44-59% from 2013 to 2016) from a completely independent direction - and it
--   does so a year earlier than the vintage curve can.
-- =============================================================================
