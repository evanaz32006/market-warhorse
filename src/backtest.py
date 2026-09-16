"""Portfolio backtest with realistic transaction costs — REPORT ONLY.

Every metric this project has produced so far is a CROSS-SECTIONAL average of independent one-shot
bets: information coefficients, hit rates, decile spreads. None of them is an account. They answer
"is the ranking informative?" — a real question, but not the same question as "what would have
happened to the money?". A ranking can carry genuine information and still lose after costs, if the
edge is thinner than the spread or the turnover it demands is too high.

So this simulates an actual book: buy the top N, hold H sessions, rebalance, pay to trade, compound.

Three disciplines carried over from the rest of the codebase:
  * NO LOOKAHEAD. Fills happen at the NEXT session's open, never at the close that produced the
    score. Date D's close is an input to date D's score, so filling at it means trading on a price
    you needed in order to decide — the same class of error as a filed-date leak.
  * NEVER INVENT DATA. A holding whose price series ends mid-hold is liquidated at its last real
    close and flagged, not silently dropped. Dropping it is the optimistic assumption, and quietly
    optimistic is precisely what a backtest must never be.
  * SAY WHAT IS WRONG WITH THE NUMBER. The universe is today's index membership projected backwards,
    so survivorship bias inflates every return here. That is stamped on every output row rather than
    buried in a footnote.
"""

import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src import evaluation, research
from src.config import PARAMS

TRADING_DAYS = PARAMS["trading_days_per_year"]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Cost model
# ---------------------------------------------------------------------------

def dollar_adv(panel, ticker, idx, window=None):
    """Average dollar volume over the trailing `window` sessions ending at idx (inclusive).

    Computed here from price history rather than read from a stored feature, deliberately: liquidity
    is a TRADEABILITY filter, not a scoring input, so it does not belong in the snapshot schema —
    and adding it there would have forced a full re-backfill for no analytical gain."""
    window = window or PARAMS["backtest_adv_window"]
    v = panel.volumes.get(ticker)
    c = panel.closes.get(ticker)
    if v is None or c is None or idx is None:
        return None
    lo = max(0, idx - window + 1)
    vol, px = v[lo:idx + 1], c[lo:idx + 1]
    if len(vol) == 0:
        return None
    dv = float(np.mean(vol * px))
    return dv if dv > 0 else None


def spread_bps(adv_dollars):
    """Half-spread proxy in basis points, widening as liquidity falls.

    A mega-cap trades at ~1bp; a thin small cap can be 50bp+. Modelled as
    base + coef / sqrt(ADV in $M), clipped to a floor and a cap. UNKNOWN liquidity returns the CAP,
    not the floor — when the cost cannot be estimated, the pessimistic assumption is the honest one."""
    if not adv_dollars or adv_dollars <= 0:
        return PARAMS["backtest_spread_max_bps"]
    adv_musd = adv_dollars / 1e6
    raw = (PARAMS["backtest_spread_base_bps"]
           + PARAMS["backtest_spread_liquidity_coef"] / math.sqrt(adv_musd))
    return float(min(max(raw, PARAMS["backtest_spread_min_bps"]), PARAMS["backtest_spread_max_bps"]))


def impact_bps(trade_dollars, adv_dollars):
    """Market impact via the square-root participation law: impact ~ coef * sqrt(participation).

    Participation is capped because beyond some share of a day's volume the honest model is not
    "an expensive fill" but "this trade does not happen at all"."""
    if not adv_dollars or adv_dollars <= 0 or trade_dollars <= 0:
        return PARAMS["backtest_spread_max_bps"]
    part = min(trade_dollars / adv_dollars, PARAMS["backtest_participation_cap"])
    return float(PARAMS["backtest_impact_coef_bps"] * math.sqrt(part))


def one_way_cost_bps(trade_dollars, adv_dollars):
    """Total one-way cost: half the spread crossed, plus impact. Charged on entry AND on exit."""
    return spread_bps(adv_dollars) / 2.0 + impact_bps(trade_dollars, adv_dollars)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def first_invested_index(equity, tol=1e-9):
    """Index of the first session on which the curve actually moves, i.e. holds a position.

    THE CASH-PERIOD PROBLEM this exists to expose (found 2026-09-16). score_120d cannot be computed
    until a name has ~252 sessions of trailing history, and `fetch_period=2y` means price history
    starts 2024-06 — so no row carried a 120-day score before 2025-04-09, and the first REBALANCE
    into real positions came later still. The backtest nonetheless began its equity curve at
    2024-06-24 and reported statistics over all 559 sessions, of which the strategy spent 200-240
    (36-43%) holding nothing at all.

    Those flat sessions are not neutral. They contribute ZERO-VARIANCE returns, which deflate the
    Sharpe denominator, and they let the strategy sit out a benchmark drawdown it was never exposed
    to. Measured across the nine configs: as reported, 9 of 9 had a shallower drawdown than SPY and
    7 of 9 a higher Sharpe; over the INVESTED period only, 4 of 9 and 2 of 9. SPY's -18.8% max
    drawdown happened almost entirely while the strategy held cash, against -8.9% once it was
    actually in the market.

    Both windows are now reported, because they answer different questions honestly:
      * the full window says what a person starting in 2024-06 would have experienced, startup
        artefact included;
      * the invested window is the only one that describes THE MODEL, and it is the one whose
        Sharpe and drawdown may be compared to a fully-invested benchmark.
    """
    eq = np.asarray(equity, dtype=np.float64)
    if len(eq) < 2:
        return 0
    moved = np.flatnonzero(np.abs(np.diff(eq)) > tol)
    return int(moved[0] + 1) if len(moved) else int(len(eq))


def equity_metrics(equity, risk_free=None):
    """CAGR, annualized Sharpe, max drawdown and volatility from one equity curve."""
    risk_free = PARAMS["backtest_risk_free_rate"] if risk_free is None else risk_free
    eq = np.asarray(equity, dtype=np.float64)
    if len(eq) < 2 or eq[0] <= 0:
        return {"cagr": None, "sharpe": None, "max_drawdown_pct": None,
                "volatility_annual": None, "total_return": None, "n_sessions": int(len(eq))}
    rets = eq[1:] / eq[:-1] - 1.0
    years = len(eq) / float(TRADING_DAYS)
    total = eq[-1] / eq[0] - 1.0
    cagr = (eq[-1] / eq[0]) ** (1.0 / years) - 1.0 if years > 0 else None
    sd = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    excess = float(np.mean(rets)) - risk_free / TRADING_DAYS
    sharpe = (excess / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else None
    peak = np.maximum.accumulate(eq)
    dd = float(np.min(eq / peak - 1.0)) * 100.0
    return {"cagr": cagr, "sharpe": sharpe, "max_drawdown_pct": dd,
            "volatility_annual": sd * math.sqrt(TRADING_DAYS),
            "total_return": total, "n_sessions": int(len(eq))}


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------

def _price_at(panel, ticker, date, field="close"):
    """(price, index) on an exact date, or (None, None). Never interpolates a missing session."""
    idx = panel.date_idx.get(ticker, {}).get(date)
    if idx is None:
        return None, None
    arr = panel.opens.get(ticker) if field == "open" else panel.closes.get(ticker)
    if arr is None or idx >= len(arr):
        return None, None
    px = float(arr[idx])
    return (px if px > 0 else None), idx


def _last_price_on_or_before(panel, ticker, date):
    """Final real close at or before `date`.

    This is what a holding is worth when its series simply stops — a delisting, an acquisition, or a
    data gap. Realizing it at a real historical price is the only honest option: assuming it still
    trades would invent data, and dropping it would quietly assume it was worth whatever the rest of
    the book was worth."""
    idx_map = panel.date_idx.get(ticker)
    c = panel.closes.get(ticker)
    if not idx_map or c is None:
        return None
    usable = [i for d, i in idx_map.items() if d <= date]
    if not usable:
        return None
    px = float(c[max(usable)])
    return px if px > 0 else None


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------

def run_single_backtest(panel, rebalance_dates, top_n, hold_days, score_col,
                        charge_costs=True, side="long", exclude=frozenset(), min_adv=None):
    """Simulate one (top_n, hold_days) configuration; return metrics, the daily curve, diagnostics.

    side="long" holds the top N by score. side="short" holds the BOTTOM N and is used only to build
    the long-short comparison leg — not a book anyone here intends to trade."""
    calendar = panel.calendar
    frame = panel.frame
    by_date = {d: g for d, g in frame.groupby("run_date")}
    rebalance_dates = set(rebalance_dates)

    cash = float(PARAMS["backtest_initial_equity"])
    holdings = {}
    curve_dates, curve_equity = [], []
    turnover_notional, total_cost_paid, n_rebalances = 0.0, 0.0, 0
    liquidated_missing, suspicious = [], []
    prev_close_px = {}

    for i, d in enumerate(calendar):
        # ---- decide on date d, FILL on d+1's open (never on d's own close) ----
        if d in rebalance_dates and i + 1 < len(calendar):
            nxt = calendar[i + 1]
            sub = by_date.get(d)
            if sub is not None and len(sub):
                clean = sub[~sub.apply(evaluation.has_stale_fundamentals, axis=1)]
                clean = clean[clean[score_col].notna()]
                if exclude:
                    clean = clean[~clean["ticker"].isin(exclude)]
                if min_adv is not None and len(clean):
                    keep = []
                    for t in clean["ticker"]:
                        _px, idx = _price_at(panel, t, d, "close")
                        adv = dollar_adv(panel, t, idx)
                        keep.append(adv is not None and adv >= min_adv)
                    clean = clean[np.asarray(keep, dtype=bool)]
                if len(clean):
                    ranked = clean.sort_values(score_col, ascending=(side == "short"))
                    target = list(ranked["ticker"].head(top_n))

                    # value the existing book at the fill session's open, then rotate into the target
                    book = cash
                    for t, sh in holdings.items():
                        px, _ = _price_at(panel, t, nxt, "open")
                        if px is None:
                            px = _last_price_on_or_before(panel, t, nxt)
                            if px is None:
                                continue
                            liquidated_missing.append((nxt, t))
                        book += sh * px

                    for t, sh in holdings.items():
                        px, idx = _price_at(panel, t, nxt, "open")
                        if px is None:
                            px, idx = _last_price_on_or_before(panel, t, nxt), None
                        if px is None:
                            continue
                        notional = sh * px
                        turnover_notional += notional
                        if charge_costs:
                            adv = dollar_adv(panel, t, idx) if idx is not None else None
                            total_cost_paid += notional * one_way_cost_bps(notional, adv) / 1e4
                            book -= notional * one_way_cost_bps(notional, adv) / 1e4

                    holdings = {}
                    fillable = [t for t in target if _price_at(panel, t, nxt, "open")[0] is not None]
                    if fillable:
                        per = book / len(fillable)
                        for t in fillable:
                            px, idx = _price_at(panel, t, nxt, "open")
                            cost = 0.0
                            if charge_costs:
                                adv = dollar_adv(panel, t, idx)
                                cost = per * one_way_cost_bps(per, adv) / 1e4
                            holdings[t] = (per - cost) / px
                            turnover_notional += per
                            total_cost_paid += cost
                        cash = 0.0
                    else:
                        cash = book
                    n_rebalances += 1

        # ---- mark to market at today's close ----
        val = cash
        for t, sh in holdings.items():
            px, _ = _price_at(panel, t, d, "close")
            if px is None:
                px = _last_price_on_or_before(panel, t, d)
                if px is None:
                    continue
            # A >50% one-day move with no corporate action is almost certainly an unadjusted split
            # leaking into the cache: new bars arrive adjusted while cached pre-split rows are not
            # re-adjusted. Flagged rather than silently compounded into the curve.
            prev = prev_close_px.get(t)
            if prev and abs(px / prev - 1.0) * 100.0 > PARAMS["backtest_suspicious_return_pct"]:
                suspicious.append((d, t, prev, px))
            prev_close_px[t] = px
            val += sh * px
        if val > 0:
            curve_dates.append(d)
            curve_equity.append(val)

    m = equity_metrics(curve_equity)
    years = max(len(curve_equity) / float(TRADING_DAYS), 1e-9)
    avg_equity = float(np.mean(curve_equity)) if curve_equity else 1.0
    m.update({
        "top_n": top_n, "hold_days": hold_days, "side": side, "costs_charged": charge_costs,
        "n_rebalances": n_rebalances,
        "turnover_annual": (turnover_notional / avg_equity) / years if avg_equity else None,
        "total_cost_paid": total_cost_paid,
        "cost_drag_pct_of_avg_equity": 100.0 * total_cost_paid / avg_equity if avg_equity else None,
        "n_liquidated_missing": len(liquidated_missing),
        "n_suspicious_moves": len(suspicious),
        "start_date": curve_dates[0] if curve_dates else None,
        "end_date": curve_dates[-1] if curve_dates else None,
    })
    return m, curve_dates, curve_equity, {"liquidated": liquidated_missing, "suspicious": suspicious}


def buy_and_hold_curve(panel, ticker, dates, initial=None):
    """A one-position buy-and-hold curve on the SAME session grid — the SPY benchmark leg.

    Built on the strategy's own date list so the comparison is like-for-like: an equity curve
    measured over a different window is not a benchmark, it is a different experiment."""
    initial = float(PARAMS["backtest_initial_equity"] if initial is None else initial)
    px0, out = None, []
    for d in dates:
        px, _ = _price_at(panel, ticker, d, "close")
        if px is None:
            out.append(out[-1] if out else initial)
            continue
        if px0 is None:
            px0 = px
        out.append(initial * px / px0)
    return out


def rebalance_schedule(calendar, panel_dates, hold_days):
    """Every hold_days-th session that actually carries a scored cross-section.

    Anchored to the trading calendar rather than to calendar days, so a holiday week does not
    silently shorten a holding period."""
    scored = set(panel_dates)
    usable = [d for d in calendar if d in scored]
    return usable[::hold_days]


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------

def _etf_tickers(panel):
    """Benchmark ETFs present in the panel. They are scored like any other row but are not holdings -
    a top-N screen would otherwise happily buy SPY because it ranked well against itself."""
    return {t for t, b in panel.benchmark_of.items() if t == b} | set(panel.benchmark_of.values())


def run_portfolio_backtest(db_path=None, model_version=None, output_dir=None,
                           top_ns=None, hold_days_list=None, score_col=None):
    """Sweep (top_n x hold_days), long and long-short, with and without costs. REPORT ONLY.

    Answers "how many positions, held how long" empirically instead of by assumption, and - the part
    no existing metric covers - whether the edge survives the cost of capturing it."""
    from src import storage
    db_path = db_path or storage.DEFAULT_DB_PATH
    model_version = model_version or PARAMS["model_version"]
    top_ns = top_ns or PARAMS["backtest_top_n"]
    hold_days_list = hold_days_list or PARAMS["backtest_hold_days"]
    score_col = score_col or PARAMS["backtest_score_column"]

    panel = research.load_panel(db_path, model_version, extra_columns=[score_col])
    if panel is None:
        print(f"[backtest] no snapshots for {model_version}")
        return pd.DataFrame()
    if score_col not in panel.frame.columns:
        raise KeyError(f"score column {score_col!r} absent from the panel; have "
                       f"{sorted(c for c in panel.frame.columns if c.startswith('score_'))}")

    exclude = _etf_tickers(panel)
    min_adv = PARAMS["min_dollar_volume_20d"] if PARAMS["backtest_exclude_illiquid"] else None
    panel_dates = sorted(panel.frame["run_date"].unique())
    bench = PARAMS["calendar_ticker"]

    rows, curves = [], {}
    for hold in hold_days_list:
        sched = rebalance_schedule(panel.calendar, panel_dates, hold)
        for n in top_ns:
            for charge in (True, False):
                m, cd, ce, diag = run_single_backtest(
                    panel, sched, top_n=n, hold_days=hold, score_col=score_col,
                    charge_costs=charge, side="long", exclude=exclude, min_adv=min_adv)
                if not ce:
                    continue
                bench_curve = buy_and_hold_curve(panel, bench, cd)
                bm = equity_metrics(bench_curve)
                # The apples-to-apples comparison. Both sides are cut to the sessions on which the
                # strategy actually held something, because comparing a part-time strategy's risk
                # against a full-time benchmark's over the same calendar credits the strategy for a
                # drawdown it was in cash for. See first_invested_index.
                fi = first_invested_index(ce)
                inv = equity_metrics(ce[fi:]) if fi < len(ce) - 1 else {}
                bm_inv = (equity_metrics(bench_curve[fi:])
                          if fi < len(bench_curve) - 1 else {})
                m.update({
                    "model_version": model_version, "score_column": score_col, "strategy": "long_only",
                    "benchmark": bench,
                    "benchmark_cagr": bm["cagr"], "benchmark_total_return": bm["total_return"],
                    "benchmark_sharpe": bm["sharpe"], "benchmark_max_drawdown_pct": bm["max_drawdown_pct"],
                    # --- invested-period-only, the numbers that describe the MODEL ---
                    "n_sessions_in_cash": fi,
                    "pct_of_window_in_cash": round(100.0 * fi / len(ce), 1) if len(ce) else None,
                    "first_invested_date": cd[fi] if fi < len(cd) else None,
                    "invested_cagr": inv.get("cagr"),
                    "invested_sharpe": inv.get("sharpe"),
                    "invested_max_drawdown_pct": inv.get("max_drawdown_pct"),
                    "invested_volatility_annual": inv.get("volatility_annual"),
                    "invested_n_sessions": inv.get("n_sessions"),
                    "benchmark_invested_cagr": bm_inv.get("cagr"),
                    "benchmark_invested_sharpe": bm_inv.get("sharpe"),
                    "benchmark_invested_max_drawdown_pct": bm_inv.get("max_drawdown_pct"),
                    # How many genuinely independent holding periods the row rests on. 559 SESSIONS
                    # reads like 2.2 years of evidence; at a 120-day horizon the invested window is
                    # about 2.7 non-overlapping periods, and that is the honest sample size.
                    "invested_independent_periods": (
                        round(inv["n_sessions"] / float(hold), 1)
                        if inv.get("n_sessions") else None),
                    "excess_total_return_vs_benchmark": (
                        (m["total_return"] - bm["total_return"])
                        if (m["total_return"] is not None and bm["total_return"] is not None) else None),
                    # The universe is TODAY's index membership projected backwards. Names that were
                    # delisted or demoted are simply absent, which inflates every return here. Stamped
                    # on the row itself so a CAGR can never be quoted without it.
                    "survivorship_biased": True,
                    "survivorship_bias_direction": "inflates returns (dead/demoted names absent)",
                    "generated_at": _now_iso(),
                })
                rows.append(m)
                if charge:
                    curves[f"long_n{n}_h{hold}"] = (cd, ce)
                    curves.setdefault("benchmark_" + bench, (cd, bench_curve))
                # Print the INVESTED figures next to the full-window ones. The full-window Sharpe
                # and drawdown flatter the strategy in proportion to how long it sat in cash, so
                # showing only those is how "40% less drawdown than SPY" got believed.
                _f = lambda v, sfx="": "n/a" if v is None else ("%.2f%s" % (v, sfx))
                print(f"[backtest] long n={n:<3d} hold={hold:<4d} costs={str(charge):<5s} "
                      f"CAGR={m['cagr']:+.1%} Sharpe={_f(m['sharpe'])} "
                      f"maxDD={m['max_drawdown_pct']:.1f}% turn={m['turnover_annual']:.1f}x", flush=True)
                if m.get("n_sessions_in_cash"):
                    print(f"[backtest]   ^ {m['n_sessions_in_cash']} of {m['n_sessions']} sessions "
                          f"({m['pct_of_window_in_cash']}%) held CASH (no score yet). Invested-only: "
                          f"CAGR={0 if m['invested_cagr'] is None else m['invested_cagr']:+.1%} "
                          f"Sharpe={_f(m['invested_sharpe'])} "
                          f"maxDD={_f(m['invested_max_drawdown_pct'], '%')} vs benchmark "
                          f"Sharpe={_f(m['benchmark_invested_sharpe'])} "
                          f"maxDD={_f(m['benchmark_invested_max_drawdown_pct'], '%')}; "
                          f"~{m['invested_independent_periods']} independent holding periods",
                          flush=True)

            # long-short: top decile long vs bottom decile short, reported for comparison only
            ls_long, _, ce_l, _ = run_single_backtest(
                panel, sched, top_n=n, hold_days=hold, score_col=score_col,
                charge_costs=True, side="long", exclude=exclude, min_adv=min_adv)
            ls_short, _, ce_s, _ = run_single_backtest(
                panel, sched, top_n=n, hold_days=hold, score_col=score_col,
                charge_costs=True, side="short", exclude=exclude, min_adv=min_adv)
            if ce_l and ce_s and len(ce_l) == len(ce_s) and len(ce_l) > 1:
                # Dollar-neutral: half the capital long the top names, half SHORT the bottom names.
                # The short leg must COMPOUND at the negative of the bottom basket's daily return.
                # Mirroring its equity curve around its starting value (2*start - s) is a linear
                # approximation that is only right for tiny moves and drifts badly over two years -
                # it would understate the short leg's contribution in exactly the volatile periods
                # where a long-short book is supposed to earn its keep.
                combo = [float(PARAMS["backtest_initial_equity"])]
                for k in range(1, len(ce_l)):
                    r_long = ce_l[k] / ce_l[k - 1] - 1.0
                    r_short_basket = ce_s[k] / ce_s[k - 1] - 1.0
                    r_combo = 0.5 * r_long + 0.5 * (-r_short_basket)
                    combo.append(combo[-1] * (1.0 + r_combo))
                cm = equity_metrics(combo)
                cm.update({"model_version": model_version, "score_column": score_col,
                           "strategy": "long_short", "top_n": n, "hold_days": hold,
                           "side": "long_short", "costs_charged": True,
                           "survivorship_biased": True,
                           "survivorship_bias_direction": "inflates returns (dead/demoted names absent)",
                           "generated_at": _now_iso()})
                rows.append(cm)

    df = pd.DataFrame(rows)
    out = research._output_dir(output_dir)
    path = os.path.join(out, "backtest_sweep.csv")
    df.to_csv(path, index=False)

    if curves:
        longest = max(len(v[0]) for v in curves.values())
        eq = pd.DataFrame({"date": max((v[0] for v in curves.values()), key=len)})
        for name, (cd, ce) in curves.items():
            eq[name] = pd.Series(ce) if len(ce) == longest else pd.Series(ce).reindex(range(longest))
        eq.to_csv(os.path.join(out, "backtest_equity_curves.csv"), index=False)

    print(f"[backtest] {len(df)} configurations -> {path}")
    return df
