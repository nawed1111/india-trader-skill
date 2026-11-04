# India Trader skill, P3 (index options, buying only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the pack plan, size, check and send intraday BUYS of NIFTY and BANKNIFTY options (calls and puts), sized by premium, with option costs, expiry-day rules, and a Time Machine that reprices the option along each replayed path.

**Architecture:** Builds on P2 (must be on `main` first): the signal is read on the index, contracts come from the F&O bhavcopy. An option's price at any index level and time comes from Black-Scholes in `india.py`, with the implied volatility backed out of the latest premium (the user's Kite quote, or the last bhavcopy close) and held constant. The plan stores the option's stop and target as premiums and the index levels they correspond to at entry. Option SELLING (writing) is out of scope and blocked.

**Tech Stack:** Python 3.8+, standard library only (`math.erf` for the normal CDF), `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-04-india-trader-skill-design.md` (P3 section). P2 plan: `docs/superpowers/plans/2026-11-04-india-trader-p2-futures.md`.

## Global Constraints

- Everything in the P1 and P2 Global Constraints still holds (stdlib, 3.8+, self-contained folders, identical `india.py`, IST, paper default, three gates, `allow_fno` required, lots in units, expiries and lots from NSE files).
- Buy to open only (CE or PE). A sell that opens or adds to a short option position is BLOCKED, whatever the config says. Selling to close a bought option is an exit.
- Option prices are on the Rs 0.05 tick (3 Nov 2026 bhavcopy: every IDO price ends in 0 or 5).
- NIFTY has weekly (Tuesday, moved to the trading day before when Tuesday is a holiday) and monthly expiries; BANKNIFTY monthly only. Always read them from the bhavcopy.
- Black-Scholes assumptions are config values, said in every report: `risk_free_rate` (default 0.06), no dividend yield, time to expiry = calendar minutes to 15:30 IST on expiry day / (365 x 1440). IV constant for the whole replay.
- Option costs: `india.round_trip("opt", ...)` (Rs 20 a order flat, STT 0.15 % of premium on the sell, exchange 0.03553 % of premium incl. IPFT), checked in Task 1.
- A premium the tool estimated (from an older bhavcopy) is always labelled "estimated", and a market-priced entry on an estimate is blocked: options move too fast for an EOD price.

## Review Focus

1. **Expiry day:** theta and gamma are extreme in the last hours. Risk BLOCKs new entries in a contract expiring today after `expiry_day_cutoff` (default 13:00), and alerts ring at 15:00 on expiry day for any open option (an ITM option left to expiry pays STT on its intrinsic value). (Tests in Tasks 6 and 8.)
2. **IV that will not solve:** a premium below intrinsic value or above the index price has no IV; the tool refuses with the reason, never prints a number. (Test in Task 2.)
3. **Illiquid strikes:** a strike with open interest under `min_option_oi` (config, default 50,000 units) or no trades in the last bhavcopy: entry warns and risk BLOCKs. (Tests in Tasks 3 and 6.)
4. **Costs on cheap options:** a Rs 3 premium option bought for 1 lot pays Rs 40 of brokerage on a Rs 195 position: the cost-share check must block it. (Test in Task 6.)
5. **Premium stop below zero or target past what BS can reach before expiry:** exit clamps the premium stop at one tick and refuses a target the index move cannot reach by the flat-by under the model. (Test in Task 4.)

---

### Task 1: Data and model check (stop for review)

**Files:**
- Modify: `tools/probe.py`, `docs/p0-findings.md` ("P3 findings")
- Create: `tests/fixtures/p3/` (`zerodha-calc-opt.json`, `iv-check.json`, the bhavcopies the example needs)

- [ ] **Step 1:** Zerodha's calculator, options tab: three cases saved as `zerodha-calc-opt.json` (1 lot NIFTY premium 120 to 150; 2 lots BANKNIFTY 400 to 380; 1 lot NIFTY 3.00 to 3.50). Read `cal_options` to confirm rounding.
- [ ] **Step 2:** Reference IVs: for three NIFTY strikes (ATM, 2 strikes OTM call, 2 strikes OTM put) on the 3 Nov 2026 bhavcopy, record an independent IV (Zerodha's or NSE's option chain, read in the browser) with the inputs used. Save as `iv-check.json`. Our BS + IV solver must land within 0.5 IV points of these with the same inputs; if not, find out why before Task 2 ships.
- [ ] **Step 3:** Confirm: Zerodha's rules on MARKET orders for index options (limit-only or market protection), SL vs SL-M for options, the STT on exercised ITM options today, and the expiry-day freeze-quantity limits (orders above the freeze size are split; say so if the example's size could hit it).
- [ ] **Step 4:** Pick the worked example: the same session as P2's (or another in the fixtures) with an ATM NIFTY call bought on the index ORB trigger; save the bhavcopy of the previous session for its IV.
- [ ] **Step 5:** Commit: `docs: P3 data and model findings`.
- [ ] **Step 6: STOP.** Show the user "P3 findings"; revise the plan if the model check or a broker rule breaks it.

### Task 2: `india.py` options math

**Files:**
- Modify: `india/india.py` (then sync)
- Test: `tests/test_india.py`

**Interfaces:**
- Produces:
  - `norm_cdf(x) -> float` via `math.erf`
  - `bs_price(right: str, spot: float, strike: float, years: float, vol: float, rate: float = 0.06) -> float`
  - `implied_vol(right, premium, spot, strike, years, rate=0.06) -> float`: bisection on 0.01 to 3.00, tolerance 1e-6 on price; raises `ValueError("no implied volatility: ...")` below intrinsic or above the spot (call) / strike (put)
  - `years_to_expiry(now_ist: datetime, expiry: date) -> float`: calendar minutes to 15:30 IST on expiry / (365 x 1440); 0 after it
  - `option_symbol(symbol, expiry: date, strike: float, right: str, weekly: bool) -> str`: `NIFTY26N0924400PE` (weekly: YY + month code 1-9/O/N/D + DD) or `NIFTY26NOV24400CE` (monthly); `parse_option_symbol(text) -> dict`
  - `strikes(rows, symbol, expiry) -> list[float]`, `atm_strike(strikes, spot) -> float`, `pick_strike(strikes, spot, right, steps_otm: int) -> float`
  - `option_row(rows, symbol, expiry, strike, right) -> dict | None` (from P2's `parse_bhavcopy`)

- [ ] **Step 1: Write the failing tests:** put-call parity holds to 1e-6 (`C - P == S - K e^(-rT)`); `bs_price("CE", 100, 100, 1, 0.2, 0.05)` == 10.4506 (the textbook value, 4 dp); `implied_vol` returns the vol that priced it to 1e-6; a premium below intrinsic raises with "no implied volatility"; `years_to_expiry` from 2026-11-03 15:30 to the 2026-11-09 expiry == 6 / 365; the IVs in `iv-check.json` match within 0.5 points; `option_symbol("NIFTY", date(2026, 11, 9), 24400, "PE", weekly=True) == "NIFTY26N0924400PE"` and the bhavcopy's contract names round-trip through `parse_option_symbol`; `zerodha-calc-opt.json` rows match `round_trip("opt", ...)` within Rs 0.01.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Sync, full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(india): Black-Scholes, implied vol, option symbols and strikes`.

### Tasks 3 to 8: each skill learns `instrument: opt`

Same five-step pattern. `"eq"` and `"fut"` paths and all their tests stay unchanged.

| Task | Skill / files | Changes | Tests must assert |
| --- | --- | --- | --- |
| 3 | `bharat-entry/entry.py` | `--instrument opt --right CE|PE [--steps-otm N] [--expiry DATE] [--premium P]`: signal on the index (a CE on a close above the range high; a PE on a close BELOW the range low, so the PE path adds the long-on-the-put mirror of the ORB rule); the result adds `option` = `{contract, expiry, strike, right, lot, premium, premium_source, iv, oi, years}`; expiry default = nearest that is not today; premium = `--premium`, else BS at the trigger index price with IV from the last bhavcopy close (`estimated`); OI under `min_option_oi` warns. | The example's contract, strike (ATM) and estimated premium; `--premium` sets IV from it; a PE triggers on the first close under the range low; an illiquid strike warns. |
| 4 | `bharat-exit/exit.py` | `instrument: opt`: the index stop and target from the ORB rule (as P1), each converted to a premium with BS at the entry time (same IV, time to expiry at the entry), tick-rounded (stop down, target up); premium stop clamped at one tick; refuses a target the model cannot reach by flat-by (BS premium at the target index level < target premium after the time decay to flat-by). Plan keeps both: `stop`/`target` as premiums, `index_stop`/`index_target`. | Example premiums at the index stop and target; a deep OTM strike clamps or refuses with the reason; the plan file has both sets of levels. |
| 5 | `bharat-timemachine/timemachine.py` | `instrument: opt`: replay the index exactly as now; at each bar price the option with BS (path index, time left to expiry at that bar, the plan's IV) and decide stop / target on the premium; report odds, R and the premium at `--until`; history replay does the same on past sessions with each session's own expiry distance taken from the plan (a stated limitation: past sessions' IVs are not known, the plan's IV is used). | The example: odds sum to 1; with IV raised the stop-first share changes in the expected direction; seed 19 numbers pinned; the report names the IV and says it is held constant. |
| 6 | `bharat-budget/size.py` + `bharat-risk/check.py` | Budget: lots by premium: max loss = lots x lot x (premium - premium stop) + `round_trip("opt", ...)` at the stop; cash = lots x lot x premium (fully paid, no margin); `max_premium_inr` (config); order `exchange: NFO`, `product: MIS`, `type: limit` always (limit = premium). Risk: `allow_fno`; BLOCK any opening sell; lot multiple; BLOCK after `expiry_day_cutoff` on expiry day; BLOCK OI under `min_option_oi`; BLOCK a market order; BLOCK an estimated premium without a user premium; costs share with segment `opt`. | Example lots and costs; a Rs 3 premium 1-lot trade blocks on costs (Rs 40 brokerage alone on Rs 195); an opening sell blocks with "option selling is not part of this pack"; 13:05 on expiry day blocks; a market order blocks. |
| 7 | `bharat-broker/ticket.py` | Kite calls: LIMIT buy at the premium on NFO; after the fill one stop (SL with limit N ticks below the premium stop, or what Task 1 found); paper fills with `leg_costs("opt", ...)`; flatten sells at a limit the user gives (`--limit`), never market. | The example's calls; flatten without `--limit` refuses for an option; paper cash includes option charges. |
| 8 | `bharat-alerts/alerts.py` | `add --from-plan` for an opt plan watches the INDEX levels (`index_stop`, `index_target`, since free option quotes do not exist) and says so in every message; an expiry-day 15:00 alert for any open option ("an ITM option held to expiry pays STT on its intrinsic value: close it"). | Messages name the option and say the levels are index levels from the model; the 15:00 expiry alert rings only on that contract's expiry day. |

### Task 9: Docs and the worked example

**Files:**
- Modify: every SKILL.md touched above, `README.md`, `tests/example_values.py` (`OPT_*`), `tests/test_repo.py`

- [ ] **Step 1:** README test covers every `OPT_*` value and the strings "buying only", "implied volatility", "held constant", "STT on its intrinsic value".
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** README "Index options" section: the example (index signal, ATM call, IV from the premium, premium stop and target, lots, costs, the Time Machine on the repriced option, expiry-day rules) and fine print (a bought option can lose 100 % of its premium in hours; the model's limits: constant IV, no skew, no jumps; SEBI's F&O loss studies; tax as non-speculative business income).
- [ ] **Step 4:** Full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `docs: index options`.

## Self-review notes

- Spec P3 coverage: buying only (Task 6 blocks opening sells), sizing by premium x lot (Task 6), expiry-day rules (Tasks 6, 8), Time Machine repricing with constant IV from the latest premium (Task 5), strike picker ATM +- N (Tasks 2, 3).
- Not in the spec but needed: puts (an option buyer's short-side view) need the ORB's mirror rule at the range low (Task 3); the index-level alerts (Task 8) exist because there are no free intraday option quotes.
- Depends on P2's `parse_bhavcopy`, `front_future`-style expiry selection and the NFO broker path; do P2 first.
