# India Trader skill: design

Date: 2026-11-04
Status: draft for review

## Goal

A public, MIT-licensed pack of 11 Claude skills for intraday trading on Indian
exchanges (NSE first, BSE where data needs it). It works like the US pack
(github.com/Jakeschincariol/day-trader-skill): plain standard-library Python
over free public data, each skill writes to a `trader/` folder for the next
one to read, and no order goes through until the user types yes.

Success means:

- Someone can install any one skill folder by itself and it works.
- The README walks through one worked example trade on real NSE data, and
  offline tests on fixtures reproduce every number in it.
- Cash stocks, index futures and index options are all covered by the end
  of phase 3.

## Decisions made

| Question | Decision |
| --- | --- |
| Audience | Public release, its own repo |
| Broker | Zerodha Kite first; local simulated ledger is the default |
| Instruments | Cash stocks, index futures, index options, built in 3 phases |
| Pelosi replacement | One skill: insider/promoter trades, bulk/block deals, FII/DII flows |
| Code layout | Each skill self-contained; India rules in a per-skill `india.py` kept identical by a test |
| Relation to US pack | Adapted copy. Keep Jake Schincariol's MIT copyright line in LICENSE and credit the original in the README |

Not doing: a market switch in the US repo, a shared package that skills
import, MCX commodities, currency derivatives, stock options, margin
trading facility (MTF), short selling beyond intraday MIS.

## Repo layout

```
india-trader-skill/
  .claude-plugin/{marketplace.json,plugin.json}
  LICENSE              MIT, original copyright + new line
  README.md
  bharat-scanner/      SKILL.md, scan.py, india.py
  bharat-news/         SKILL.md, news.py, india.py
  bharat-entry/        SKILL.md, entry.py, india.py
  bharat-exit/         SKILL.md, exit.py, india.py
  bharat-timemachine/  SKILL.md, timemachine.py, india.py
  bharat-budget/       SKILL.md, size.py, config.example.json, india.py
  bharat-risk/         SKILL.md, check.py, india.py
  bharat-broker/       SKILL.md, ticket.py, ledger.py, india.py
  bharat-alerts/       SKILL.md, alerts.py, india.py
  bharat-analyst/      SKILL.md, results.py, india.py
  bharat-insider/      SKILL.md, insider.py, india.py
  tests/               one test file per skill, test_repo.py, fixtures/
```

Each script starts as a copy of the matching US script and has its US
parts replaced. Skills not changed by a phase stay as they are.

## `india.py` (the same file in every skill)

One file holding every India-specific rule, so the skill scripts don't
contain them. `tests/test_repo.py` fails if any skill's copy differs from
the others.

- **Clock:** `Asia/Kolkata`. Pre-open 9:00–9:08, regular session
  9:15–15:30, MIS auto square-off 15:20 (Zerodha; the broker setting can
  change it). Default "flat by" time is 15:15.
- **Calendar:** NSE trading holidays for 2026 and 2027, plus the Muhurat
  session (its date and times are entered by hand each year). For years
  not on the list, the calendar reports "holiday list unknown" instead of
  guessing.
- **Symbols:** NSE symbol to Yahoo (`RELIANCE` to `RELIANCE.NS`), index
  names (`NIFTY` to `^NSEI`, `BANKNIFTY` to `^NSEBANK`), F&O contract
  names (`NIFTY26NOVFUT`, `NIFTY26N1024500CE`), and the instrument tokens
  Kite needs.
- **Costs:** `costs(segment, side, qty, price)` returns brokerage, STT,
  exchange transaction charge, SEBI fee, GST and stamp duty. The segment
  is `eq_intraday`, `fut` or `opt`. Starting rates (to be confirmed in
  phase 0 against Zerodha's brokerage calculator and the current Union
  Budget):
  - Brokerage: the lower of ₹20 and 0.03% per executed order (intraday
    stocks); ₹20 flat (futures and options).
  - STT, on the sell side: 0.025% (intraday stocks), 0.02% (futures),
    0.1% of premium (options).
  - NSE transaction charge: 0.00297% (stocks), 0.00173% (futures),
    0.03503% of premium (options).
  - SEBI fee: ₹10 per crore of turnover.
  - Stamp duty, on the buy side: 0.003% (stocks), 0.002% (futures),
    0.003% (options).
  - GST: 18% on brokerage, the exchange charge and the SEBI fee.
  All rates live in one table with the date they were checked. A user
  config file can override them.
- **Contract data:** lot sizes and expiry dates come from NSE's published
  F&O contract list. They are cached by date, never hard-coded.
- **Exchange limits:** a stock's daily price band (2/5/10/20%) from NSE's
  price-band file, and the F&O ban list.

## The 11 skills

| Skill | Starts from | What changes |
| --- | --- | --- |
| bharat-scanner | trader-scanner | Universe from NSE `EQUITY_L.csv` (cash) and the F&O list. Opening range from 9:15. Setups unchanged (ORB, flags, oversold bounce). Filters: price band, F&O ban, minimum turnover in ₹. |
| bharat-news | trader-news | Yahoo RSS for `.NS` tickers, plus NSE and BSE corporate announcements in place of SEC 8-Ks. Times in IST. Tags results, board meetings, dividends/splits, block deals. |
| bharat-entry | trader-entry | NSE session times. Same trigger logic. Warns when the stock is near its price band. |
| bharat-exit | trader-exit | Flat by 15:15. Stops and targets rounded to the ₹0.05 tick (the tick size is read per instrument). |
| bharat-timemachine | trader-timemachine | IST bars and NSE days. P3: replays the underlying index and prices the option at each step (see Options). |
| bharat-budget | trader-budget | Sizes in ₹. Loss per trade includes round-trip costs from `india.costs`. Futures and options are sized in whole lots. MIS leverage is optional and capped at the broker's limit. |
| bharat-risk | trader-risk | Drops the PDT rule. Adds checks for price band, F&O ban, lot multiple, expiry day, the square-off window, and costs as a share of the expected reward (BLOCK above a configurable threshold, default 25%). |
| bharat-broker | trader-broker | Default: `ledger.py`, a local paper ledger that fills at the next bar's open plus a configurable slippage, and applies costs. Live: Zerodha via its Kite MCP server or the Kite Connect API, with bracket-like orders sent as an entry plus a GTT/SL-M stop. Two yeses as today: one typed in chat, plus Claude's tool approval. |
| bharat-alerts | trader-alerts | IST clock, NSE calendar, a 15:15 flatten alert, an expiry-day alert. |
| bharat-analyst | trader-analyst | Quarterly results from NSE's XBRL financial-results filings: revenue, operating profit, PAT and EPS, quarter over quarter and year over year. |
| bharat-insider | trader-pelosi | Three feeds: SEBI insider-trading (PIT) disclosures filed on NSE, NSE bulk and block deals, and NSE's daily FII/DII cash figures. Same index/new-since-last-run flow as the Pelosi skill. |

## Data sources

| Need | Source | Notes |
| --- | --- | --- |
| Intraday stock and index bars | Yahoo chart API (`.NS`, `^NSEI`, `^NSEBANK`) | Same code path as the US pack |
| Symbol universe | `nsearchives.nseindia.com/content/equities/EQUITY_L.csv` | Plain download |
| F&O contracts, lot sizes | NSE F&O contract/lot-size files | Cached by date |
| F&O end-of-day prices | NSE F&O bhavcopy | For history and the Time Machine |
| F&O intraday prices | Kite Connect API | Optional. Needs the user's own key; without one, options are planned from end-of-day data only |
| Announcements, insider, bulk/block, FII/DII | NSE (and BSE) JSON endpoints | NSE blocks scripted access: fetch the home page for cookies, send a browser-like User-Agent, back off, and cache. If an endpoint fails, report it and continue with partial results; never invent data |
| Quarterly results | NSE XBRL results files | |

NSE endpoints change without notice, so every fetcher has an `--offline
<fixtures dir>` mode, and the tests only use that mode.

## Phases

**P0: check that the data works (no skill code).** Fetch every source
above once and save the results as fixtures. Confirm the cost rates against
Zerodha's calculator. Confirm the current SEBI rules on retail API orders
(registered apps, static IP above a certain order rate) and the current
index expiry schedule and contract sizes. Write down anything that breaks
this design and revise the spec before P1.

**P1: cash stocks.** All 11 skills for NSE stocks traded intraday (MIS),
using the paper ledger and Zerodha. A README worked example: one real NSE
stock on one real 2026 session, the same chain as the US README. Tests
reproduce every number in it.

**P2: index futures.** NIFTY and BANKNIFTY futures: lot sizing, margin
from Zerodha's SPAN calculator (or a user-entered figure), rollover and
expiry warnings, and futures prices in the Time Machine.

**P3: index options.** Buying options only (no option selling in v1,
because the margin and unlimited-loss rules are a separate project).
Sizing by premium times lot size. Expiry-day rules. The Time Machine
replays the underlying and reprices the option with Black-Scholes, using
implied volatility backed out of the latest premium and the same IV for
the whole replay (a stated limitation). Strike picker: ATM ± N strikes.

Each phase ends with its tests passing and the README updated. It is
shippable on its own.

## Safety and fine print

- No order without the user's typed yes for that exact order, plus
  Claude's tool approval. The paper ledger is the default
  (`"paper": true`).
- Keys only in environment variables (`KITE_API_KEY`,
  `KITE_ACCESS_TOKEN`), never in chat or config files.
- README fine print, rewritten for India: not investment advice and the
  authors are not SEBI-registered advisers; SEBI's studies show most
  retail intraday and F&O traders lose money; intraday profit is taxed as
  speculative business income and F&O as non-speculative business income
  (not tax advice); the data is free and unofficial; a stop is a plan,
  not a guarantee, and a price-band freeze can stop you exiting; Time
  Machine odds are not predictions.

## Testing

Same style as the US pack: `python3 -m unittest discover -s tests`, offline
only, fixtures cut from real data saved in P0/P1. Each skill has one test
file. `test_repo.py` checks that the `india.py` copies are identical, every
SKILL.md has front matter, and the plugin manifests list all 11 skills.
Costs are tested against Zerodha calculator outputs saved in P0.

## Risks

- **NSE blocking scripts** is the biggest risk. Mitigations: caching,
  offline mode, BSE as a fallback for announcements, and failures reported
  clearly.
- **Rules change often** (STT, lot sizes, expiry days, the algo
  framework). Every rate is in one table with the date it was checked;
  contract data is downloaded, not hard-coded.
- **Kite Connect** may need a paid plan for live market data. Phase 1
  works without it.
