import json
import os
import sys
import unittest
from datetime import date, datetime, time, timezone

from _load import FIX, ROOT

sys.path.insert(0, os.path.join(ROOT, "india"))
sys.modules.pop("india", None)
import india  # noqa: E402


class Calendar(unittest.TestCase):
    def test_holiday(self):
        ok, why = india.trading_day(date(2026, 1, 26))
        self.assertFalse(ok)
        self.assertTrue(why.startswith("NSE holiday"), why)

    def test_weekend(self):
        self.assertEqual(india.trading_day(date(2026, 11, 7)), (False, "weekend"))

    def test_unknown_year(self):
        self.assertEqual(india.trading_day(date(2028, 3, 1))[1], "holiday list unknown for 2028")
        self.assertFalse(india.trading_day(date(2028, 3, 1))[0])

    def test_normal_day(self):
        self.assertEqual(india.trading_day(date(2026, 10, 19)), (True, ""))
        o, c = india.session(date(2026, 10, 19))
        self.assertEqual((o.time(), c.time()), (time(9, 15), time(15, 30)))

    def test_muhurat(self):
        self.assertTrue(india.trading_day(date(2026, 11, 8))[0])
        o, c = india.session(date(2026, 11, 8))
        self.assertEqual((o.time(), c.time()), (time(14, 20), time(15, 30)))

    def test_closed_day_has_no_session(self):
        self.assertIsNone(india.session(date(2026, 10, 20)))  # Dussehra

    def test_next_open_skips_holiday(self):
        self.assertEqual(india.next_open(date(2026, 10, 19)), datetime(2026, 10, 21, 9, 15, tzinfo=india.IST))


class Clock(unittest.TestCase):
    def test_to_ist(self):
        self.assertEqual(india.to_ist(datetime(2026, 11, 4, 3, 45, tzinfo=timezone.utc)).time(), time(9, 15))

    def test_naive_is_ist(self):
        self.assertEqual(india.ist_to_utc(datetime(2026, 11, 4, 9, 15)),
                         datetime(2026, 11, 4, 3, 45, tzinfo=timezone.utc))


class Symbols(unittest.TestCase):
    def test_yahoo(self):
        self.assertEqual(india.yahoo_symbol("M&M"), "M&M.NS")
        self.assertEqual(india.yahoo_symbol("BAJAJ-AUTO"), "BAJAJ-AUTO.NS")
        self.assertEqual(india.yahoo_symbol("NIFTY"), "^NSEI")
        self.assertEqual(india.yahoo_symbol("banknifty"), "^NSEBANK")
        self.assertEqual(india.yahoo_symbol("TCS.BO"), "TCS.BO")
        self.assertEqual(india.yahoo_symbol("^NSEI"), "^NSEI")
        self.assertEqual(india.yahoo_symbol(" reliance "), "RELIANCE.NS")


class Costs(unittest.TestCase):
    def test_matches_zerodha_calculator(self):
        with open(os.path.join(FIX, "p0", "zerodha-calc.json")) as fh:
            rows = json.load(fh)["rows"]
        for r in rows:
            got = india.round_trip(r["segment"], r["qty"], r["buy"], r["sell"])
            for k in ("brokerage", "stt", "exchange", "sebi", "stamp", "gst", "total"):
                self.assertAlmostEqual(got[k], r[k], delta=0.01, msg="%s %s" % (k, r))

    def test_leg_costs_sell_pays_stt_buy_pays_stamp(self):
        buy = india.leg_costs("eq_intraday", "buy", 100, 1400)
        sell = india.leg_costs("eq_intraday", "sell", 100, 1410)
        self.assertEqual(buy["stt"], 0)
        self.assertEqual(sell["stamp"], 0)
        self.assertEqual(buy["stamp"], 4)
        self.assertEqual(sell["stt"], 35)
        self.assertEqual(buy["brokerage"], 20)

    def test_unknown_segment(self):
        with self.assertRaises(ValueError):
            india.round_trip("mtf", 1, 1, 1)

    def test_rates_are_dated(self):
        self.assertEqual(india.RATES["checked"], "2026-11-04")


class Prices(unittest.TestCase):
    def test_tick_round(self):
        self.assertEqual(india.tick_round(1402.33), 1402.35)
        self.assertEqual(india.tick_round(1402.33, mode="down"), 1402.30)
        self.assertEqual(india.tick_round(1402.31, mode="up"), 1402.35)
        self.assertEqual(india.tick_round(1215.35), 1215.35)

    def test_band(self):
        self.assertTrue(india.band_ok(110.0, 100.0, 10))
        self.assertFalse(india.band_ok(110.05, 100.0, 10))
        self.assertTrue(india.band_ok(89.95, 100.0, None))  # "No Band"


class Fetch(unittest.TestCase):
    def test_html_is_an_error(self):
        class Resp:
            headers = {}
            def read(self):
                return b"<!DOCTYPE html><html>blocked</html>"
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        class Opener:
            def open(self, req, timeout=None):
                return Resp()

        with self.assertRaises(india.NSEError) as cm:
            india.nse_get("https://www.nseindia.com/api/x", opener=Opener(), warm=False)
        self.assertIn("api/x", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
