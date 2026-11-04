# India Trader skill, P3 follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the eight findings left after the P3 index-options merge (PR #2): two holes in risk's option format checks, an expiry date risk takes on trust, a cost check a high target can talk past, NSE's freeze limit, an unrounded flatten limit, a wrong word in the expiry alert, and dead helpers in `india.py`.

**Architecture:** Almost all of it lands in `bharat-risk/check.py`, the one gate every order goes through, so a fix there covers every skill that writes orders. `india.py` loses two test-only helpers and gains one table (`FREEZE_QTY`). Broker and alerts get one-line fixes each. No new files.

**Tech Stack:** Python 3.8+, standard library only, `unittest` (`python3 -m unittest discover -s tests -v`).

**Spec:** the findings list in the request (quoted per task below); P3 plan `docs/superpowers/plans/2026-11-04-india-trader-p3-options.md`; data in `docs/p0-findings.md` ("P3 findings").

## Global Constraints

- Everything in the P1–P3 Global Constraints still holds: stdlib only, 3.8+, each skill folder self-contained, `india.py` identical in every folder (edit `india/india.py`, run `python3 tools/sync_india.py`; `tests/test_repo.py` fails on a drifted copy).
- Exits stay possible. The one new rule that touches exits (Task 2) refuses an order **type**, never the exit itself: a limit sell still closes the position.
- Freeze limits, from `docs/p0-findings.md` (NSE/FAOP/77189, from 2 Nov 2026): NIFTY 1,800 units (27 lots of 65), BANKNIFTY 900 units (30 lots of 30).
- Option prices are on the Rs 0.05 tick.
- `"eq"` and `"fut"` paths and their tests stay as they are, except where a task says so.

## Review Focus

1. **A futures order without `exchange`:** Task 2's NFO rule applies to futures too. Budget writes `exchange: NFO` for both; any test or fixture order without it must be fixed to carry it, not the rule loosened. (Test in Task 2.)
2. **A monthly option name carries no day:** `NIFTY26OCT23100CE` says only October. Risk can check the order's expiry is in that month, not that it is the month's last expiry (that needs the bhavcopy). (Test in Task 3.)
3. **A position held above the freeze limit:** an exit over the limit is refused by the exchange anyway; risk BLOCKs it with "flatten in two tickets" rather than letting Kite reject it live. (Test in Task 3.)
4. **Many cheap lots:** the premium-paid cost check must pass a Rs 3 option bought in enough lots that the flat Rs 20 an order stops mattering (5 lots: Rs 975 paid, Rs 49.01 costs, 5 %). (Test in Task 4.)
5. **Flatten limit already on the tick:** `--limit 150.00` must stay 150.00 and print no rounding note. (Test in Task 5.)

---

### Task 1: `india.py`: drop test-only helpers, add the freeze table

Finding: "Four option-symbol helpers in india.py are used only by tests."

Callers today (`grep "india\.NAME("` over `bharat-*/` minus `india.py`): `option_symbol`, `parse_option_symbol`, `is_monthly` have none; `atm_strike` is used inside `pick_strike`. After Task 3, `parse_option_symbol` has a real caller (risk). So: delete `option_symbol` and `is_monthly`; keep `parse_option_symbol` (and `WEEK_CODE`, `OPT_NAME`, which it uses) and `atm_strike`.

**Files:**
- Modify: `india/india.py` (then `python3 tools/sync_india.py`)
- Test: `tests/test_india.py` (`test_option_symbols`, around line 252)

**Interfaces:**
- Produces: `FREEZE_QTY = {"NIFTY": 1800, "BANKNIFTY": 900}` with a comment naming NSE/FAOP/77189 and "from 2 Nov 2026; NSE revises it each quarter"; `parse_option_symbol(text) -> dict | None` unchanged.
- Removes: `option_symbol`, `is_monthly`.

- [ ] **Step 1: Rewrite `test_option_symbols`** to stop calling the two deleted helpers. Keep the `parse_option_symbol` asserts on `"NIFTY26O1923100CE"`, `"BANKNIFTY26OCT55000PE"` (expiry None) and `"NIFTY26OCTFUT"` (None). Replace the bhavcopy round-trip loop with: for every option row `r` in `self.r19`, `p = india.parse_option_symbol(r["contract"])` is not None, `p["strike"] == r["strike"]`, `p["right"] == r["right"]`, `p["month"] == r["expiry"].strftime("%Y-%m")`, and `p["expiry"] in (None, r["expiry"])` (a weekly name's date is the row's expiry). Add `self.assertEqual(india.FREEZE_QTY["NIFTY"] // 65, 27)`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_india -v`. Expected: FAIL on `FREEZE_QTY`.
- [ ] **Step 3: Implement:** delete `option_symbol` and `is_monthly`, add `FREEZE_QTY` in the "F&O contracts" section. Run `python3 tools/sync_india.py`.
- [ ] **Step 4: Full suite.** Expected: PASS (nothing outside tests used the deleted two; if something does, keep it and say so).
- [ ] **Step 5: Commit:** `refactor(india): drop test-only option helpers; freeze quantities`

### Task 2: Risk: options go on NFO, and close at a limit

Findings: "A market sell that closes an option you hold passes risk with a warning, because exits are never blocked." "Risk doesn't check that an option order is on NFO."

Why both block: `kite_calls` in `bharat-broker/ticket.py` sends `exchange: order.get("exchange") or "NSE"`, so an option order with no exchange goes to NSE live. And `ticket.py flatten` already refuses a market close for an option; risk must agree, since a hand-written orders file skips flatten.

**Files:**
- Modify: `bharat-risk/check.py` (the per-order loop, `check()`, around lines 350–500), its module docstring (lines 16–19), `bharat-risk/SKILL.md` (lines 15 and 181)
- Test: `tests/test_risk.py` (class `Options`, helpers `opt_order`, `fut_order`, `fut_cfg`)

**Interfaces:**
- Consumes: the loop's existing `fno`, `opt`, `fut`, `typ`, `reasons` (blocks any kind), `later` (entry-only).

- [ ] **Step 1: Write the failing tests** in `Options`:
  - `test_closing_an_option_at_market_blocks`: the `test_selling_a_bought_option_is_an_exit` sell with `type="market"` and no `limit_price` → `("exit", "BLOCK")`, reasons contain `"flatten --symbol"` and `"--limit"`.
  - `test_an_option_off_nfo_blocks`: `opt_order(exchange="NSE")` → BLOCK, reasons contain `"NFO"`; `opt_order()` with `exchange` deleted → BLOCK; the same for the exit sell with `exchange="NSE"` → BLOCK.
  - In `Futures`: `fut_order(exchange="NSE")` → BLOCK with `"NFO"`.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_risk -v`. Expected: the four new tests FAIL.
- [ ] **Step 3: Implement** in the format section, appended to `reasons` (so exits block too):
  - `if (fut or opt) and str(o.get("exchange") or "").upper() != "NFO"`: `"format: %s is an F&O contract and goes on NFO, not %s" % (sym, exchange or "no exchange")`.
  - `if opt and typ == "market"`: `"format: an option is bought and sold at a limit, never market (a market order can fill far from its value); to close it: ticket.py flatten --symbol %s --limit PRICE"`. Drop the now-duplicate entry-only `typ != "limit"` line in the `opt and kind == "entry"` block only if it says the same thing for the same types (a `stop_limit` entry still goes through the old line; keep that).
  - Docstring and SKILL.md: "an exit is checked for format, asset and short sales only" stays true (both rules are format); add one sentence: "An option exit must be a limit order: that is a format rule, and a limit sell still gets you out."
- [ ] **Step 4: Full suite.** Expected: PASS. If an existing futures test or fixture order lacks `exchange: NFO`, add it there (Review Focus 1).
- [ ] **Step 5: Commit:** `fix(bharat-risk): F&O orders must be on NFO; options close at a limit`

### Task 3: Risk: expiry from the contract name, and the freeze limit

Findings: "Risk trusts the order's expiry date rather than reading it from a weekly contract's name." "Orders above NSE's per-order limit (27 NIFTY lots) aren't split."

Not split: refused, with the count of tickets to send instead. Kite's `autoslice` would split it, but each slice is its own order and its own stop, which breaks the one-ticket-one-yes flow and the "cancel the stop first" flatten step. `max_lots` defaults to 1, so this only bites someone who raised it past 27.

**Files:**
- Modify: `bharat-risk/check.py` (replace `OPT_SYM` with `india.parse_option_symbol`; the `opt and kind == "entry"` expiry block, around line 516; one freeze check for `fno` orders)
- Test: `tests/test_risk.py` (`Options`, `Futures`)

**Interfaces:**
- Consumes: `india.parse_option_symbol(sym) -> {symbol, expiry (date | None), month "YYYY-MM", strike, right, weekly} | None`, `india.FREEZE_QTY` (Task 1).

- [ ] **Step 1: Write the failing tests:**
  - `test_a_weekly_name_sets_the_expiry`: `opt_order(symbol="NIFTY26O2023100CE", expiry="2026-10-27")` → BLOCK, reasons contain `"2026-10-20"` and `"2026-10-27"` (the name says 20 Oct, the order says 27 Oct). With `expiry="2026-10-20"` the expiry reasons are gone.
  - `test_a_weekly_expiring_today_from_its_name`: `opt_order(symbol="NIFTY26O2123100CE", expiry=None)` at `now="2026-10-21 13:05"` → BLOCK with `"expiry_day_cutoff"` (the name alone sets today as expiry; no "no expiry date" reason).
  - `test_a_monthly_name_checks_the_month`: `opt_order(expiry="2026-11-24")` on `NIFTY26OCT23100CE` → BLOCK, reasons contain `"2026-10"`.
  - `test_over_the_freeze_limit_blocks`: an `opt_order` with `qty="1820"` (28 lots of 65) under `fut_cfg(max_lots=30)` → BLOCK, reasons contain `"1,800"` and `"2 tickets"`; `qty="1755"` (27 lots) has no freeze reason. A `fut_order` on a BANKNIFTY future over 900 units → BLOCK the same way.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_risk -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement:**
  - `name = india.parse_option_symbol(sym)`; `opt = o.get("instrument") == "opt" or name is not None`; `unknown_nfo` uses `name` in place of `OPT_SYM.match(sym)`. Delete `OPT_SYM`.
  - In the option entry expiry block, before reading `exp`: if `name` and `name["expiry"]` (weekly): when the order's expiry is set and differs, `later.append("expiry: the order says %s but %s expires on %s (the date is in its name)")`; then use the name's date as `exp`. If `name` and no `name["expiry"]` (monthly) and `exp[:7] != name["month"]`: `later.append("expiry: the order says %s but %s is a %s contract")`. `# ponytail: a monthly name gives the month only; checking it is that month's last expiry needs the bhavcopy`.
  - Freeze, for every `fno` order with `q` (in `reasons`, so exits block too): `und = name["symbol"] if name else FUT_NAME.match(sym).group(1) if FUT_NAME.match(sym) else o.get("underlying")`; `cap = india.FREEZE_QTY.get(und)`; when `q > cap`: `"freeze: %s units is over NSE's %s-unit limit for one %s order; send it as %d tickets of at most %s" % (q, "{:,}".format(cap), und, ceil(q / cap), cap)`.
- [ ] **Step 4: Full suite.** Expected: PASS.
- [ ] **Step 5: Commit:** `fix(bharat-risk): read a weekly option's expiry from its name; NSE freeze limit`

### Task 4: Risk: the cheap-option cost check stops depending on the target

Finding: "The cheap-option block depends on the target: a Rs 3 option with a Rs 6 target passes."

Measured: 1 lot of 65 at Rs 3 costs Rs 47.37 round trip on Rs 195 paid (24 %); with a Rs 6 target the reward is Rs 195 and costs Rs 48.52 (24.9 %), just under `max_cost_share` 0.25. The fix measures costs against the premium paid, which no target can change: the flat Rs 20 an order is what makes a cheap option uneconomic.

**Files:**
- Modify: `bharat-risk/check.py` (`DEFAULTS` near line 84; the costs part of the day-trade checks, near line 645), `bharat-risk/SKILL.md` (the "What blocks" list), `bharat-budget/config.example.json` (add `"max_option_cost_share": 0.10` next to `max_cost_share`)
- Test: `tests/test_risk.py` (`Options`)

**Interfaces:**
- Produces: config key `max_option_cost_share`, default `0.10`: round-trip costs at the entry price (`costs(shares, ref, ref, "opt")`) over that share of the premium paid (`shares * ref`) BLOCKs an option entry.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_cheap_option_blocks_whatever_the_target`: the `test_costs_block_a_cheap_option` order with target `6.00` (`take_profit_limit_price="6.00"`, plan target 6.0) → BLOCK, reasons contain `"max_option_cost_share"` and `"Rs 195"`.
  - `test_enough_cheap_lots_pass_the_premium_cost_check`: the same at 5 lots (`qty="325"`, `fut_cfg(max_lots=5)`) → no `"max_option_cost_share"` reason.
  - `test_the_example_passes_with_option_costs` stays green (the example's costs are about 1 % of its premium).
- [ ] **Step 2: Run** `python3 -m unittest tests.test_risk -v`. Expected: the first new test FAILS.
- [ ] **Step 3: Implement** inside the `elif ref:` stop branch, for `opt` only, after `max_loss`: `paid = shares * ref`; `cost_in = costs(shares, ref, ref, seg)`; when `cost_in > share * paid + CENT`: `later.append("costs: %s round-trip costs are %.0f%% of the %s premium paid, over your %.0f%% max_option_cost_share: the flat Rs 20 an order eats a cheap option; buy more lots or a dearer strike")`. Leave the target-based `max_cost_share` check as it is.
- [ ] **Step 4: Full suite.** Expected: PASS.
- [ ] **Step 5: Commit:** `fix(bharat-risk): cheap options block on costs against the premium paid`

### Task 5: Broker: the flatten limit goes on the tick

Finding: "The flatten --limit price isn't rounded to the 0.05 tick."

Rounded down for the sell: flatten exists to get out, and a limit 0.04 lower is the one that fills. NSE rejects an off-tick price, so leaving it is not an option.

**Files:**
- Modify: `bharat-broker/ticket.py` (`cmd_flatten`, around line 740)
- Test: `tests/test_broker.py` (class `Options`, next to `test_flatten_an_option_needs_a_limit`)

**Interfaces:**
- Consumes: `india.tick_round(price, tick=0.05, mode="down") -> float`.

- [ ] **Step 1: Write the failing test** `test_flatten_rounds_the_limit_down_to_the_tick`: flatten an option with `--limit 150.03` → the written order's `limit_price == "150.00"` and stdout contains `"150.03"` and `"150.00"`; with `--limit 150.00` → `"150.00"` and no rounding note (Review Focus 5).
- [ ] **Step 2: Run** `python3 -m unittest tests.test_broker -v`. Expected: FAIL.
- [ ] **Step 3: Implement:** `lim = india.tick_round(_f(a.limit), mode="down")`; `order["limit_price"] = _p(lim)`; when `abs(lim - _f(a.limit)) > 1e-9`, print `"--limit %s is off NSE's 0.05 tick: the sell goes at %s"`. Applies to every segment (cash stocks above Rs 0.05 tick use the same rule in this pack).
- [ ] **Step 4: Full suite.** Expected: PASS.
- [ ] **Step 5: Commit:** `fix(bharat-broker): round the flatten limit down to the 0.05 tick`

### Task 6: Alerts: the 9:15 expiry message names the next expiry, not the next month

Finding: "The 9:15 expiry alert says 'next month' even for a weekly option."

**Files:**
- Modify: `bharat-alerts/alerts.py` (the `typ == "expiry"` branch, lines 396–398)
- Test: `tests/test_alerts.py` (classes `Expiry`, `Options`)

- [ ] **Step 1: Write the failing test** in `Options`: a 09:15 expiry rule for `NIFTY26O2023100CE` with expiry `2026-10-20`, run on that day → the message does not contain `"month"` and contains `"next expiry"`. Update any `Expiry` test that pins the old "next month" text for a future to the new wording.
- [ ] **Step 2: Run** `python3 -m unittest tests.test_alerts -v`. Expected: FAIL.
- [ ] **Step 3: Implement:** the two sentences become `"No new entry in it today; an open position must be closed or rolled to the next expiry."` and `"Plan new entries in the next expiry's contract."`. One wording for futures and options; no weekly/monthly branch.
- [ ] **Step 4: Full suite.** Expected: PASS.
- [ ] **Step 5: Commit:** `fix(bharat-alerts): the expiry alert says next expiry, not next month`

### Task 7: Docs

**Files:**
- Modify: `README.md` (the index options section: limit-only closes, `max_option_cost_share`, the freeze limit), `bharat-risk/SKILL.md` (already touched in Tasks 2 and 4: check it reads as one list), `bharat-broker/SKILL.md` (flatten rounds `--limit` down to the tick), `tests/test_repo.py` if it pins README strings
- Test: `tests/test_repo.py`

- [ ] **Step 1:** Add README strings to `test_repo.py`'s checks: `"max_option_cost_share"`, `"1,800 units"`, `"at a limit"`.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_repo -v`. Expected: FAIL.
- [ ] **Step 3:** Write the README lines (one sentence each, in the options fine print).
- [ ] **Step 4:** Full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `docs: P3 follow-ups`

## Self-review notes

- Coverage: market close (Task 2), NFO (Task 2), flatten tick (Task 5), expiry from the name (Task 3), alert wording (Task 6), test-only helpers (Task 1; two deleted, `parse_option_symbol` gets its caller in Task 3, `atm_strike` was never test-only), freeze limit (Task 3, refused not split), cheap option (Task 4).
- Order: Task 1 before Task 3 (`FREEZE_QTY`, and the deleted helpers must not be what Task 3 uses). Tasks 2–4 all edit `check()`: run them in order, one at a time. Tasks 5 and 6 are independent of the rest.
