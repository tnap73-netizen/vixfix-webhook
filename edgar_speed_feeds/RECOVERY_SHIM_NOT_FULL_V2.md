# Recovery Shim, Not Full PEAD v2

This directory is currently a recovery shim.

It is being version-controlled so BMCMC has a repo-owned scanner path while full PEAD v2.0 recovery continues. This shim must not be represented as the original full v2 evaluator.

## Current role

- Preserve a runnable `edgar_speed_feeds` package.
- Test Massive/Benzinga credential injection.
- Fetch recovery endpoints for ratings, earnings, and guidance.
- Write JSONL alert output.
- Provide enough structure for scheduled-run migration work.

## Current limitations

- Not the original full PEAD v2 evaluator.
- Not final production scoring doctrine.
- Not final alert-composer pipeline.
- Not final SMS dispatch pipeline.
- Not final market-health integration.
- Disables TLS verification for `api.massive.com` only because the current custom-credential proxy chain presents a self-signed certificate. Permanent fix is a proper CA bundle or Railway-native secret path.

## Promotion rule

Do not promote this shim to production PEAD v2 until:

- Full v2 evaluator source is recovered or intentionally rebuilt.
- Massive/Benzinga credentials are available to Railway scheduled runs.
- Market health is integrated into every alert.
- Paper-position output matches BMCMC doctrine.
- One manual Railway run succeeds.
- One native Railway scheduled run succeeds.
- Old Perplexity scheduled task remains live until replacement output is verified.

