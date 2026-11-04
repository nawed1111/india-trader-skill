# India Trader skill, P2 (index futures) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the pack plan, size, check and send intraday trades in NIFTY and BANKNIFTY index futures, in whole lots, with futures costs, margin, and expiry/rollover rules.

**Architecture:** Futures have no free intraday bars (Yahoo has none for NSE F&O). The signal is read on the index itself (`^NSEI`, `^NSEBANK`, which the P1 tools already read). The futures price is the index price times the basis ratio (futures close / index close) from the latest NSE F&O bhavcopy, or a price the user gives (Kite quote). Every skill gains an `instrument` field (`"eq"` default, `"fut"`). Contract data (lot sizes, expiries, symbols) comes from NSE's bhavcopy and lot-size files through new `india.py` functions.

**Tech Stack:** Python 3.8+, standard library only, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-04-india-trader-skill-design.md` (P2 section). P1 is on `main`; read `docs/p0-findings.md` for the data quirks.

## Global Constraints

- Everything in the P1 plan's Global Constraints still holds (stdlib, 3.8+, each folder self-contained, `india.py` copies identical, IST, paper default, three gates).
- F&O stays off by default: every futures path requires `"allow_fno": true` in the config, and bharat-risk blocks otherwise.
- P2 is NIFTY and BANKNIFTY futures only. Stock futures and anything on BSE are out.
- Index futures trade on a Rs 0.05 tick (checked in the 3 Nov 2026 bhavcopy: every IDF/IDO price ends in 0 or 5).
- Quantities sent to the broker are in units (lots x lot size); lots are whole.
- Expiries come from the bhavcopy (`XpryDt`), never computed from weekday rules alone. 3 Nov 2026 data: NIFTY monthly 2026-11-23 (Tue 24 Nov is a holiday), 2026-12-29; BANKNIFTY monthly only, 2026-11-23, 2026-12-29, 2027-01-25.
- Lot sizes come from `fo_mktlots.csv` (NIFTY 65, BANKNIFTY 30 on 4 Nov 2026), never hard-coded in skill scripts.
- Margin is never guessed: `margin_per_lot_inr` (`{"NIFTY": ..., "BANKNIFTY": ...}`) in the config, entered by the user from Zerodha's margin calculator. No figure means no futures order.
- Futures costs: `india.round_trip("fut", ...)`, checked against Zerodha's calculator in Task 1.

## Review Focus

1. **The contract expires today, or the trade is the day before a holiday expiry:** entry warns on the day before expiry and risk BLOCKs a new entry in a contract that expires today (rollover message names the next contract). (Tests in Tasks 2 and 7.)
2. **A stale basis:** the bhavcopy is from an earlier day than the last session, or missing; the futures price is then marked "estimated from DATE" and risk BLOCKs a market entry without a user-given futures price or a basis from the last session. (Tests in Tasks 3 and 7.)
3. **A lot size change between months** (NSE revises lot sizes; `fo_mktlots.csv` has one column per month): sizing uses the lot size of the contract's own expiry month. (Test in Task 2.)
4. **No margin figure, or margin larger than the cash:** budget refuses with the reason; never sizes from a guess. (Test in Task 6.)
5. **SL-M on NFO:** if Task 1 finds NSE/Zerodha refuse SL-M for F&O, the stop goes as SL (stop-limit) with a limit a few ticks through the trigger, and the ticket says a limit stop may not fill in a fast move. (Test in Task 8.)

---

### Task 1: Data check (stop for review)

**Files:**
- Modify: `tools/probe.py` (add sources), `docs/p0-findings.md` (new section "P2 findings")
- Create: `tests/fixtures/p2/` (`fo-bhavcopy-20261016.csv.zip`, `fo-bhavcopy-20261019.csv.zip`, `fo_mktlots.csv`, `yahoo-NSEBANK-5m.json`, `zerodha-calc-fut.json`)

- [ ] **Step 1:** Add to `probe.py`: F&O bhavcopy for 2026-10-16 and 2026-10-19 (the example's previous session and day), `^NSEBANK` 60d 5m. Run it; expect `OK` per source.
- [ ] **Step 2:** With the built-in browser on zerodha.com/brokerage-calculator (F&O, futures tab), run three cases and save `zerodha-calc-fut.json` in the `zerodha-calc.json` shape with `"segment": "fut"`: 1 lot NIFTY (65) 23,500 to 23,600; 2 lots BANKNIFTY (60) 55,000 to 54,800; 1 lot NIFTY 23,500 to 23,505. Read the calculator's `cal_futures` source to confirm the rounding (as P0 did for `cal_intra`).
- [ ] **Step 3:** Confirm and write down in "P2 findings": whether Zerodha accepts SL-M for NFO (Kite docs / support pages); MIS margin for NIFTY and BANKNIFTY futures that day (for the README example only, never as a default); the exact Kite `place_order` fields for NFO (`exchange: NFO`, `tradingsymbol`, `quantity` in units).
- [ ] **Step 4:** Pick the worked example: an ORB on `^NSEI` on a session in the 60-day fixture where the index broke its 9:15 to 9:30 range, with that day's and the previous day's bhavcopy saved. Record symbol, date, range, trigger bar, the futures contract and the basis ratio.
- [ ] **Step 5:** Commit: `docs: P2 data findings and fixtures`.
- [ ] **Step 6: STOP.** Show the user "P2 findings". Revise this plan if SL-M, margin or data findings break it.

### Task 2: `india.py` contracts

**Files:**
- Modify: `india/india.py` (then `tools/sync_india.py`)
- Test: `tests/test_india.py`

**Interfaces:**
- Produces:
  - `parse_lot_sizes(text: str) -> dict`: `{SYMBOL: {"2026-11": 65, "2026-12": 65, ...}}` from `fo_mktlots.csv` (strip the padded cells; month columns like `NOV-26`)
  - `parse_bhavcopy(data: bytes) -> list[dict]`: the zip or the CSV inside it, rows with `kind` (`fut` for IDF, `opt` for IDO), `symbol`, `contract` (FinInstrmNm), `expiry` (date), `strike` (float or None), `right` (`CE`/`PE`/None), `close`, `settle`, `underlying`, `oi`, `lot`, `date`
  - `futures(rows, symbol) -> list[dict]`: that symbol's futures, nearest expiry first
  - `front_future(rows, symbol, today: date, roll_days: int = 0) -> dict | None`: the nearest future that does not expire today (or within `roll_days` trading days)
  - `basis_ratio(fut_row) -> float`: `close / underlying`
  - `lot_size(lots: dict, symbol: str, expiry: date) -> int`: the lot for the contract's own month; raise `ValueError` when the month is missing
  - `is_expiry_day(rows, symbol, d: date) -> bool`
  - RATES `fut` confirmed (or corrected) against `zerodha-calc-fut.json`

- [ ] **Step 1: Write the failing tests:** on `fo-bhavcopy-20261103.csv.zip` (P0 fixture): `futures(rows, "NIFTY")[0]["contract"] == "NIFTY26NOVFUT"` with expiry `2026-11-23`, lot 65, close 23780.50, underlying 23810.85; `front_future(rows, "NIFTY", date(2026, 11, 23))` is the December contract; `is_expiry_day(rows, "NIFTY", date(2026, 11, 23))` is True and `date(2026, 11, 24)` is False (holiday); `lot_size(parse_lot_sizes(...), "BANKNIFTY", date(2026, 12, 29)) == 30`; `lot_size(..., "NIFTY", date(2031, 6, 30))` raises; every row of `zerodha-calc-fut.json` matches `round_trip("fut", ...)` within Rs 0.01; `basis_ratio` of the NIFTY Nov future is `23780.50 / 23810.85`.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_india -v`. Expected: FAIL (names missing).
- [ ] **Step 3:** Implement. `parse_bhavcopy` accepts zip bytes (`zipfile.ZipFile(io.BytesIO(data))`) or plain CSV bytes.
- [ ] **Step 4:** Run the tests, then `tools/sync_india.py` and the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(india): F&O contracts, lots, expiries, basis`.

### Tasks 3 to 9: each skill learns `instrument: fut`

Same five-step pattern as P1's port tasks (failing test with the row's assertions, run it red, implement, full suite green, commit `feat(bharat-<skill>): index futures`). New fixtures come from `tests/fixtures/p2/`. The `"eq"` paths and every P1 test stay unchanged.

| Task | Skill / files | Changes | Tests must assert |
| --- | --- | --- | --- |
| 3 | `bharat-entry/entry.py` | `--instrument fut` (symbol NIFTY or BANKNIFTY): the signal on the index bars as now; the result adds `future` = `{contract, expiry, lot, basis_ratio, basis_date, price}` from `--bhavcopy FILE` (default: download the last session's), price = trigger close x ratio, tick-rounded; `--fut-price P` overrides; a basis older than the last session sets `future.estimated` with a warning; a contract expiring tomorrow warns "rolls over". | The example's trigger and its futures price from the saved bhavcopy; `--fut-price` wins; a bhavcopy two sessions old gives `estimated` and the warning; on 2026-11-23 the contract is December's. |
| 4 | `bharat-exit/exit.py` | Plans `instrument: fut` in futures points: entry = `future.price`, stop and target shifted by the same ratio as the index levels and tick-rounded; `risk_per_unit`, `lot`, `contract` carried into `trader/plan.json`. | Example: or-mid stop and 1R target in futures points; `risk_per_unit` x `lot` = risk per lot; a level plan still needs a named stop. |
| 5 | `bharat-timemachine/timemachine.py` | For `instrument: fut` it replays the index bars (the pool is the index's own) with the plan's stop and target divided by `basis_ratio`, and reports odds unchanged plus R and price at `--until` in futures points. | The odds of the example fut plan equal the odds of the same plan on the index (constant ratio); the report says "futures price = index x RATIO from DATE". |
| 6 | `bharat-budget/size.py` + `config.example.json` | `instrument: fut`: lots, not shares. Limits: max loss (lots x lot x risk + `round_trip("fut", ...)` at the stop), margin (`(cash - buffer) / margin_per_lot_inr[symbol]`; no figure = refusal naming the key), max order (notional), `max_lots` (config, default 1). Order: `exchange: NFO`, `product: MIS`, `symbol` = the contract, `qty` = lots x lot, `instrument: fut`. New config keys with no default margin. | Example sizing to the lot; missing margin refuses with "margin_per_lot_inr"; a margin above the cash gives 0 lots; costs match `zerodha-calc-fut.json`'s rounding. |
| 7 | `bharat-risk/check.py` | For an F&O symbol: BLOCK unless `allow_fno`; qty a multiple of the contract's lot; BLOCK a new entry in a contract expiring today (name the next one); BLOCK a market entry whose basis is estimated and has no user futures price (`plan.basis_estimated`); costs with segment `fut`; margin check against `margin_per_lot_inr`; `max_lots`. The F&O ban list stays irrelevant for index futures (say so in the SKILL.md). | `allow_fno` false blocks; 64 units of NIFTY blocks (lot 65); an entry on its expiry day blocks with "trade NIFTY26DECFUT"; an estimated-basis market entry blocks; the example passes with costs and margin in the info lines. |
| 8 | `bharat-broker/ticket.py` | Kite calls for NFO: `exchange: NFO`, `tradingsymbol` = contract, `quantity` units; the stop is SL-M, or SL with `price` = trigger minus N ticks (config `stop_limit_ticks`, default 10) when Task 1 found SL-M refused for F&O; paper fills use `leg_costs("fut", ...)`; flatten works on a futures position. | The example's two calls; the SL variant when the finding says so, with the "may not fill in a fast move" line; paper cash after a round trip includes futures charges. |
| 9 | `bharat-alerts/alerts.py` | New rule type `expiry` (`symbol`, rings at `at`, default 09:15, on the contract's expiry day and the trading day before, from the bhavcopy); `add --from-plan` adds it for a fut plan. | Rings on 2026-11-20 and 2026-11-23 for NIFTY26NOVFUT (Nov 24 holiday), not on Nov 24. |

### Task 10: Scanner, docs and the worked example

**Files:**
- Modify: `bharat-scanner/SKILL.md`, all SKILL.md files touched above, `README.md`, `tests/example_values.py` (add `FUT_*` values), `tests/test_repo.py`

- [ ] **Step 1:** Test first: `scan.py orb --symbols NIFTY,BANKNIFTY --offline <p2 fixtures>` lists the example's index breakout (the scanner already maps `NIFTY` to `^NSEI`; this pins it). README test covers every `FUT_*` value.
- [ ] **Step 2:** Run. Expected: FAIL on the README values.
- [ ] **Step 3:** Write the README "Index futures" section: the chain for the example (signal on the index, futures price from the basis, lots, margin, costs, the expiry rules) and the F&O fine print (leverage; SEBI's finding that about 9 in 10 F&O traders lost money; futures losses can exceed the margin; F&O is non-speculative business income for tax).
- [ ] **Step 4:** Full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `docs: index futures`.

## Self-review notes

- Spec P2 coverage: lot sizing (Task 6), margin (Task 6, 7), rollover and expiry warnings (Tasks 3, 7, 9), futures prices in the Time Machine (Task 5).
- Decision carried from the data: intraday futures bars are not free, so the index is the signal and the bhavcopy basis prices the future. Kite's quote (paid "Connect" plan) is the user-given price path, not a dependency.
- Task 1 can change Task 8 (SL-M) and the example; it stops for review.
