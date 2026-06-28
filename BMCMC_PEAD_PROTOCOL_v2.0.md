# BMCMC PEAD Protocol v2.0

Status: repo-owned doctrine  
Owner: BMCMC LLC  
Effective date: 2026-06-27  
Current implementation status: recovery shim only until full v2 evaluator is recovered

## Doctrine locks

- No price stops. Time stops only.
- PEAD vehicle is 30-day ATM call structure. Never use Jan 2027 LEAPS for PEAD.
- Friday entries are allowed.
- Every alert must include market health context.
- Vendor audit is required before requesting or adding new services.
- No Bloomberg dependency after 2026-06-29.
- No custom `/exec` endpoint. Use Railway native shell, Railway native cron, repo-owned scripts, or approved connectors.
- SMS route is Verizon gateway only through `7187047511@vtext.com` until replaced.
- Do not call in-app notification for BMCMC trading alerts.

## Purpose

PEAD v2.0 is the BMCMC daily post-earnings-announcement-drift scanner. It runs pre-market on market days, evaluates fresh earnings-related events, gates them through BMCMC trading doctrine, records paper-test positions during the current evaluation window, and routes only actionable fires to the SMS queue.

## Canonical schedule

- Name: BMCMC daily PEAD scan.
- Time: 08:30 ET, Monday through Friday.
- UTC cron during EDT: `30 12 * * 1-5`.
- Paper-test window: through 2026-07-10.
- Current no-delete lock: both `aadcd5f8` and `aa59ac63` remain active until the duplicate slot is intentionally deleted after confirmation.

## Slot authority

- `aadcd5f8` contains the original Protocol v2.0 scheduled-task text.
- `aa59ac63` contains the replacement recovery-shim scheduled-task text.
- Delete candidate: `aa59ac63` only after the operator confirms `aadcd5f8` remains the desired source of truth or after repo-owned replacement is live and verified.
- Until then, no-delete holds.

## Required credential path

- Current Perplexity run path requires `api_credentials=["custom-cred:api.massive.com"]`.
- Railway cutover is blocked until Massive/Benzinga credentials are added to Railway or shared Railway variables.
- Proof result from 2026-06-28T00:30Z: Railway scheduled env injection works for Schwab, QuantData, and FINVIZ references, but `MASSIVE_API_KEY` and `BENZINGA_API_KEY` are absent.

## Canonical run command

From the scanner root:

```bash
python3 -m scrapers.run_all --force
```

Current sandbox path:

```bash
cd /home/user/workspace/edgar_speed_feeds && python3 -m scrapers.run_all --force
```

Current Railway target path after repo cutover:

```bash
python3 -m scrapers.run_all --force
```

## Expected scanner outputs

- Alerts file: `edgar_speed_feeds/alerts/YYYY-MM-DD_pead.jsonl`
- Run log: `edgar_speed_feeds/logs/run_all.log`
- Paper positions: `edgar_speed_feeds/paper_test/positions.jsonl`
- SMS queue: `edgar_speed_feeds/alerts/sms_queue.jsonl`

## Fire definition

Count only records where:

- `event == "FIRE"`, or
- `type == "PEAD_ALERT"`

Do not count observation records, including:

- `OBSERVE`
- `BENZINGA_OBSERVE`
- raw `PEAD_SETUP` records

## Paper-position record

For each fire during the paper-test window, append one record with:

- `ticker`
- `entry_date`
- `vehicle="30d ATM call"`
- `contracts=1`
- `entry_premium`, preferably from alert vehicle premium mid when available
- `exit_target_date`, seven business days after entry
- `profit_lock_pct=75`
- `sue_pct`, when available
- `gates_passed`, when available
- `tier`, when available
- `friday_entry`, boolean

## SMS routing

- Each actionable alert must route through `edgar_speed_feeds/alerts/sms_queue.jsonl`.
- Body cap: 155 characters.
- Required body elements: BMCMC prefix, ticker, setup type, market health summary.
- Summary SMS after scan only if fires are greater than zero:

```text
BMCMC SCAN <YYYY-MM-DD> | fired:<N> | paper wk<W> day<D>
```

- If fires equal zero, stay silent.
- Never call `send_notification`.

## Error handling

- On any auth/API error, read `edgar_speed_feeds/logs/run_all.log`.
- Report the exact HTTP status and error text.
- Never assume calendar-thin without log confirmation.
- If Benzinga/Massive returns:
  - `200` with empty records: vendor returned no records.
  - `401`: credential injection or key problem.
  - `429`: rate limit or external burner.
  - timeout: upstream/network/runtime issue.

## Recovery-shim warning

The current committed `edgar_speed_feeds` implementation is a recovery shim, not the full v2 evaluator. It exists to preserve a working repo-owned scanner shell while full v2 recovery continues. Any run of the shim must log and communicate that it is the recovery shim.

The recovery shim currently fetches Massive/Benzinga ratings, earnings, and guidance endpoints, writes PEAD JSONL output, and emits high-signal recovery events. It does not replace the original full v2 evaluator until explicitly promoted.

## Cutover gate

Do not cut over PEAD from Perplexity scheduled tasks to Railway until all are true:

- `cron_registry.json` exists in repo.
- Full target job is version-controlled.
- Massive/Benzinga credentials are visible to scheduled Railway runs.
- One manual Railway run completes.
- One native Railway scheduled run completes.
- Output matches or improves on the Perplexity scheduled-task output.
- Old task remains active until replacement is verified.

