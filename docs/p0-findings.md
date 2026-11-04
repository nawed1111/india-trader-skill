# P0 findings

Checked 2026-11-04. Raw responses are in `tests/fixtures/p0/`. Re-run with
`python3 -I tools/probe.py` (or `--only <name>`).

## (a) Data sources

| Source | Status | Notes |
| --- | --- | --- |
| Yahoo 5m chart, `RELIANCE.NS`, `^NSEI`, `M&M.NS` (60d) | OK | Needs a plain tool User-Agent: a browser-looking UA gets HTTP 429. `M&M` must be URL-encoded (`M%26M.NS`). 60 sessions, 75 bars each, 9:15 to 15:25 IST. **The 9:15 bar always has volume 0**, so any rule that uses opening-range volume must skip it or use the 9:20 and later bars. |
| `nsearchives.nseindia.com/content/equities/EQUITY_L.csv` | OK | Plain download, no cookies. |
| `.../equities/sec_list.csv` (price bands) | OK | Columns `Symbol,Series,Security Name,Band,Remarks`; band 2/5/10/20, or "No Band". |
| `.../fo/fo_secban.csv` | OK | Header line names the trade date, then `n,SYMBOL` rows (KAYNES, SAIL on 04-Nov-2026). |
| `.../fo/fo_mktlots.csv` | OK | Fixed-width padded CSV; one column per expiry month. NIFTY 65, BANKNIFTY 30. |
| F&O bhavcopy (UDiFF) `BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip` | OK | 1.1 MB per day. Used in P2/P3. |
| `www.nseindia.com/api/holiday-master?type=trading` | OK | Works **without** cookies. The home-page warm-up itself answers 403, so the warm-up must be best-effort. |
| `/api/corporate-announcements?index=equities&symbol=S` | OK | 2.9 MB for RELIANCE (full history). Trim to recent days in fixtures. |
| BSE `api.bseindia.com` announcements | **FAIL** | Akamai "Access Denied" (403) to scripts, even with Referer and Origin headers. |
| `/api/corporates-pit?index=equities&symbol=S` | OK | The `from_date`/`to_date` form answers an empty list; use the plain form (recent filings). |
| `/api/historical/bulk-deals`, `/block-deals` | **FAIL** | 503 to urllib, an HTML page to curl. |
| `/api/snapshot-capital-market-largedeal` | OK | One call gives `BULK_DEALS_DATA`, `BLOCK_DEALS_DATA`, `SHORT_DEALS_DATA` for the latest day. No history. |
| `/api/fiidiiTradeReact` | OK | Latest day only: FII/FPI and DII buy, sell, net in ₹ crore. |
| `/api/corporates-financial-results` | Stale | Its list stops at the Dec 2024 quarter. |
| `/api/integrated-filing-results?index=equities&symbol=S` | OK | Results since 2025 (SEBI integrated filing). Each row has an `xbrl` link. The XBRL uses the `in-capmkt:` namespace: `RevenueFromOperations`, `ProfitBeforeTax`, `ProfitLossForPeriod`, `BasicEarningsLossPerShareFromContinuingOperations`; context `OneD` is the quarter, `FourD` is year to date. Saved: Q1 and Q2 FY27 consolidated for RELIANCE. |

## (b) Costs (Zerodha, from zerodha.com/charges, 2026-11-04)

| | Intraday equity | Futures | Options |
| --- | --- | --- | --- |
| Brokerage | lower of ₹20 / 0.03% per order | lower of ₹20 / 0.03% | ₹20 flat |
| STT, sell side | 0.025% | **0.05%** | **0.15% of premium** (0.15% of intrinsic value if exercised) |
| NSE transaction charge | **0.00307%** | **0.00183%** | **0.03553% of premium** |
| SEBI fee | ₹10 / crore | ₹10 / crore | ₹10 / crore |
| Stamp duty, buy side | 0.003% | 0.002% | 0.003% |
| GST | 18% of (brokerage + exchange + SEBI) | same | same |

The figures in bold differ from the spec's starting values. The futures and options STT went up under Budget 2026. The spec's rate table must use these.

Zerodha calculator results are in `zerodha-calc.json` (3 intraday cases). How it rounds: **STT and stamp duty go to the whole rupee**, brokerage per order is rounded, and the exchange charge and SEBI fee are shown to 2 dp. The third case's exchange charge (₹61.24 against a raw ₹61.2465) and SEBI fee (₹1.99 against ₹1.995) suggest each leg is computed separately and truncated. Task 3 must match within ₹0.01.

## (c) Calendar

2026 NSE trading holidays (cash market, from `holidays.json`): 15 Jan, 26 Jan, 15 Feb, 3 Mar, 21 Mar, 26 Mar, 31 Mar, 3 Apr, 14 Apr, 1 May, 28 May, 26 Jun, 15 Aug, 14 Sep, 2 Oct, 20 Oct, 8 Nov (Diwali, Sunday), 10 Nov, 24 Nov, 25 Dec.

- **Muhurat 2026:** Sunday 8 Nov, normal market 14:20 to 15:30 IST (NSE circular CMTR76941, 19 Oct 2026). The holiday API has no Muhurat times (`morning_session` is null), so they are entered by hand as the spec says.
- **2027:** not published yet. The calendar must say "holiday list unknown for 2027" until it is added.

## (d) Rules

- **SEBI retail algo framework, in force since 1 Apr 2026:** every order placed through the API must come from a **static IP whitelisted in Kite**. Unregistered IPs are rejected, and the whitelist can be changed once a week. Reading data (quotes, positions, websocket) works from any IP. Up to 10 orders per second needs no exchange registration. **Effect:** live orders from `bharat-broker` only work from the user's whitelisted IP. The SKILL.md must say so, and the paper ledger stays the default.
- **Kite Connect:** "Personal" is free (orders, no market data); "Connect" is ₹500/month (adds market data).
- **Kite MCP (zerodha/kite-mcp-server):** order tools exist (`place_order`, `modify_order`, `cancel_order`, `place_gtt_order`), but **the hosted `mcp.kite.trade` leaves order tools out**. Placing orders needs a self-hosted server with the user's own API key, and the static-IP rule applies to it.
- **Expiries:** NIFTY weekly expiry is Tuesday, monthly on the last Tuesday. BANKNIFTY is monthly only (last Tuesday). Lot sizes: NIFTY 65, BANKNIFTY 30 (`fo_mktlots.csv`).
- **New, not in the spec:** the Muhurat circular mentions a closing auction session where some stocks stop normal trading at 15:15. Check in P2 whether this applies on normal days; the default `flat_by` of 15:15 already avoids it.

## (e) Worked example

**RELIANCE, Monday 19 Oct 2026**, 5-minute bars (`tests/fixtures/example/RELIANCE-5m.json`, the 60 sessions from 7 Aug to 3 Nov 2026):

| Bar (IST) | Open | High | Low | Close |
| --- | --- | --- | --- | --- |
| 9:15 | 1212.20 | **1223.40** | 1211.90 | 1218.20 |
| 9:20 | 1218.00 | 1218.90 | 1214.00 | 1215.00 |
| 9:25 | 1215.50 | 1215.50 | **1207.30** | 1208.40 |
| 9:30 | 1208.30 | 1216.30 | 1207.80 | 1215.00 |
| 9:35 | 1215.30 | 1221.00 | 1215.30 | 1218.80 |
| 9:40 | 1219.00 | 1221.80 | 1216.10 | 1221.80 |
| 9:45 | 1221.70 | 1228.00 | 1220.60 | **1227.80** |

- 15-minute opening range: 1207.30 to 1223.40.
- Trigger: the 9:45 bar, the first close above the range, at 1227.80. It is known when the bar closes at 9:50.
- Like the US example, this falls on 19 Oct 2026 (the day before the Dussehra holiday).

The remaining example numbers (stop, target, size, Time Machine odds) are computed by the tools in Tasks 6 to 9 and pinned in `tests/example_values.py`.

## What this changes in the spec

1. **The rate table:** use section (b), not the spec's starting values.
2. **BSE fallback for news is dropped.** BSE blocks scripts. News uses NSE announcements plus Yahoo RSS. If NSE fails, the output says so.
3. **bharat-insider:** bulk and block deals come from the latest-day snapshot only (no history). FII/DII is latest day only. The `index`/`new` state builds history over runs instead.
4. **bharat-analyst** reads `integrated-filing-results` plus its XBRL (`in-capmkt:`), not the older results list.
5. **bharat-entry:** opening-range volume skips the 9:15 bar (always 0 on Yahoo).
6. **bharat-broker live mode:** needs a self-hosted Kite MCP server or the Kite Connect API, run from a whitelisted static IP. The hosted Kite MCP is read-only for orders.

# P2 findings

Checked 2026-11-04. Raw files are in `tests/fixtures/p2/`. Re-run with
`python3 -I tools/probe.py --p2 [--days 20261016,20261019,20261021]`.

## Data

| Source | Status | Notes |
| --- | --- | --- |
| Yahoo 5m `^NSEI`, `^NSEBANK` (60d) | OK | Index volume is 0 on every bar, so a volume filter can never pass on an index. |
| F&O bhavcopy 16, 19, 21 Oct 2026 | OK | Old days still download from the archive. Futures rows: `FinInstrmTp` `IDF`; `NewBrdLotQty` carries the lot. |
| `fo_mktlots.csv` | OK | **Only current and future months** (NOV-26 to JUN-31 on 4 Nov). An expired contract's month (OCT-26) is gone, so a past contract's lot must come from its bhavcopy row. NIFTY has a JUN-31 column (65); BANKNIFTY is blank from DEC-27. |

## Costs (futures)

`zerodha-calc-fut.json`: three cases from Zerodha's calculator (`cal_futures` read on the page). Same rounding as intraday: STT (0.05% sell) and stamp (0.002% buy) to the whole rupee, brokerage per order capped at Rs 20, exchange 0.00173% plus IPFT 0.0001% each to 2 dp, SEBI to 2 dp, GST 18%. `india.round_trip("fut", ...)` already matches all three to the paisa; `RATES["fut"]` needs no change.

## Orders and margin

- **SL-M on NFO futures: allowed.** NSE stopped SL-M for options only (27 Sep 2021; Zerodha blocked it for index options from 20 Sep 2021). BSE dropped SL-M for everything (BFO is out of scope). So index futures keep the SL-M stop; the SL (stop-limit) variant is not needed in P2. It is needed in P3 (options).
- **Market protection is mandatory for API orders (exchange rule since 1 Apr 2026).** Kite rejects MARKET and SL-M orders with `market_protection` 0 or missing. Values: above 0 up to 100 (percent) or `-1` (automatic). **This also hits P1:** `bharat-broker/ticket.py` sends MARKET entries and SL-M stops with no `market_protection`, so live equity orders would be rejected today.
- **Kite `place_order` for NFO:** `variety: regular`, `exchange: NFO`, `tradingsymbol` = the contract (`NIFTY26OCTFUT`), `transaction_type`, `order_type`, `quantity` in units (lots x lot), `product: MIS` (or NRML), `trigger_price` for SL/SL-M, `market_protection` for MARKET/SL-M. Optional `autoslice` for orders above the freeze limit.
- **MIS margin = NRML margin** (Zerodha bulletin, 4 Nov 2026: "Index F&O 1X (100% of NRML margins (SPAN + Exposure))"). Auto square-off for index derivatives is 3:26 PM; `flat_by` 15:15 is ahead of it.
- **Margin on 4 Nov 2026** (Zerodha SPAN calculator, 1 lot, buy; README example only, never a default): NIFTY26NOVFUT Rs 1,75,953 (SPAN 1,45,038 + exposure 30,915); BANKNIFTY26NOVFUT Rs 1,89,482 (SPAN 1,56,143 + exposure 33,339).
- Seen in passing for P3: the NIFTY weekly option expiring in the 10 Nov holiday week expires Monday 9 Nov.

## Worked example

**NIFTY, Wednesday 21 Oct 2026** (the session after the 20 Oct Dussehra holiday). 19 Oct is not usable: NIFTY broke down that day and bharat-entry is long-only.

| Bar (IST) | Open | High | Low | Close |
| --- | --- | --- | --- | --- |
| 9:15 | 23016.00 | 23063.35 | **22981.35** | 23039.20 |
| 9:20 | 23040.15 | 23085.60 | 23036.80 | 23076.60 |
| 9:25 | 23076.85 | **23086.75** | 23064.25 | 23079.85 |
| 9:30 | 23080.95 | 23118.30 | 23069.20 | **23115.65** |

- Opening range 22981.35 to 23086.75; trigger the 9:30 bar, close 23115.65, known at 9:35 (`entry.py check NIFTY --now "2026-10-21 09:35"` prints it).
- Contract: **NIFTY26OCTFUT**, expiry Tue 27 Oct 2026, lot 65 (bhavcopy row; `fo_mktlots.csv` no longer has OCT-26).
- Basis from the last session's bhavcopy (**19 Oct**, since 20 Oct was a holiday): close 22895.20 / underlying 22888.95 = **1.000273**. Futures price at the trigger: 23115.65 x 1.000273 = 23121.96, tick-rounded **23121.95**. One lot is Rs 15.03 lakh notional.
- Stale-basis fixture: the 16 Oct bhavcopy is two sessions old on 21 Oct (NIFTY26OCTFUT 23119.20 / 23146.15 = 0.998836).
- **The basis moves a lot in one session.** The 21 Oct close basis was 22743.30 / 22811.35 = 0.997017. Priced with that, the trigger is 23046.69, 75 points (Rs 4,893 a lot) under the estimate from 19 Oct. The estimated futures price is fine for planning the stop distance in points, but not as an entry price.

## What this changes in the plan

1. **Task 2, `lot_size`:** the bhavcopy row's lot is the contract's lot; `fo_mktlots.csv` covers months the bhavcopy has no row for (a live plan for a new month). The planned failing case `NIFTY 2031-06` exists (65); use BANKNIFTY Dec 2027 (blank) or NIFTY Jul 2031 (no column).
2. **Task 8:** keep SL-M for futures (the SL variant and `stop_limit_ticks` are not needed until P3). Add `market_protection: -1` to every MARKET and SL-M Kite call, equity included (a P1 fix).
3. **Tasks 3, 4, 7:** the example is 21 Oct, not 19 Oct; the previous session is 19 Oct; the 16 Oct bhavcopy is the stale one. Given the 75-point basis swing, the futures stop and target should be carried as points from the entry (re-anchored on the fill), and the ticket should say the entry price is estimated.

# P3 findings

Checked 2026-11-04 (after the close). Raw files are in `tests/fixtures/p3/`; the example's bhavcopies are
the P2 ones (`tests/fixtures/p2/fo-bhavcopy-2026101{6,9}`, `-20261021`). Re-run the chain with
`python3 -I tools/probe.py --p3 --expiry 09-Nov-2026`.

## Costs (options)

`zerodha-calc-opt.json`: the three planned cases, run through `cal_options` on Zerodha's page. Brokerage Rs 20
an order flat (Rs 40 a round trip), STT 0.15 % of the sell premium to the whole rupee, exchange 0.03503 % plus
IPFT 0.0005 % each to 2 dp, SEBI 0.0001 %, stamp 0.003 % of the buy to the whole rupee, GST 18 % on brokerage +
exchange + SEBI. `india.round_trip("opt", ...)` matches all three to the paisa; `RATES["opt"]` needs no change.
The cheap case (65 x Rs 3.00 to 3.50) costs Rs 47.38 against a Rs 32.50 gross gain.

## The model

- **Our Black-Scholes matches NSE's IV.** `iv-check.json`: four NIFTY 9 Nov strikes from NSE's option chain
  (ATM call and put 23950, 24050 CE, 23850 PE). With NSE's own premium and spot, rate 0.06, no dividend and time
  = calendar minutes to 15:30 IST on expiry / (365 x 1440), our IV lands within **0.06 points** of NSE's on every
  row (the plan allows 0.5). Rate 0 or 0.10 misses by up to 1 point, so NSE uses about 6 %.
- **But spot Black-Scholes splits calls from puts.** On the same strike the put's IV is far above the call's:
  4 Nov 18.0 vs 11.7 (23950); 21 Oct 21.6 vs 12.5 (23100, 27 Oct expiry). The options are priced off the
  forward, and NIFTY's futures traded 68 points under spot on 21 Oct (P2 finding). Priced as Black-76 on the
  forward, the same premiums give one IV: 21 Oct 14.5 to 15.3 for both rights across 23000-23200; 19 Oct 12.4
  to 12.7.
- **The forward from put-call parity** (`F = K + e^(rT) (C - P)` at the ATM strike, same expiry, from the
  bhavcopy closes) is within 3 points of the future's close for the monthly expiry (19 Oct 22897.25 vs
  22895.20; 21 Oct 22739.94 vs 22743.30) and gives a forward for weekly expiries too, which have no future.
- No free intraday option prices exist, so the premium at a trigger can only be modelled, never checked.

## Orders and rules

- **SL-M is not allowed for options** (NSE since 27 Sep 2021; P2 finding). The stop goes as SL with a limit a
  few ticks through the trigger.
- **Market orders:** Zerodha blocks them for stock options; index options take them only with market
  protection, which is mandatory on API orders since 1 Apr 2026. The plan's LIMIT-only entries stand.
  Zerodha also rejects a limit buy over 150 % above the LTP or a sell under 50 % below it, and blocks fresh
  orders in low-OI contracts (exits always allowed): both agree with `min_option_oi` and limit exits.
- **STT on an exercised ITM option: 0.15 % of the intrinsic value**, paid by the buyer (up from 0.125 %, from
  1 Apr 2026; secondary sources, not the Finance Act text). The 15:00 expiry alert's message stands.
- **Freeze limits from 2 Nov 2026** (NSE/FAOP/77189, via Zerodha TradingQnA): NIFTY 1,800 units (27 lots),
  BANKNIFTY 900 (30 lots). An order above it must be sliced. The example (1 lot) is far under.
- **Symbols, from the bhavcopy:** weekly `NIFTY26O1923100CE` (YY, month code 1-9/O/N/D, DD), monthly
  `NIFTY26OCT23100CE`. A weekly that falls in the monthly's week is the monthly (27 Oct has only `NIFTY26OCT...`).
  The 20 Oct Dussehra holiday moved that week's expiry to Monday 19 Oct.
- **Units:** bhavcopy `OpnIntrst` is in units; the NSE chain's `openInterest` is in contracts (lots). An
  expiring option's `SttlmPric` is the index, not a premium; use `ClsPric`.

## Worked example

Same session as P2: **NIFTY, 21 Oct 2026**, ORB trigger at 9:35 on the index at 23115.65.

- Contract: **NIFTY26OCT23100CE** (ATM: 23115.65 to the nearest 50), expiry Tue 27 Oct, lot 65. The 19 Oct weekly
  expired on 19 Oct, so 27 Oct is the nearest expiry that is not today.
- Last session's bhavcopy (19 Oct): close **87.25** at index 22888.95, OI 49,34,930 units.
- Time to expiry at the trigger: 8,995 minutes (21 Oct 9:35 to 27 Oct 15:30) = 0.017114 years.
- Spot Black-Scholes (the plan as written): IV 11.92 % from 87.25 with 8 days left, premium at the trigger
  **164.25**.
- Black-76 on the future's basis: IV 12.56 %, forward 23121.96, premium 162.55. On the parity forward (the model
  chosen, ratio 1.000362 from the 19 Oct ATM pair): IV **12.50 %**, premium **162.95**.
- That day the option closed at 50.05 (the index fell to 22811.35 by the close): the bought call lost.

## What this changes in the plan (for review)

1. **Model (Tasks 2-5), a choice:** (a) the plan as written, spot Black-Scholes; or (b) recommended: Black-76
   on a forward = index x the parity ratio from the bhavcopy (same expiry), held constant for the replay, the
   way P2 holds the futures basis. (b) needs no new pricing function (`bs_price` with spot = F e^(-rT)), keeps
   `iv-check.json` as the test of the formula, and stops a put's IV reading 6-9 points above the call's.
2. **Task 2:** test the symbol round trip on the 19 Oct bhavcopy (it has weekly, holiday-shifted and monthly
   names); pick strikes by `ClsPric`, never `SttlmPric`.
3. **Task 3:** the example's expiry is the 27 Oct monthly; the estimated premium is 164.25 (a) or 162.55 (b).
4. **Task 7:** the stop is SL (limit `stop_limit_ticks` below), as planned; entries and flatten stay LIMIT.
