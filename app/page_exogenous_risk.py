from __future__ import annotations

import numpy as np
import pandas as pd

from app.risk_system_sources import (
    align_weekly,
    garch_like_vol,
    json_series,
    rolling_std,
    stale_weeks,
    to_weekly_prices,
    weekly_fred,
)


def compute_exogenous_risk(period_weeks: int = 1) -> dict:
    period_weeks = max(1, min(int(period_weeks), 26))
    y_tickers = ["^VIX", "^VVIX", "^MOVE", "^VIX3M", "DX-Y.NYB", "VTI"]
    prices = to_weekly_prices(y_tickers).tail(575)

    vix = prices["^VIX"]
    vvix = prices["^VVIX"]
    move = prices["^MOVE"]
    vix3m = prices["^VIX3M"]
    dxy = prices["DX-Y.NYB"]
    vti_ret = prices["VTI"].pct_change()

    hy = weekly_fred("BAMLH0A0HYM2")
    ted_raw = weekly_fred("TEDRATE")
    ted_label = "TED Spread"
    if stale_weeks(ted_raw) > 26:
        sofr = weekly_fred("SOFR")
        dtb3 = weekly_fred("DTB3")
        ted_raw = (sofr - dtb3).dropna()
        ted_label = "TED Spread Proxy"

    anchor = vix.index
    exo_df = pd.DataFrame(index=anchor)
    exo_df["vix"] = vix.reindex(anchor)
    exo_df["vvix"] = vvix.reindex(anchor)
    exo_df["move"] = move.reindex(anchor)
    exo_df["vix3m"] = vix3m.reindex(anchor)
    exo_df["dxy"] = dxy.reindex(anchor)
    exo_df["hy"] = hy.reindex(anchor).ffill()
    exo_df["ted"] = ted_raw.reindex(anchor).ffill()
    exo_df = exo_df.tail(575)

    vix = exo_df["vix"].dropna()
    latest_index = exo_df.index
    vvix = exo_df["vvix"].reindex(latest_index)
    move = exo_df["move"].reindex(latest_index)
    vix3m = exo_df["vix3m"].reindex(latest_index)
    dxy = exo_df["dxy"].reindex(latest_index)
    hy = exo_df["hy"].reindex(latest_index)
    ted = exo_df["ted"].reindex(latest_index)
    vti_ret = vti_ret.reindex(latest_index).fillna(0.0)

    term_str = vix3m - vix
    real_vol = rolling_std(vti_ret, 4, annualization=np.sqrt(52)) * 100
    ivr_spread = vix - real_vol
    garch_scaled = (garch_like_vol(vti_ret) * 100)
    garch_scaled = garch_scaled / max(garch_scaled.max(), 1e-9) * 40
    vix_scaled = vix / max(vix.max(), 1e-9) * 40
    divergence = vix_scaled - garch_scaled

    z_df = pd.concat([vix, move, hy, ted], axis=1).dropna()
    z = (z_df - z_df.mean()) / z_df.std(ddof=0)
    composite = z.mean(axis=1)
    crisis_thresh = float(composite.quantile(0.8))
    risk_off = composite > crisis_thresh
    q90_vix = float(vix.quantile(0.9))
    def pct_rank(series: pd.Series, val: float) -> float:
        s = series.dropna()
        return float((s <= val).mean() * 100) if not s.empty else np.nan

    def delta(series: pd.Series, periods: int) -> float:
        if len(series.dropna()) <= periods:
            return np.nan
        return float(series.iloc[-1] - series.iloc[-1 - periods])

    latest = latest_index[-1]
    latest_composite = composite.dropna().index[-1]
    recent_focus = [
        {
            "name": "VIX",
            "current": round(float(vix.loc[latest]), 2),
            "delta_1w": round(delta(vix, 1), 2),
            "delta_period": round(delta(vix, period_weeks), 2),
            "percentile": round(pct_rank(vix, float(vix.loc[latest])), 1),
        },
        {
            "name": "VVIX",
            "current": round(float(vvix.loc[latest]), 2),
            "delta_1w": round(delta(vvix, 1), 2),
            "delta_period": round(delta(vvix, period_weeks), 2),
            "percentile": round(pct_rank(vvix, float(vvix.loc[latest])), 1),
        },
        {
            "name": "MOVE",
            "current": round(float(move.loc[latest]), 2),
            "delta_1w": round(delta(move, 1), 2),
            "delta_period": round(delta(move, period_weeks), 2),
            "percentile": round(pct_rank(move, float(move.loc[latest])), 1),
        },
        {
            "name": "HY Spread",
            "current": round(float(hy.loc[latest]), 2),
            "delta_1w": round(delta(hy, 1), 2),
            "delta_period": round(delta(hy, period_weeks), 2),
            "percentile": round(pct_rank(hy, float(hy.loc[latest])), 1),
        },
        {
            "name": ted_label,
            "current": round(float(ted.loc[latest]), 2),
            "delta_1w": round(delta(ted, 1), 2),
            "delta_period": round(delta(ted, period_weeks), 2),
            "percentile": round(pct_rank(ted, float(ted.loc[latest])), 1),
        },
        {
            "name": "DXY",
            "current": round(float(dxy.loc[latest]), 2),
            "delta_1w": round(delta(dxy, 1), 2),
            "delta_period": round(delta(dxy, period_weeks), 2),
            "percentile": round(pct_rank(dxy, float(dxy.loc[latest])), 1),
        },
    ]

    signals = [
        {
            "name": "VIX",
            "cond": "> 90th pct",
            "val": round(float(vix.loc[latest]), 2),
            "thresh": round(q90_vix, 2),
            "fire": bool(vix.loc[latest] > q90_vix),
        },
        {
            "name": "MOVE",
            "cond": "> 80th pct",
            "val": round(float(move.loc[latest]), 2),
            "thresh": round(float(move.quantile(0.8)), 2),
            "fire": bool(move.loc[latest] > move.quantile(0.8)),
        },
        {
            "name": "HY Spread",
            "cond": "> 80th pct",
            "val": round(float(hy.loc[latest]), 2),
            "thresh": round(float(hy.quantile(0.8)), 2),
            "fire": bool(hy.loc[latest] > hy.quantile(0.8)),
        },
        {
            "name": "Composite Z",
            "cond": "> 80th pct",
            "val": round(float(composite.loc[latest_composite]), 3),
            "thresh": round(crisis_thresh, 3),
            "fire": bool(composite.loc[latest_composite] > crisis_thresh),
        },
    ]

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in latest_index],
        "stats": {
            "vix": round(float(vix.iloc[-1]), 1),
            "vvix": round(float(vvix.iloc[-1]), 1),
            "move": round(float(move.iloc[-1]), 1),
            "hy": round(float(hy.iloc[-1]), 1),
            "ted": round(float(ted.iloc[-1]), 1),
            "dxy": round(float(dxy.iloc[-1]), 2),
            "term_structure": round(float(term_str.iloc[-1]), 2),
            "impl_real": round(float(ivr_spread.iloc[-1]), 2),
        },
        "period_weeks": period_weeks,
        "latest_date": latest.strftime("%Y-%m-%d"),
        "ted_label": ted_label,
        "series": {
            "vix": json_series(vix, 2),
            "vvix": json_series(vvix, 2),
            "move": json_series(move, 2),
            "hy": json_series(hy, 2),
            "ted": json_series(ted, 2),
            "dxy": json_series(dxy, 2),
            "term_structure": json_series(term_str, 2),
            "impl_real": json_series(ivr_spread, 2),
            "garch_scaled": json_series(garch_scaled, 2),
            "vix_scaled": json_series(vix_scaled, 2),
            "divergence": json_series(divergence, 2),
            "composite": json_series(composite, 3),
        },
        "thresholds": {"vix_q90": round(q90_vix, 2), "composite_q80": round(crisis_thresh, 3)},
        "risk_off": [bool(x) for x in risk_off.reindex(latest_index, fill_value=False)],
        "recent_focus": recent_focus,
        "signals": signals,
    }
