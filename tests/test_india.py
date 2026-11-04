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


class Rupees(unittest.TestCase):
    def test_lakh_grouping(self):
        self.assertEqual(india.inr(200000), "Rs 2,00,000")
        self.assertEqual(india.inr(89629.4), "Rs 89,629.40")
        self.assertEqual(india.inr(12345678.5), "Rs 1,23,45,678.50")
        self.assertEqual(india.inr(987.73), "Rs 987.73")
        self.assertEqual(india.inr(-1000), "-Rs 1,000")
        self.assertEqual(india.inr(1227.8, paise=True), "Rs 1,227.80")


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


P2 = os.path.join(FIX, "p2")


def _bhav(name, folder="p2"):
    with open(os.path.join(FIX, folder, name), "rb") as fh:
        return india.parse_bhavcopy(fh.read())


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _bhav("fo-bhavcopy-20261103.csv.zip", "p0")
        with open(os.path.join(P2, "fo_mktlots.csv")) as fh:
            cls.lots = india.parse_lot_sizes(fh.read())

    def test_nifty_front_month(self):
        f = india.futures(self.rows, "NIFTY")[0]
        self.assertEqual(f["contract"], "NIFTY26NOVFUT")
        self.assertEqual(f["expiry"], date(2026, 11, 23))
        self.assertEqual((f["kind"], f["lot"], f["close"], f["underlying"]), ("fut", 65, 23780.50, 23810.85))
        self.assertEqual(f["date"], date(2026, 11, 3))
        self.assertEqual([x["expiry"] for x in india.futures(self.rows, "NIFTY")],
                         [date(2026, 11, 23), date(2026, 12, 29), date(2027, 1, 25)])

    def test_options_rows(self):
        o = [r for r in self.rows if r["contract"] == "NIFTY26N0924400PE"][0]
        self.assertEqual((o["kind"], o["strike"], o["right"]), ("opt", 24400.0, "PE"))

    def test_front_future_skips_expiry_day(self):
        self.assertEqual(india.front_future(self.rows, "NIFTY", date(2026, 11, 20))["contract"], "NIFTY26NOVFUT")
        self.assertEqual(india.front_future(self.rows, "NIFTY", date(2026, 11, 23))["contract"], "NIFTY26DECFUT")
        # roll 1 trading day early: 20 Nov is the day before the 23 Nov expiry
        self.assertEqual(india.front_future(self.rows, "NIFTY", date(2026, 11, 20), roll_days=1)["contract"],
                         "NIFTY26DECFUT")
        self.assertIsNone(india.front_future(self.rows, "NOSUCH", date(2026, 11, 20)))

    def test_expiry_day(self):
        self.assertTrue(india.is_expiry_day(self.rows, "NIFTY", date(2026, 11, 23)))
        self.assertFalse(india.is_expiry_day(self.rows, "NIFTY", date(2026, 11, 24)))  # holiday

    def test_basis_ratio(self):
        f = india.futures(self.rows, "NIFTY")[0]
        self.assertEqual(india.basis_ratio(f), 23780.50 / 23810.85)

    def test_lot_sizes(self):
        self.assertEqual(self.lots["NIFTY"]["2026-11"], 65)
        self.assertEqual(india.lot_size(self.lots, "BANKNIFTY", date(2026, 12, 29)), 30)
        with self.assertRaises(ValueError):
            india.lot_size(self.lots, "BANKNIFTY", date(2027, 12, 28))  # blank cell
        with self.assertRaises(ValueError):
            india.lot_size(self.lots, "NIFTY", date(2031, 7, 29))  # no column
        with self.assertRaises(ValueError):
            india.lot_size(self.lots, "NOSUCH", date(2026, 11, 23))

    def test_plain_csv_and_old_day(self):
        import io, zipfile
        with open(os.path.join(P2, "fo-bhavcopy-20261019.csv.zip"), "rb") as fh:
            z = zipfile.ZipFile(io.BytesIO(fh.read()))
            plain = z.read(z.namelist()[0])
        f = india.front_future(india.parse_bhavcopy(plain), "NIFTY", date(2026, 10, 21))
        self.assertEqual((f["contract"], f["close"], f["underlying"]), ("NIFTY26OCTFUT", 22895.20, 22888.95))

    def test_fut_costs_match_zerodha(self):
        with open(os.path.join(P2, "zerodha-calc-fut.json")) as fh:
            rows = json.load(fh)["rows"]
        for r in rows:
            c = india.round_trip("fut", r["qty"], r["buy"], r["sell"])
            for k in india.COST_KEYS:
                self.assertAlmostEqual(c[k], r[k], delta=0.01, msg="%s %s" % (k, r))


if __name__ == "__main__":
    unittest.main()
