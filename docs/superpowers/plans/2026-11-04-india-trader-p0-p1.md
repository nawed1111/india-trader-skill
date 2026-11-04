# India Trader skill, P0 + P1 (cash stocks) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship 11 `bharat-*` skills for intraday NSE cash-stock trading, ported from the US day-trader pack, with offline tests that reproduce one worked example trade on real NSE data.

**Architecture:** Copy each US skill folder to a `bharat-*` folder. Remove each script's own New York clock, calendar and symbol helpers and replace them with imports from a shared-by-copy `india.py` that sits next to it. Data fetchers keep the US pack's `--offline <dir>` pattern, and the tests only run offline.

**Tech Stack:** Python 3.8+, standard library only, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-04-india-trader-skill-design.md`

**Source repo:** `/Volumes/SSD/dev/ai/day-trader-skill` (the US pack, MIT, by Jake Schincariol). Every task that ports a skill copies the US script and its tests from there first.

**Scope:** P0 and P1 only. P2 (futures) and P3 (options) get their own plans after the P0 findings, because P0 may change what data they can use.

## Global Constraints

- Standard-library Python only, 3.8+. No `zoneinfo`: IST is a fixed UTC+5:30 with no DST, so use `timezone(timedelta(hours=5, minutes=30))`.
- Each skill folder must work installed by itself: a script imports only the stdlib and the `india.py` in its own folder.
- Every `india.py` copy is byte-identical (enforced by `tests/test_repo.py`).
- Session 9:15–15:30 IST; MIS square-off 15:20; default `flat_by` 15:15.
- Money in ₹; prices rounded to the instrument's tick (₹0.05 default).
- `"paper": true` is the default; no order without the user's typed yes plus Claude's tool approval.
- Keys only from env vars `KITE_API_KEY`, `KITE_ACCESS_TOKEN`.
- Network fetchers: browser-like User-Agent, a cookie warm-up for NSE, backoff, caching. A fetch that fails is reported and the run continues with partial results. Never invent data.
- Tests: `python3 -m unittest discover -s tests -v`, fully offline.
- LICENSE keeps "Copyright (c) … Jake Schincariol" and adds a line for this repo.

## Review Focus

1. **A holiday, the Muhurat session, or a year not in the list (2028):** the skills must not treat a closed day as open. A year that isn't listed says "holiday list unknown". (Test in Task 3.)
2. **NSE returns HTML or a 403 instead of JSON:** the fetcher raises a clear error naming the URL; batch commands keep going and list what failed. (Tests in Tasks 5 and 14.)
3. **Symbols with `&` or `-` (`M&M`, `BAJAJ-AUTO`):** they map to `M&M.NS` / `BAJAJ-AUTO.NS` and are URL-encoded in requests. (Test in Task 3.)
4. **Costs larger than the expected reward on a small position:** risk BLOCKs with the reason. (Test in Task 10.)
5. **A stock frozen at its price band, or on the F&O ban list:** entry warns and risk BLOCKs. (Tests in Tasks 6 and 10.)

---

## P0: check that the data works

### Task 1: Repo scaffold from the US pack

**Files:**
- Create: `bharat-{scanner,news,entry,exit,timemachine,budget,risk,broker,alerts,analyst,insider}/` (copies of `trader-{scanner,news,entry,exit,timemachine,budget,risk,broker,alerts,analyst,pelosi}/`)
- Create: `tests/` (copy of the US `tests/`, with fixture folders renamed the same way), `LICENSE`, `.claude-plugin/{marketplace.json,plugin.json}`, `README.md` (a stub: title, the line crediting the US pack, "work in progress")
- Modify: `tests/_load.py`, `tests/test_repo.py`, and every `tests/test_*.py` folder name

**Interfaces:**
- Produces: `load(folder, name)` in `tests/_load.py`, which now also puts `ROOT/folder` at the front of `sys.path` and drops any cached `india` module before loading, so each script's `import india` resolves to its own folder.

- [ ] **Step 1:** Copy the folders and tests, renaming `trader-X` to `bharat-X` (`pelosi` becomes `insider`) in folder names, test files, SKILL.md `name:` front matter and the manifests. Plugin name `india-trader-skill`, version `0.1.0`.
- [ ] **Step 2:** Update `test_repo.py`: `SKILLS` holds the 11 `bharat-*` names; `ABOUT` = "11 Claude skills for intraday trading on NSE: scan the market, track announcements, time every entry and exit, and replay every outcome before you risk a rupee."; drop `V1_ONLY`.
- [ ] **Step 3:** Run `python3 -m unittest discover -s tests -v`. Expected: the US-data tests still pass under the new names. This is the green baseline. Fix only renaming slips. Tests of README content may be skipped with `@unittest.skip("README rewritten in Task 16")`.
- [ ] **Step 4:** Commit: `chore: scaffold india-trader-skill from the US pack`.

### Task 2: Data probe and findings (stop for review)

**Files:**
- Create: `tools/probe.py` (dev only, not in any skill), `docs/p0-findings.md`, `tests/fixtures/p0/` (raw saved responses)

**Interfaces:**
- Produces: fixture files that later tasks cut from, and `docs/p0-findings.md` with: (a) each source's URL, status and quirks, (b) confirmed cost rates plus three Zerodha brokerage-calculator results saved as `tests/fixtures/p0/zerodha-calc.json` (`[{"segment","qty","buy","sell","brokerage","stt","exchange","sebi","stamp","gst","total"}]`), (c) the 2026 and 2027 NSE holiday list and the Muhurat date and time, (d) the current SEBI retail-API rules, NIFTY/BANKNIFTY expiry days and lot sizes, Kite Connect pricing, Kite MCP order capabilities, (e) **the worked example**: one NIFTY 50 stock and one 2026 session with a 15-minute opening-range breakout, plus the symbol, date, range high/low, trigger bar and time. Tasks 5–16 assert against this.

- [ ] **Step 1:** Write `probe.py`, with one function per source in the spec's Data sources table, each saving the raw response to `tests/fixtures/p0/<name>`: Yahoo 5m chart for `RELIANCE.NS` (`range=60d`) and `^NSEI`; `EQUITY_L.csv`; NSE price-band file; F&O ban list; NSE corporate announcements for one symbol; BSE announcements for the same one; NSE PIT insider disclosures; bulk and block deals; FII/DII; one company's XBRL results file; the NSE holiday-list endpoint.
- [ ] **Step 2:** Run `python3 tools/probe.py`. Expected: one line per source, `OK <bytes>` or `FAIL <reason>`.
- [ ] **Step 3:** Fill in `docs/p0-findings.md` sections (a)–(e). Enter the three calculator cases by hand from zerodha.com/brokerage-calculator: intraday 100 shares at ₹1,400 to ₹1,410; 1 share at ₹50 to ₹50.50; 500 at ₹2,000 to ₹1,990.
- [ ] **Step 4:** Pick the worked example from the saved 5m bars: scan the 60 days of `RELIANCE.NS` (or another NIFTY 50 stock if RELIANCE gives none) for a session whose 9:30 or later bar closes above the 9:15–9:30 range high, and save that stock's 60-day 5m chart as `tests/fixtures/example/<SYM>-5m.json`.
- [ ] **Step 5:** Commit: `docs: P0 data findings and fixtures`.
- [ ] **Step 6: STOP.** Show the user `docs/p0-findings.md`. If any source failed with no workaround, or a rule breaks the spec, revise the spec with the user before Task 3.

---

## P1: cash stocks

### Task 3: `india.py`

**Files:**
- Create: `india/india.py` (the master copy) and `tools/sync_india.py` (copies the master into every `bharat-*/` folder)
- Test: `tests/test_india.py`

**Interfaces:**
- Produces (used by every later task):
  - `IST: datetime.tzinfo`; `OPEN = time(9,15)`, `CLOSE = time(15,30)`, `SQUARE_OFF = time(15,20)`, `FLAT_BY = time(15,15)`
  - `to_ist(utc: datetime) -> datetime`, `ist_to_utc(local: datetime) -> datetime` (a naive input is treated as IST)
  - `trading_day(d: date) -> tuple[bool, str]`. The reason is `"weekend"`, `"NSE holiday: <name>"`, `"holiday list unknown for <year>"` or `""`
  - `session(d: date) -> tuple[datetime, datetime] | None`: IST open and close. On the Muhurat date it returns the Muhurat window from `MUHURAT`
  - `next_open(d: date) -> datetime`
  - `HOLIDAYS: dict[date, str]`, `MUHURAT: dict[date, tuple[time, time]]`, both filled from the P0 findings
  - `yahoo_symbol(sym: str) -> str`: `"RELIANCE"` → `"RELIANCE.NS"`, `"NIFTY"` → `"^NSEI"`, `"BANKNIFTY"` → `"^NSEBANK"`, and anything already ending in `.NS`, `.BO` or starting with `^` passes through. Callers URL-encode it with `urllib.parse.quote`
  - `RATES: dict` = `{"checked": "<P0 date>", "eq_intraday": {...}, "fut": {...}, "opt": {...}}`, with keys `brokerage_pct`, `brokerage_cap`, `stt_sell_pct`, `exchange_pct`, `sebi_per_crore`, `stamp_buy_pct`, `gst_pct`
  - `leg_costs(segment: str, side: str, qty: int, price: float, rates: dict | None = None) -> dict` with keys `brokerage, stt, exchange, sebi, stamp, gst, total` (₹, 2 dp)
  - `round_trip(segment: str, qty: int, buy: float, sell: float, rates=None) -> dict`, the same keys summed over both legs
  - `tick_round(price: float, tick: float = 0.05, mode: str = "nearest") -> float`, where mode is `nearest`, `down` or `up`
  - `band_ok(price: float, prev_close: float, band_pct: float) -> bool`
  - `nse_get(url: str, timeout: int = 20) -> bytes`: warms up cookies on `https://www.nseindia.com/` once per process, sends a browser User-Agent and `Accept: application/json`, and retries 3 times with backoff on 401/403/429. Raises `NSEError(url, reason)` when it gives up, or when the response is HTML where JSON was expected

- [ ] **Step 1: Write the failing tests** in `tests/test_india.py`:
  - `trading_day(date(2026,1,26))[0] is False` and its reason starts with `"NSE holiday"`; `trading_day(date(2026,11,7)) == (False, "weekend")`; `trading_day(date(2028,3,1))[1] == "holiday list unknown for 2028"`; the Muhurat date from P0 has `session()` returning the Muhurat window
  - `to_ist(datetime(2026,11,4,3,45,tzinfo=timezone.utc)).time() == time(9,15)`
  - `yahoo_symbol("M&M") == "M&M.NS"`, `yahoo_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO.NS"`, `yahoo_symbol("NIFTY") == "^NSEI"`, `yahoo_symbol("TCS.BO") == "TCS.BO"`
  - for each row of `tests/fixtures/p0/zerodha-calc.json`: every key of `round_trip("eq_intraday", qty, buy, sell)` is within ₹0.01 of the calculator's figure
  - `tick_round(1402.33) == 1402.35`, `tick_round(1402.33, mode="down") == 1402.30`
  - `band_ok(110.0, 100.0, 10) is True`, `band_ok(110.05, 100.0, 10) is False`
  - `nse_get` given a stub opener that returns `<html>` raises `NSEError`
- [ ] **Step 2:** Run `python3 -m unittest tests.test_india -v`. Expected: FAIL, `india` not found.
- [ ] **Step 3:** Implement `india/india.py` with the interfaces above. If the calculator cases don't match within ₹0.01 by plain 2 dp rounding, write the rounding rule that does match into the code next to `RATES` and in `p0-findings.md`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Write `tools/sync_india.py` and run it. Add to `test_repo.py`: `test_india_copies_identical`, which checks every `bharat-*/india.py` has the same bytes as `india/india.py`. Run the full suite. Expected: PASS.
- [ ] **Step 6:** Commit: `feat: india.py clock, calendar, symbols, costs`.

### Tasks 4–14: port each skill

Every port task follows the same five steps. The table below says what each one changes. Common to all of them:

- Delete the script's `_nth_sunday`, `eastern_offset`, `to_eastern`, `eastern_to_utc`, `trading_day`, `session`, `next_open` and `to_yahoo`/`yahoo_symbol`, and call the `india.*` functions instead. Rename `*_eastern`/`ny_*` in output to IST. Change user-facing text from "New York"/"ET"/"$" to "IST"/"₹".
- In the SKILL.md: replace US examples with the worked example, replace NYSE/SEC/Alpaca references, and keep the safety block on skills that lead to an order.
- In the test file: replace the US fixtures with ones cut from `tests/fixtures/p0/` and `tests/fixtures/example/`, and replace the asserted numbers with the worked-example numbers computed in P0.

**Step pattern per port task:**
- [ ] **Step 1:** Rewrite `tests/test_<skill>.py` with the assertions listed in that task's row.
- [ ] **Step 2:** Run `python3 -m unittest tests.test_<skill> -v`. Expected: FAIL on the US values or symbols.
- [ ] **Step 3:** Port the script and SKILL.md as listed.
- [ ] **Step 4:** Run the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(bharat-<skill>): NSE cash port`.

| Task | Skill / files | Changes | Tests must assert |
| --- | --- | --- | --- |
| 4 | `bharat-scanner/scan.py` | `cmd_universe` reads `EQUITY_L.csv` (EQ series only) in place of the Nasdaq symdir, so `parse_symdir` and `build_universe` are replaced by `parse_equity_l(text) -> list[str]`. ORB from 9:15. New filters `--min-turnover` (₹, default 5 crore over 20 days), and the F&O ban list plus price-band status from P0 fixtures. | The universe count from the `EQUITY_L.csv` fixture; on the example date and time, `scan orb` lists the example symbol with its range high/low and trigger close; a banned symbol is excluded with its reason. |
| 5 | `bharat-news/news.py` | SEC 8-K feed replaced by `nse_announcements(sym)` and `bse_announcements(code)` (BSE as fallback); Yahoo RSS for `<sym>.NS`; times in IST; tags `results`, `board meeting`, `dividend/split`, `block deal`. | The example symbol's announcements from the fixture, in IST order with tags; an `NSEError` from the stub makes it fall back to BSE and the output says so (Review Focus 2). |
| 6 | `bharat-entry/entry.py` | `india.session`; `waiting`/`triggered`/`expired` unchanged; new `near_band` warning when price is within 1% of the band limit. | Example: `waiting` at the minute before the trigger bar closes, `triggered` at the trigger time with the trigger close; `pre-open` before 9:15 with "NSE opens at 9:15"; a band-limit fixture gives the `near_band` warning (Review Focus 5). |
| 7 | `bharat-exit/exit.py` | `flat_by` default 15:15; stop and target go through `india.tick_round` (stop `down` for a long position, target `up`). | Example plan: stop at the range midpoint rounded down to a tick, target at 1R rounded up, flat_by `15:15`. |
| 8 | `bharat-timemachine/timemachine.py` | IST bars and NSE days; the replay ends at 15:15, not 15:55. | Seed 19, 10,000 runs on the example fixture: target/stop/open-at-close percentages equal the P0-computed values; the history count over the 59 sessions. |
| 9 | `bharat-budget/size.py` + `config.example.json` | ₹ throughout; `size_trade` subtracts `india.round_trip` costs at the stop from `max_loss` before sizing; config keys `account_inr`, `max_loss_inr`, `mis_leverage` (default 1, capped at 5); `broker: "zerodha"`; `round_cent` becomes ₹0.05 ticks. | Example with ₹1,00,000 and ₹1,000 max loss: qty = floor((1000 − costs_at_stop) / risk_per_share), and loss at stop including costs ≤ ₹1,000; `mis_leverage: 9` gives a SizeError naming the cap. |
| 10 | `bharat-risk/check.py` | Remove `pdt_guard`/`business_days`; `window_check` uses 9:15 to `flat_by`; new checks `band` (BLOCK when the entry is outside the band or the stock is frozen), `fno_ban` (BLOCK), `cost_share` (BLOCK when round-trip costs exceed `max_cost_share` × expected reward, default 0.25). | The example order → PASS; 1 share at ₹50 with target ₹50.50 → BLOCK `cost_share` with the ₹ figures (Review Focus 4); a banned symbol → BLOCK `fno_ban`; an entry above the band → BLOCK `band` (Review Focus 5). |
| 11 | `bharat-broker/ticket.py` + `claude_desktop_config.example.json` | Paper mode: `apply_fill` subtracts `india.leg_costs` per fill and the ledger stays in `trader/portfolio.json`, so no separate `ledger.py` is needed (spec deviation, same behaviour). Live: `tool_input(order)` builds a Kite order (`exchange: NSE`, `product: MIS`, `order_type: LIMIT`) plus a stop as `SL-M`, for the Kite tool names found in P0 section (d). Missing `KITE_API_KEY` in live mode → TicketError "set KITE_API_KEY or stay on paper". | `show` renders the example ticket in ₹; `parse_yes` still needs the exact order; a paper fill reduces cash by price × qty + costs; live mode without the env var raises the error; `flatten` at 15:15 closes open MIS positions. |
| 12 | `bharat-alerts/alerts.py` | IST clock and the NSE calendar; `--before-close` defaults to 15:15; holiday and Muhurat days come from `india`. | The example plan's stop, target and 15:15 alerts each ring once; an `alerts check` on an NSE holiday reports the market as closed with the holiday name. |
| 13 | `bharat-analyst/results.py` (replaces `facts.py`) | Parse the NSE XBRL financial-results files: revenue, operating profit, PAT, EPS; QoQ and YoY %. Drop the SEC CIK lookup. | Figures for the fixture company match the values in the XBRL file; growth % to 1 dp; a missing tag shows as `n/a`, not 0. |
| 14 | `bharat-insider/insider.py` (replaces `ptr.py`) | Three subcommands: `insider --symbol S` (PIT disclosures: person, category, buy/sell, qty, value, date), `deals --date D` (bulk + block), `flows --days N` (FII/DII net ₹ cr). `index`/`new` keep the Pelosi skill's seen-since-last-run state in `trader/insider-seen.json`. | Rows from each fixture; a second `new` run returns 0 new rows; one feed failing with `NSEError` still prints the other two and lists the failure (Review Focus 2). |

### Task 15: README, worked example and fine print

**Files:**
- Modify: `README.md`, `tests/test_repo.py` (remove the skips from Task 1)

- [ ] **Step 1:** Remove the README skips in `test_repo.py` and add `test_readme_example_numbers`, which asserts that every number in the README's worked-example section appears in the outputs of the tests from Tasks 4–12. Do this by importing the expected-value constants those tests define in `tests/example_values.py` (create it in Task 4 and add to it in each port task).
- [ ] **Step 2:** Run it. Expected: FAIL (the README is still a stub).
- [ ] **Step 3:** Write the README in the US README's structure: install, the 11 skills, the worked example (scanner → news → entry → exit → timemachine → budget → risk → broker → alerts) with the numbers from `example_values.py`, the tools, and the spec's India fine print (not advice and not SEBI-registered; SEBI's loss studies; speculative business income; unofficial data; price-band freezes; Time Machine odds are not predictions; keys in env vars). Credit the US pack and its author.
- [ ] **Step 4:** Run the full suite. Expected: PASS.
- [ ] **Step 5:** Commit: `docs: README with the NSE worked example`.

---

## Self-review notes

- Spec coverage: layout (Task 1), `india.py` (Task 3), the 11 skills (Tasks 4–14), data sources and P0 (Task 2), safety and fine print (Tasks 11 and 15), testing (every task, plus `test_repo`). Futures and options are deferred to their own plans by design.
- Spec deviation: there is no `ledger.py`, because the US `ticket.py` already keeps a paper portfolio via `apply_fill`, so Task 11 adds costs to it. Update the spec's layout section in Task 11's commit.
- The numbers in Tasks 4–15 depend on the worked example chosen in Task 2. That is why Task 2 ends with a stop for review.
