#!/usr/bin/env python3
"""Position sizing for bharat-budget. Standard library only, no network.

Sizes ONE intraday NSE trade from trader/plan.json (written by bharat-exit)
to your budget and your max loss per trade, trading costs included, then
writes one bracket order (entry, stop-loss, take-profit) to
trader/orders.json. It never places anything: bharat-risk checks the order
and bharat-broker asks you yes or no.

    python3 size.py                                  # trader/plan.json + trader/config.json
    python3 size.py --write                          # write trader/orders.json
    python3 size.py --limit                          # a limit order at the plan's entry
    python3 size.py --limit 1228.00 --write          # a limit order at 1228.00
    python3 size.py --now "2026-10-19 09:51" --json  # pin the clock (IST)

How many shares. Whole shares only.

    shares = the smallest of
      max loss       the most shares where shares x risk a share + round-trip
                     costs at the stop <= max_loss_per_trade_inr
      position cap   budget x max_position_pct / entry
      max order      max_order_inr / entry
      cash           (budget minus the cash buffer) x mis_leverage / entry
                     (and no more than the cash in trader/portfolio.json, if you have one)

Costs are Zerodha's intraday equity charges (brokerage, STT, NSE transaction
and investor-protection charges, SEBI fee, GST, stamp duty), from india.py.
mis_leverage (default 1, at most 5) lets the cash limit use the broker's
intraday margin; it never raises the max loss or the position cap.

The entry it sizes at: a limit order's limit price; for a market order the
plan's entry, or the price in trader/prices.json if that is fresh (under 15
minutes old) and higher, because a price that ran up since the plan means a
bigger loss at the same stop. Zero shares (the stop is too far away for your
max loss) is a plain refusal: no order is written. So is a reward:risk under
min_reward_risk.
"""

import argparse
import datetime
import json
import math
import os
import sys

import india

DEFAULTS = {
    "budget": None,
    "cash_buffer_pct": 10,
    "max_position_pct": 75,
    "max_order_inr": 200000,
    "min_order_inr": 500,
    "max_loss_per_trade_inr": 1000,
    "max_daily_loss_inr": 3000,
    "max_trades_per_day": 3,
    "max_orders_per_day": 10,
    "min_reward_risk": 1.0,
    "max_cost_share": 0.25,
    "require_stop": True,
    "no_entries_before": "09:30",
    "no_entries_after": "14:45",
    "flat_by": "15:15",
    "mis_leverage": 1,
    "broker": "zerodha",
    "paper": True,
    "blocked": [],
    "allow_fno": False,
    "allow_margin": False,
    "allow_short": False,
}
MAX_LEVERAGE = 5      # SEBI's minimum intraday margin is 20 % of the trade's value
EPS = 1e-9
FRESH_MINUTES = 15
SEGMENT = "eq_intraday"
SETUP_WORDS = {"orb": "opening-range breakout", "flag": "flag", "bounce": "oversold bounce", "level": "level"}


class SizeError(Exception):
    pass


# ---------------------------------------------------------------- time (IST)

def to_local(utc):
    """Naive UTC -> naive IST."""
    return india.to_ist(utc.replace(tzinfo=datetime.timezone.utc)).replace(tzinfo=None)


def parse_now(text):
    """ISO time -> naive UTC. A time without an offset is taken as IST."""
    if not text:
        return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None)
    t = text.strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(t)
    except ValueError:
        raise SizeError("--now wants a time like \"2026-10-19 09:51\" (IST) or ...Z (UTC)")
    if dt.tzinfo is None:
        return india.ist_to_utc(dt).replace(tzinfo=None)
    return (dt - dt.utcoffset()).replace(tzinfo=None)


def parse_utc(text):
    """"2026-10-19T04:21:13Z" -> naive UTC, or None."""
    if not text:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)
    return dt


def utc_iso(now_utc=None):
    now_utc = now_utc or datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return now_utc.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- inputs

def read_json(path, what):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise SizeError("no %s at %s" % (what, path))
    except json.JSONDecodeError as e:
        raise SizeError("%s is not valid JSON: %s" % (path, e))


def load_config(path):
    cfg = dict(DEFAULTS)
    if path and os.path.exists(path):
        cfg.update(read_json(path, "config"))
    return cfg


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def price_time(doc, sym):
    """When this symbol's price is from: detail[sym].time, else .fetched, else the file's as_of."""
    det = ((doc or {}).get("detail") or {}).get(sym) or {}
    for key in ("time", "fetched"):
        t = parse_utc(det.get(key))
        if t:
            return t
    return parse_utc((doc or {}).get("as_of"))


def fresh_price(doc, sym, now_utc, minutes=FRESH_MINUTES):
    """(price, fetched_utc, fresh) for sym from a prices.json doc, or (None, None, False)."""
    if not isinstance(doc, dict):
        return None, None, False
    p = _f((doc.get("prices") or {}).get(sym))
    if p is None or p <= 0:
        return None, None, False
    t = price_time(doc, sym)
    if t is None:
        return p, None, False
    age = (now_utc - t).total_seconds()
    return p, t, -60 <= age <= minutes * 60


# ---------------------------------------------------------------- money helpers

def round_paisa(x):
    """Round to the paisa (half up)."""
    return math.floor(float(x) * 100 + 0.5 + EPS) / 100.0


def shares_for(inr, per_share):
    """Whole shares that fit in inr at per_share, in exact integer paise."""
    u, p = int(round(float(inr) * 100)), int(round(float(per_share) * 100))
    if p <= 0 or u <= 0:
        return 0
    return u // p


def costs_at(qty, buy, sell):
    """Round-trip charges for qty shares bought at buy and sold at sell (Rs)."""
    return india.round_trip(SEGMENT, qty, buy, sell)["total"] if qty > 0 else 0.0


def shares_after_costs(max_loss, risk, entry, stop):
    """The most whole shares whose loss at the stop, costs included, fits max_loss."""
    q = shares_for(max_loss, risk)
    while q > 0 and q * risk + costs_at(q, entry, stop) > max_loss + EPS:
        q -= 1
    return q


def _price(x):
    return "%.2f" % round_paisa(x)


def _num(x):
    x = round(float(x), 2)
    if abs(x - round(x)) < 0.005:
        return str(int(round(x)))
    return "%.2f" % x


def money(x):
    return india.inr(x)


# ---------------------------------------------------------------- sizing

def size_trade(plan, cfg, budget=None, limit=None, price=None, cash=None, today=None):
    """Pure function: one plan + your rules -> the sizing (a dict). qty may be 0.

    limit  the limit price for a limit order (None = market)
    price  a FRESH latest price; a market order is sized at the higher of it and the plan's entry
    cash   the cash in trader/portfolio.json, if there is one
    today  IST date (YYYY-MM-DD); a plan for another day is refused"""
    c = dict(DEFAULTS)
    c.update(cfg or {})
    if not isinstance(plan, dict):
        raise SizeError("the plan is not a JSON object")
    sym = str(plan.get("symbol") or "").strip().upper()
    if not sym:
        raise SizeError("the plan has no symbol (run bharat-exit)")
    side = str(plan.get("side") or "buy").strip().lower()
    if side != "buy":
        raise SizeError("this pack sizes long (buy) intraday trades only; the plan says %r" % side)
    if today and plan.get("date") and str(plan["date"]) != today:
        raise SizeError("the plan is for %s and today is %s (IST): make a new plan with bharat-exit"
                        % (plan["date"], today))
    entry_plan, stop, target = _f(plan.get("entry")), _f(plan.get("stop")), _f(plan.get("target"))
    for name, v in (("entry", entry_plan), ("stop", stop), ("target", target)):
        if v is None or v <= 0:
            raise SizeError("the plan needs a positive %s (run bharat-exit); a bracket order needs entry, "
                            "stop and target" % name)
    blocked = {str(b).upper() for b in (c.get("blocked") or [])}
    if sym in blocked:
        raise SizeError("%s is on your blocked list" % sym)

    budget = float(budget if budget is not None else (c.get("budget") or 0))
    if budget <= 0:
        raise SizeError("no budget: pass --budget or set \"budget\" in trader/config.json (in rupees)")
    buf_pct = float(c.get("cash_buffer_pct") or 0)
    if not 0 <= buf_pct < 100:
        raise SizeError("cash_buffer_pct must be between 0 and 100")
    lev = _f(c.get("mis_leverage"))
    if lev is None or not 1 <= lev <= MAX_LEVERAGE:
        raise SizeError("mis_leverage must be between 1 and %d (SEBI's intraday margin is at least 20 %%), not %r"
                        % (MAX_LEVERAGE, c.get("mis_leverage")))

    if limit is not None:
        ref, ref_from = india.tick_round(limit), "limit"
    elif price is not None and round_paisa(price) > round_paisa(entry_plan):
        ref, ref_from = round_paisa(price), "price"
    else:
        ref, ref_from = round_paisa(entry_plan), "plan"
    stop, target = round_paisa(stop), round_paisa(target)
    if stop >= ref:
        raise SizeError("the stop %s is not below the entry %s; a long trade needs its stop underneath"
                        % (_price(stop), _price(ref)))
    if target <= ref:
        raise SizeError("the target %s is not above the entry %s: the move has already happened. "
                        "Skip it or make a new plan with bharat-exit" % (_price(target), _price(ref)))
    risk_p = int(round((ref - stop) * 100))
    reward_p = int(round((target - ref) * 100))
    risk = risk_p / 100.0

    cash_buffer = round(budget * buf_pct / 100.0, 2)
    available = budget - cash_buffer
    cash_note = "(budget %s - %s buffer)" % (money(budget), money(cash_buffer))
    if cash is not None and cash - cash_buffer < available - 0.005:
        available = cash - cash_buffer
        cash_note = "(cash %s - %s buffer)" % (money(cash), money(cash_buffer))
    available = max(round(available, 2), 0.0)
    buying = round(available * lev, 2)
    if lev != 1:
        cash_note += " x %sx MIS" % _num(lev)

    limits = []
    max_loss = _f(c.get("max_loss_per_trade_inr"))
    if max_loss:
        q = shares_after_costs(max_loss, risk, ref, stop)
        limits.append({"name": "max loss", "inr": max_loss, "per": risk, "shares": q,
                       "how": "%s incl. costs: %d x %s + %s costs = %s" % (
                           money(max_loss), q, _price(risk), money(costs_at(q, ref, stop)),
                           money(q * risk + costs_at(q, ref, stop)))})
    cap_pct = _f(c.get("max_position_pct"))
    if cap_pct:
        cap = round(budget * cap_pct / 100.0, 2)
        limits.append({"name": "position cap", "inr": cap, "per": ref, "shares": shares_for(cap, ref),
                       "how": "%s%% of %s = %s / %s" % (_num(cap_pct), money(budget), money(cap), _price(ref))})
    max_order = _f(c.get("max_order_inr"))
    if max_order:
        limits.append({"name": "max order", "inr": max_order, "per": ref, "shares": shares_for(max_order, ref),
                       "how": "%s / %s" % (money(max_order), _price(ref))})
    limits.append({"name": "cash", "inr": buying, "per": ref, "shares": shares_for(buying, ref),
                   "how": "%s %s / %s" % (money(buying), cash_note, _price(ref))})

    qty = max(0, min(l["shares"] for l in limits))
    bound = [l["name"] for l in limits if l["shares"] == qty]
    for l in limits:
        l["binds"] = l["name"] == bound[0]
    value = round(qty * ref, 2)
    costs_stop = round(costs_at(qty, ref, stop), 2)
    costs_target = round(costs_at(qty, ref, target), 2)
    loss = round(qty * risk_p / 100.0 + costs_stop, 2)
    gain = round(qty * reward_p / 100.0 - costs_target, 2)
    refusal = None
    if qty == 0:
        if bound[0] == "max loss":
            refusal = ("one share risks %s (entry %s minus stop %s) plus %s costs, more than your %s max loss per "
                       "trade. No order. Skip this trade, or plan a closer stop with bharat-exit."
                       % (money(risk), _price(ref), _price(stop), money(costs_at(1, ref, stop)), money(max_loss)))
        else:
            refusal = ("one share of %s costs %s, more than your %s limit (%s). No order."
                       % (sym, money(ref), bound[0], limits[[l["name"] for l in limits].index(bound[0])]["how"]))
    elif _f(c.get("min_reward_risk")) and reward_p < _f(c["min_reward_risk"]) * risk_p - EPS:
        refusal = ("reward:risk %.2f (target %s, entry %s, stop %s) is under your minimum %s, so bharat-risk "
                   "would block it. No order. Skip it, or make a new plan with bharat-exit."
                   % (reward_p / float(risk_p), _price(target), _price(ref), _price(stop), _num(c["min_reward_risk"])))
    elif value < float(c.get("min_order_inr") or 0) - 0.005:
        refusal = ("%d share%s of %s is %s, under your %s minimum order. No order."
                   % (qty, "" if qty == 1 else "s", sym, money(value), money(c["min_order_inr"])))
    return {
        "symbol": sym, "side": "buy", "setup": plan.get("setup", ""), "date": plan.get("date"),
        "entry_time": plan.get("entry_time", ""), "entry_plan": round_paisa(entry_plan),
        "entry": ref, "entry_from": ref_from, "stop": stop, "target": target,
        "risk_per_share": risk, "reward_risk": round(reward_p / float(risk_p), 2),
        "stop_label": plan.get("stop_label", ""), "target_label": plan.get("target_label", ""),
        "budget": budget, "cash_buffer_pct": buf_pct, "cash_buffer": cash_buffer, "cash_available": available,
        "mis_leverage": lev, "max_loss_per_trade_inr": max_loss, "limits": limits, "qty": qty,
        "bound_by": bound[0], "value": value, "costs_at_stop": costs_stop, "costs_at_target": costs_target,
        "max_loss": loss, "gain_at_target": gain, "flat_by": plan.get("flat_by") or c.get("flat_by"),
        "order_type": "limit" if limit is not None else "market", "refusal": refusal,
    }


def bracket_order(s):
    """The one proposed order: an NSE intraday (MIS) buy with its stop-loss and take-profit."""
    if s["refusal"] or s["qty"] <= 0:
        return None
    o = {"symbol": s["symbol"], "exchange": "NSE", "product": "MIS", "side": "buy", "qty": str(int(s["qty"])),
         "type": s["order_type"], "time_in_force": "day"}
    if s["order_type"] == "limit":
        o["limit_price"] = _price(s["entry"])
    setup = SETUP_WORDS.get(s["setup"], s["setup"] or "intraday trade")
    why = ("%s on %s: %d shares, bound by your %s (%d x %s + %s costs = %s at the stop)"
           % (setup, s["symbol"], s["qty"],
              {"max loss": "%s max loss per trade" % money(s["max_loss_per_trade_inr"] or 0),
               "position cap": "position cap", "max order": "max order",
               "cash": "cash after the buffer"}[s["bound_by"]],
              s["qty"], _price(s["risk_per_share"]), money(s["costs_at_stop"]), money(s["max_loss"])))
    o.update({
        "order_class": "bracket",
        "take_profit_limit_price": _price(s["target"]),
        "stop_loss_stop_price": _price(s["stop"]),
        "why": why,
        "plan": {"entry": s["entry"], "stop": s["stop"], "target": s["target"],
                 "risk_per_share": s["risk_per_share"], "max_loss": s["max_loss"],
                 "costs_at_stop": s["costs_at_stop"], "costs_at_target": s["costs_at_target"],
                 "setup": s["setup"], "entry_time": s["entry_time"], "flat_by": s["flat_by"]},
    })
    return o


def plan_report(s, order, notes=()):
    lines = []
    setup = SETUP_WORDS.get(s["setup"], s["setup"] or "setup")
    lines.append("%s buy, %s, entry %s%s" % (s["symbol"], setup, _price(s["entry_plan"]),
                                            (" at " + s["entry_time"]) if s["entry_time"] else ""))
    lines.append("Stop %s%s. Target %s%s." % (_price(s["stop"]), (": " + s["stop_label"]) if s["stop_label"] else "",
                                             _price(s["target"]),
                                             (": " + s["target_label"]) if s["target_label"] else ""))
    for n in notes:
        lines.append(n)
    src = {"plan": "the plan's entry", "price": "the latest price, above the plan's entry",
           "limit": "your limit price"}[s["entry_from"]]
    lines.append("Sized at %s (%s). Risk %s a share (entry %s minus stop %s). Reward:risk %.2f."
                 % (_price(s["entry"]), src, _price(s["risk_per_share"]), _price(s["entry"]), _price(s["stop"]),
                    s["reward_risk"]))
    lines.append("")
    lines.append("Limits (whole shares; the smallest one wins):")
    for l in s["limits"]:
        lines.append("  %-13s %-62s %4d shares%s" % (l["name"], l["how"], l["shares"],
                                                      "  <- binds" if l["binds"] else ""))
    lines.append("")
    if order is None:
        lines.append("No order: " + s["refusal"])
        lines.append("Education and tooling, not financial advice.")
        return "\n".join(lines)
    lines.append("Size: %d shares of %s = %s at %s (MIS, intraday)." % (
        s["qty"], s["symbol"], money(s["value"]), _price(s["entry"])))
    lines.append("Costs, round trip (Zerodha): %s if it exits at the stop, %s at the target." % (
        money(s["costs_at_stop"]), money(s["costs_at_target"])))
    lines.append("Max loss at the stop: %d x %s + %s costs = %s. At the target, after costs: %s." % (
        s["qty"], _price(s["risk_per_share"]), money(s["costs_at_stop"]), money(s["max_loss"]),
        money(s["gain_at_target"])))
    lines.append("A stop is an order, not a promise: in a fast market or a band freeze it can fill below %s."
                 % _price(s["stop"]))
    lines.append("")
    lines.append("Proposed bracket order (nothing has been placed):")
    how = "limit %s" % order["limit_price"] if order["type"] == "limit" else "market"
    lines.append("  buy %s %s on NSE, MIS, %s, day, take-profit %s, stop-loss %s"
                 % (order["qty"], order["symbol"], how, order["take_profit_limit_price"],
                    order["stop_loss_stop_price"]))
    if s["flat_by"]:
        lines.append("Flat by %s IST: anything still open then gets closed (bharat-alerts rings, "
                     "bharat-broker flatten), before the broker's 15:20 square-off." % s["flat_by"])
    lines.append("")
    lines.append("Next: bharat-risk checks it, then bharat-broker asks you yes or no.")
    lines.append("Education and tooling, not financial advice.")
    return "\n".join(lines)


def write_orders(path, orders, cfg, source="", now_utc=None):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    doc = {
        "created_by": "bharat-budget",
        "created_at": utc_iso(now_utc),
        "status": "proposed",
        "paper": bool(cfg.get("paper", True)),
        "note": ("Proposals only. Nothing is placed until bharat-risk passes each order "
                 "and you say yes to it in the chat."),
        "source": source,
        "orders": orders,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------- main

def run_plan(a, cfg):
    now = parse_now(a.now)
    today = to_local(now).date().isoformat()
    plan = read_json(a.plan, "plan (run bharat-exit first)")
    limit = None
    if a.limit is not None:
        if a.limit == "plan":
            limit = _f((plan or {}).get("entry"))
        else:
            limit = _f(a.limit)
            if limit is None or limit <= 0:
                raise SizeError("--limit wants a price, like --limit 1228.00")
    sym = str((plan or {}).get("symbol") or "").upper()
    notes, price = [], None
    ppath = a.prices or ("trader/prices.json" if os.path.exists("trader/prices.json") else None)
    if ppath and limit is None and sym:
        pdoc = read_json(ppath, "prices")
        p, t, fresh = fresh_price(pdoc, sym, now)
        if p is not None and fresh:
            price = p
            if round_paisa(p) > round_paisa(_f(plan.get("entry")) or 0):
                notes.append("%s last %s (as of %s IST) is above the plan's entry %s, so the risk "
                             "is bigger: sized at %s." % (sym, _price(p), to_local(t).strftime("%H:%M"),
                                                          _price(plan.get("entry")), _price(p)))
        elif p is not None:
            notes.append("%s in %s is %s: not used (older than %d minutes). Sized at the plan's entry."
                         % (sym, ppath, ("from " + to_local(t).strftime("%Y-%m-%d %H:%M") + " IST")
                            if t else "undated", FRESH_MINUTES))
    cash = None
    if a.portfolio and os.path.exists(a.portfolio):
        pf = read_json(a.portfolio, "portfolio")
        cash = _f(pf.get("cash")) if isinstance(pf, dict) else None
    s = size_trade(plan, cfg, a.budget, limit, price, cash, today)
    order = bracket_order(s)
    if order and a.write:
        src = "trader/plan.json (%s %s %s)" % (s["symbol"], s["setup"] or "plan", s["date"] or today)
        write_orders(a.write, [order], cfg, src, now)
    if a.json:
        print(json.dumps({"sizing": s, "orders": [order] if order else [], "notes": notes}, indent=2))
    else:
        print(plan_report(s, order, notes))
        if order and a.write:
            print("Wrote 1 proposed bracket order to %s" % a.write)
    return 0 if order else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Size an intraday trade to your budget and max loss (bharat-budget).")
    ap.add_argument("--plan", default="trader/plan.json", help="the trade plan (default trader/plan.json)")
    ap.add_argument("--config", default="trader/config.json", help="rules (default trader/config.json)")
    ap.add_argument("--budget", type=float, help="override the budget in the config (Rs)")
    ap.add_argument("--limit", nargs="?", const="plan", metavar="PRICE",
                    help="a limit order instead of market, at the plan's entry or at PRICE")
    ap.add_argument("--prices", help="prices JSON (default trader/prices.json if it exists)")
    ap.add_argument("--portfolio", default="trader/portfolio.json",
                    help="your account; its cash caps the size if it exists")
    ap.add_argument("--now", help="pretend it is this IST time, e.g. \"2026-10-19 09:51\"")
    ap.add_argument("--write", nargs="?", const="trader/orders.json", metavar="PATH",
                    help="write the proposed order (default trader/orders.json)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the report")
    a = ap.parse_args(argv)
    try:
        return run_plan(a, load_config(a.config))
    except SizeError as e:
        print("size.py: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
