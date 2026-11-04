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
