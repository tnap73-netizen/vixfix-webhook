# BMCMC Edge Detector Two-Sided v3.0

Status: repo-owned canonical implementation spec.

Supersedes:

- `BMCMC_PEAD_EdgeDetector_v2.md`
- `BMCMC_PEAD_EdgeDetector_Spec.md`

Purpose: run BMCMC's Pre-EAD drift, live PEAD v2 continuation, and a market-neutral relative version through the same portable decision gate, then answer which part of the earnings cycle, if any, produces real alpha after stripping market beta, momentum, size, and value.

The output is not a prettier equity curve. It is a PASS/FAIL verdict per arm, written to the signal archive as diligence-grade evidence. When the gate fires, the backtesting loop on this question closes.

## Governance preconditions

- **Subscription registry check**: before any feed is touched, confirm every dependency maps to an already-subscribed endpoint in `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md`.
- **No new vendor without reconciliation**: vendor audit is mandatory before any new service request.
- **Signal archive wiring**: all outputs are written to `bmcms_signal_archive`, append-only and SHA-256 hash-chained, with parameter snapshot, git commit hash, and T+1/T+5/T+30/T+90 outcome backfills.
- **Canonical state**: reference the current BMCMC complete state before running. No Bloomberg, no TrendSpider, no EMA-fan dependency anywhere in this run.

## Three arms

| Arm | Trades | Construction | Entry | Exit | Beta exposure | Question |
|---|---|---|---|---|---|---|
| Arm C: Pre-EAD Drift | Before the print | Stock-only, two-sided; long top-ESS / short bottom-ESS pre-EAD names | Signal-triggered; sign follows signal | C1 exits at/before close prior to announcement; C2 hold-through is shadow ledger only | Carries market beta | Is pre-print drift real edge or just buy/sell-the-rumor beta? |
| Arm A: PEAD v2 Continuation | After the print | Two-sided; long strong signal / short weak-or-miss qualifying names | At/after first full post-announcement session | Day-7 time stop and +75% profit lock | Carries market beta by design | Does the live system have edge beyond beta and momentum? |
| Arm B: Market-Neutral Relative | After the print | Long top-signal vs short weak/miss peer, sector and beta matched | Same as A, both legs | Same hold grid, 5/10/20/40/60d | Neutralized by construction | Does the idiosyncratic signal have edge once beta is removed? |

All arms are scored on the same ESS, over the same universe and costs, and feed the same portable gate. The only difference is when and how they trade.

## Direction-agnostic rule

The detector imposes no directional thesis. On every arm, position sign follows signal sign:

- Strong catalyst: long.
- Weak/miss catalyst: short.

The gate asks one neutral question per arm and per tail: after stripping market, momentum, size, and value, is there alpha left?

Long and short tails are scored as separate return series so a strong long tail cannot mask a dead short tail, and vice versa.

## Walling rules

- **Arm C is stock-only and paper-first**: no options vehicle and no live capital in the pre-EAD test.
- **Arm C short tail is research-only** until it independently passes the gate and borrow is confirmed realistic.
- **Long and short tails are distinct series** per arm: `C-long`, `C-short`, `A-long`, `A-short`.
- **Each tail runs the gate independently** and may be combined into a sleeve only after both pass on their own.
- **Any live short carries borrow cost and locate realism**. A short-tail edge that exists only at zero borrow is not deployable.
- **No position is credited to two arms**. C1 exits before the print. Arm A enters after the print. They never overlap on the same event under both labels.
- **C2 hold-through is informational only**. It quantifies what spanning the print would add. It is never summed into PEAD or pre-EAD headline attribution.

## Hypotheses

- **H_C pre-EAD**: pre-print drift contains positive alpha after removing MKT + MOM + SMB/HML. Tested under C1 as the deployable claim. C2 is measured only to quantify what spanning the print adds.
- **H_A PEAD v2 continuation**: post-print continuation returns contain positive alpha after removing MKT + MOM + SMB/HML.
- **H_B market-neutral relative**: market-neutral relative construction contains positive alpha after the same strip-out.
- **H0 null, per arm**: returns are fully explained by beta and momentum; no demonstrated edge.

Reject H0 only on significant, positive, out-of-sample alpha. Each arm and each tail is tested independently.

## Earnings Signal Score

Rank every earnings candidate by a composite of structured catalyst fields that BMCMC actually subscribes to. All fields must be point-in-time as delivered by the feeds.

| Component | Source | Field logic | Weight |
|---|---|---|---:|
| SUE / earnings surprise | Massive entitlement: Benzinga Earnings | Actual EPS minus consensus, standardized by recent surprise dispersion; include revenue surprise | 30% |
| Guidance impulse | Massive entitlement: Benzinga Corporate Guidance | Guidance raise/cut direction times magnitude vs prior | 25% |
| Analyst-rating / PT revision | Massive entitlement: Benzinga Analyst Ratings | Net upgrade/downgrade plus price-target raise momentum in post-print window | 20% |
| Smart-money / insider catalyst | EDGAR Speed Feeds | Insider buying, Form 4 clusters, critical filing flags | 15% |
| Post-event confirmation | Schwab/ToS market data or registered OHLCV substitute | First-session abnormal return times relative volume | 10% |

Rules:

- Standardize each component cross-sectionally with z-scores inside the event window before weighting.
- Pre-register weights before the run. Do not tune weights to the result.
- Attach a separate pre-EAD tag: `pre_run_spent`, `clean`, or `buy_the_rumor_risk`.
- The pre-EAD tag is separate from ESS and used as a filter or conditioning variable.

If Benzinga/Massive are unavailable, follow `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md` reduced-ESS doctrine and mark missing components `unavailable_this_run`.

Canonical Massive package for BMCMC:

- Options Starter.
- Benzinga Analyst Ratings.
- Benzinga Corporate Guidance.
- Benzinga Earnings.

These are accessed through the unified Massive key. The required Railway variable is `MASSIVE_API_KEY`.

## Universe

Run both universes:

- **Research universe**: survivorship-bias-free, includes small/mid caps, liquidity floor such as ADTV above $5M and price above $5.
- **Deployable universe**: names tradable at BMCMC size with acceptable borrow for Arm B short leg and acceptable options liquidity if/when options layer is added.

Report the research-vs-deployable gap per arm. That gap is the true capacity constraint.

## Costs and execution realism

- Model commissions, slippage, and bid/ask on every leg.
- Model borrow cost and locate realism on every short series.
- Report gross and net.
- An edge that exists only gross is not an edge.
- Equity-first for the edge test. Options are layered only after an arm passes.
- Arm C carries no options vehicle and no live capital in the pre-EAD test.
- C1 exits before the print, so it carries zero IV-crush and earnings-gap exposure.
- C2 deliberately carries the gap and is ledgered separately.

## Portable decision gate

The decision gate is feed-agnostic. It takes any strategy return series and returns a verdict.

Regression:

```text
R_arm(t) - Rf(t) = alpha + beta_mkt*MKT(t) + beta_mom*MOM(t) + beta_smb*SMB(t) + beta_hml*HML(t) + error
```

Factors:

- MKT
- MOM
- SMB
- HML

Use Fama-French or AQR daily factor datasets. Include SMB/HML because Arm B and the small/mid universe carry size exposure.

Implementation:

- Python `statsmodels` OLS on each arm's net return series.
- Report Newey-West HAC standard errors.
- Metrics: annualized alpha, HAC t-stat of alpha, beta_mkt, beta_mom, SMB/HML, R-squared.

## Stop rule

Set thresholds before running.

PASS, all required:

- Alpha positive and economically meaningful: approximately 3-4% annualized net of costs or better.
- HAC t-stat of alpha at or above approximately 2.0.
- Beta_mom small enough that alpha is not just momentum.
- Holds on the out-of-sample slice.

FAIL, any condition:

- Alpha approximately zero or negative net.
- HAC t-stat below approximately 2.0.
- High R-squared with beta_mom or beta_mkt carrying the return.

If fail, no parameter tweaking. Redeploy engine time to a different hypothesis.

## Three-way verdict

Each arm and each tail runs independently.

- **Only C passes**: edge is in the run-up, not continuation. Deploy pre-EAD module stock-only, paper-to-live. Shelve A and B.
- **Only A passes**: live continuation system has real edge. Deploy A. Shelve C and B.
- **Only B passes**: edge is idiosyncratic and beta was masking it. Migrate toward market-neutral construction.
- **C and A both pass**: edge spans the cycle. Check double-counting first. Because C1 exits before print and A enters after print, they can run as sequential walled sleeves.
- **B plus C and/or A pass**: keep the neutral sleeve and any directional sleeve that beats it on net alpha after stripping beta.
- **All pass**: compare alpha, t-stat, and capacity. Size as diversified sleeves. Never blend C2 into the headline.
- **All fail**: PEAD/pre-EAD in these forms is not the edge. Stop running it and reallocate engine time.

C1 vs C2:

- If C1 passes but C2 does not, edge is purely pre-print and spanning the print destroys it.
- If C2 beats C1, spanning the print adds return, but that increment is earnings-gap risk premium. It is logged in its own ledger and never summed into pre-EAD or PEAD attribution.

Code assertion:

- A single price move on a single event may be credited to at most one arm.
- C1 owns pre-print.
- A owns post-print.
- B owns the neutralized spread.
- C2 is shadow ledger only.

## Out-of-sample discipline

- Split history: in-sample around 60-70%, out-of-sample remainder.
- Gate must pass out-of-sample, not just in-sample.
- Prefer walk-forward rolling re-fit if history allows.
- Pre-register thresholds and ESS weights before the run.
- Log thresholds and weights to the signal archive.

## Run checklist

1. Subscription Registry reconciled; all feeds already subscribed.
2. Point-in-time Benzinga Earnings/Ratings/Guidance and EDGAR fields wired with no look-ahead.
3. For Arm C, every signal field timestamp is strictly before the announcement it is used against.
4. ESS computed and cross-sectionally standardized; pre-EAD tag attached.
5. Arm C built: signal-triggered, sign follows signal, stock-only, C1 and C2 measured separately, short tail detection/research-only.
6. Arm A built two-sided with live exits: day-7 time stop and +75% lock.
7. Arm B built sector/beta-matched long/short.
8. Long and short tails split before scoring.
9. Research and deployable universes both run.
10. Costs modeled per arm; gross and net reported.
11. Holding-period/window grid run; drift decay reported per arm.
12. Net return series exported per arm, with C1 and C2 distinct.
13. Portable gate run on each arm and each tail: C1-long, C1-short, A-long, A-short, B, and C2 separately.
14. Out-of-sample or walk-forward confirmation completed.
15. Three-way verdict computed, including C1-vs-C2 sub-read.
16. No-double-counting rule asserted in code.
17. Run and verdict written to `bmcms_signal_archive` with params, git hash, and T+1/T+5/T+30/T+90 backfills scheduled.
18. C2 flagged as shadow ledger.

## One-line summary

Run pre-EAD drift, live PEAD v2 continuation, and a market-neutral relative version on the same Benzinga/EDGAR-scored signal, same universe, same costs, then feed each into one portable factor-regression gate. Whichever arm's alpha survives beta, momentum, size, and value with out-of-sample t-stat at or above approximately 2 is where the real edge lives. C2 is shadow ledger only. No single price move is ever credited to two arms.
