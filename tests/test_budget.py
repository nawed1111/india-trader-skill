import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, ROOT, FIX
import example_values as EX

size = load("bharat-budget", "size")

CFG = os.path.join(ROOT, "bharat-budget", "config.example.json")
PLAN = os.path.join(FIX, "bharat-budget", "plan-reliance.json")
NOW = "2026-10-19 09:51"
TODAY = "2026-10-19"
CONFIG_KEYS = {
    "budget": 200000, "cash_buffer_pct": 10, "max_position_pct": 75, "max_order_inr": 200000, "min_order_inr": 500,
    "max_loss_per_trade_inr": 1000, "max_daily_loss_inr": 3000, "max_trades_per_day": 3, "max_orders_per_day": 10,
    "min_reward_risk": 1.0, "max_cost_share": 0.25, "require_stop": True,
    "no_entries_before": "09:30", "no_entries_after": "14:45", "flat_by": "15:15", "mis_leverage": 1,
    "broker": "zerodha", "paper": True, "blocked": [], "allow_fno": False, "allow_margin": False,
    "allow_short": False,
}


def cfg(**over):
    with open(CFG) as fh:
        c = json.load(fh)
    c.update(over)
    return c


def the_plan(**over):
    with open(PLAN) as fh:
        p = json.load(fh)
    p.update(over)
    return p


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = size.main(argv)
    return code, out.getvalue(), err.getvalue()


class TheExample(unittest.TestCase):
    def setUp(self):
        self.s = size.size_trade(the_plan(), cfg(), today=TODAY)

    def test_config_example_is_the_contract(self):
        self.assertEqual(cfg(), CONFIG_KEYS)

    def test_73_shares_bound_by_the_max_loss_with_costs(self):
        s = self.s
        self.assertEqual((s["qty"], s["bound_by"], s["refusal"]), (73, "max loss", None))
        # by hand: 73 x 12.45 = 908.85; costs at the stop: brokerage 40, STT 22, NSE 5.48, GST 8.22,
        # SEBI 0.18, stamp 3 = 78.88; 908.85 + 78.88 = 987.73. 74 shares would be 921.30 + 78.96 = 1,000.26
        self.assertEqual((s["costs_at_stop"], s["max_loss"]), (78.88, 987.73))
        self.assertEqual((s["costs_at_target"], s["gain_at_target"]), (79.94, 828.91))
        self.assertEqual(s["value"], 89629.4)
        self.assertGreater(74 * 12.45 + size.costs_at(74, 1227.8, 1215.35), 1000)
        self.assertEqual([(l["name"], l["shares"]) for l in s["limits"]],
                         [("max loss", 73), ("position cap", 122), ("max order", 162), ("cash", 146)])
        self.assertEqual((s["qty"], s["costs_at_stop"], s["max_loss"]), (EX.QTY, EX.COSTS_AT_STOP, EX.MAX_LOSS))

    def test_the_bracket_order(self):
        o = size.bracket_order(self.s)
        self.assertEqual({k: o[k] for k in ("symbol", "exchange", "product", "side", "qty", "type", "time_in_force",
                                            "order_class", "take_profit_limit_price", "stop_loss_stop_price")},
                         {"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "73",
                          "type": "market", "time_in_force": "day", "order_class": "bracket",
                          "take_profit_limit_price": "1240.25", "stop_loss_stop_price": "1215.35"})
        self.assertEqual(o["plan"]["costs_at_stop"], 78.88)
        self.assertIn("Rs 1,000 max loss per trade", o["why"])

    def test_a_limit_order_rounds_to_the_tick(self):
        s = size.size_trade(the_plan(), cfg(), limit=1227.82, today=TODAY)
        self.assertEqual(s["entry"], 1227.8)
        o = size.bracket_order(s)
        self.assertEqual((o["type"], o["limit_price"]), ("limit", "1227.80"))
        # a limit above the entry shrinks the reward under the risk: refused, not resized
        self.assertIn("reward:risk 0.97", size.size_trade(the_plan(), cfg(), limit=1228.0, today=TODAY)["refusal"])

    def test_cli_writes_one_bracket_order(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "orders.json")
        code, text, err = run(["--plan", PLAN, "--config", CFG, "--now", NOW, "--portfolio", "/nonexistent",
                               "--write", out])
        self.assertEqual(code, 0, err)
        for line in ("max loss      Rs 1,000 incl. costs: 73 x 12.45 + Rs 78.88 costs = Rs 987.73",
                     "position cap  75% of Rs 2,00,000 = Rs 1,50,000 / 1227.80",
                     "Size: 73 shares of RELIANCE = Rs 89,629.40 at 1227.80 (MIS, intraday).",
                     "Costs, round trip (Zerodha): Rs 78.88 if it exits at the stop, Rs 79.94 at the target.",
                     "Max loss at the stop: 73 x 12.45 + Rs 78.88 costs = Rs 987.73.",
                     "buy 73 RELIANCE on NSE, MIS, market, day, take-profit 1240.25, stop-loss 1215.35",
                     "Flat by 15:15 IST", "not financial advice"):
            self.assertIn(line, text)
        with open(out) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["created_by"], doc["status"], doc["paper"], len(doc["orders"])),
                         ("bharat-budget", "proposed", True, 1))
        self.assertEqual(doc["created_at"], "2026-10-19T04:21:00Z")


class Rules(unittest.TestCase):
    def test_zero_shares_is_a_plain_refusal(self):
        s = size.size_trade(the_plan(), cfg(max_loss_per_trade_inr=12), today=TODAY)
        self.assertEqual(s["qty"], 0)
        self.assertIn("more than your Rs 12 max loss per trade", s["refusal"])
        self.assertEqual(size.size_trade(the_plan(), cfg(max_loss_per_trade_inr=30), today=TODAY)["qty"], 2)
        self.assertIsNone(size.bracket_order(s))
        code, text, _ = run(["--plan", PLAN, "--config", CFG, "--now", NOW, "--budget", "200000",
                             "--portfolio", "/nonexistent", "--write", os.path.join(tempfile.mkdtemp(), "o.json")])
        self.assertEqual(code, 0)

    def test_each_limit_can_bind(self):
        self.assertEqual(size.size_trade(the_plan(), cfg(budget=100000), today=TODAY)["bound_by"], "position cap")
        self.assertEqual(size.size_trade(the_plan(), cfg(max_order_inr=50000), today=TODAY)["bound_by"], "max order")
        s = size.size_trade(the_plan(), cfg(max_position_pct=100, cash_buffer_pct=60), today=TODAY)
        self.assertEqual((s["bound_by"], s["qty"]), ("cash", 65))   # 80,000 / 1227.80

    def test_mis_leverage_widens_only_the_cash_limit(self):
        s = size.size_trade(the_plan(), cfg(budget=40000, max_position_pct=500, mis_leverage=5), today=TODAY)
        self.assertEqual([(l["name"], l["shares"]) for l in s["limits"]][3], ("cash", 146))   # 36,000 x 5
        self.assertEqual((s["qty"], s["bound_by"]), (73, "max loss"))
        for bad in (9, 0.5, "lots"):
            with self.assertRaises(size.SizeError) as cm:
                size.size_trade(the_plan(), cfg(mis_leverage=bad), today=TODAY)
            self.assertIn("between 1 and 5", str(cm.exception))

    def test_a_fresh_higher_price_means_a_bigger_risk(self):
        s = size.size_trade(the_plan(), cfg(), price=1230.0, today=TODAY)
        self.assertEqual((s["entry"], s["entry_from"], s["risk_per_share"]), (1230.0, "price", 14.65))
        self.assertLess(s["qty"], 73)
        self.assertEqual(size.size_trade(the_plan(), cfg(), price=1225.0, today=TODAY)["entry"], 1227.8)

    def test_prices_file_is_used_only_when_fresh(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "prices.json")
        with open(p, "w") as fh:
            json.dump({"prices": {"RELIANCE": 1230.0}, "as_of": "2026-10-19T04:20:00Z"}, fh)
        code, text, _ = run(["--plan", PLAN, "--config", CFG, "--now", NOW, "--prices", p,
                             "--portfolio", "/nonexistent"])
        self.assertIn("is above the plan's entry 1227.80", text)
        code, text, _ = run(["--plan", PLAN, "--config", CFG, "--now", "2026-10-19 10:30", "--prices", p,
                             "--portfolio", "/nonexistent"])
        self.assertIn("not used (older than 15 minutes)", text)

    def test_the_portfolio_cash_caps_the_size(self):
        s = size.size_trade(the_plan(), cfg(), cash=50000, today=TODAY)
        self.assertEqual((s["bound_by"], s["qty"]), ("cash", 24))      # (50,000 - 20,000) / 1227.80

    def test_bad_plans(self):
        cases = [(dict(side="sell"), "long (buy)"), (dict(date="2026-10-21"), "today is 2026-10-19"),
                 (dict(stop=None), "positive stop"), (dict(stop=1230.0), "not below the entry"),
                 (dict(target=1220.0), "not above the entry"), (dict(symbol=""), "no symbol")]
        for over, words in cases:
            with self.assertRaises(size.SizeError, msg=over) as cm:
                size.size_trade(the_plan(**over), cfg(), today=TODAY)
            self.assertIn(words, str(cm.exception))
        with self.assertRaises(size.SizeError):
            size.size_trade(the_plan(), cfg(blocked=["reliance"]), today=TODAY)
        with self.assertRaises(size.SizeError):
            size.size_trade(the_plan(), cfg(budget=None), today=TODAY)

    def test_reward_risk_and_minimum_order(self):
        s = size.size_trade(the_plan(target=1235.0), cfg(), today=TODAY)
        self.assertIn("reward:risk 0.58", s["refusal"])
        s = size.size_trade(the_plan(), cfg(min_order_inr=100000), today=TODAY)
        self.assertIn("under your Rs 1,00,000 minimum order", s["refusal"])

    def test_missing_plan(self):
        code, _, err = run(["--plan", "/nonexistent.json", "--config", CFG])
        self.assertEqual(code, 1)
        self.assertIn("run bharat-exit first", err)


if __name__ == "__main__":
    unittest.main()
