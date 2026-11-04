"""The worked example's numbers (RELIANCE, Mon 19 Oct 2026), each pinned by a
skill's own test. The README test checks every one of them appears in the README."""

SYMBOL = "RELIANCE"
DATE = "2026-10-19"
SCAN_AT = "10:15"
SCAN_HITS = 8           # of the NIFTY 50
OR_HIGH = 1223.40
OR_LOW = 1207.30
TRIGGER_BAR = "09:45"
TRIGGER_AT = "9:50 AM"
TRIGGER_CLOSE = 1227.80
PCT_OVER = 0.36
STOP = 1215.35          # bharat-exit: the opening-range midpoint
TARGET = 1240.25        # 1R
RISK_PER_SHARE = 12.45
TM_TARGET = 0.1702      # bharat-timemachine, seed 19, to the 15:15 flat-by
TM_STOP = 0.1767
TM_NEITHER = 0.6531
TM_SESSIONS = 48
TM_FIRED = 22
TM_H_TARGET = 10
TM_H_STOP = 10
TM_H_NEITHER = 2
ACCOUNT = 200000        # bharat-budget: the example account, Rs 2,00,000
MAX_LOSS_LIMIT = 1000   # max loss per trade
QTY = 73
COSTS_AT_STOP = 78.88
MAX_LOSS = 987.73       # 73 x 12.45 + 78.88

# Index futures (P2): NIFTY, Wed 21 Oct 2026, the session after the Dussehra holiday
FUT_SYMBOL = "NIFTY"
FUT_DATE = "2026-10-21"
FUT_OR_HIGH = 23086.75
FUT_OR_LOW = 22981.35
FUT_TRIGGER_AT = "9:35 AM"
FUT_TRIGGER_CLOSE = 23115.65   # the index
FUT_CONTRACT = "NIFTY26OCTFUT"
FUT_EXPIRY = "2026-10-27"
FUT_LOT = 65
FUT_BASIS_DATE = "2026-10-19"  # the last session's bhavcopy
FUT_BASIS = 22895.20 / 22888.95
FUT_PRICE = 23121.95           # 23115.65 x basis, tick 0.05
FUT_INDEX_STOP = 23034.05      # bharat-exit: the index's opening-range midpoint
FUT_STOP = 23040.30            # the futures stop: entry - 81.60 x basis, tick down
FUT_TARGET = 23203.60          # 1R in futures points, tick up
FUT_RISK_PER_UNIT = 81.65
FUT_RISK_PER_LOT = 5307.25     # 81.65 x 65
