from __future__ import annotations

import numpy as np
import pandas as pd
from fear_and_greed.cnn import Fetcher

from app.risk_system_sources import json_multi, to_weekly_prices, to_weekly_returns, cov_to_corr


GLOBAL_MARKETS = {
    "china": ("China (CSI300)", "ASHR"),
    "japan": ("Japan (N225)", "EWJ"),
    "korea": ("Korea (KOSPI)", "EWY"),
    "europe": ("Europe (STOXX600)", "FEZ"),
    "pacific": ("Pacific ex-JP", "EPP"),
    "em": ("EM (MSCI EM)", "EEM"),
    "gold": ("Gold", "GLD"),
    "silver": ("Silver", "SLV"),
    "oil": ("Oil (WTI)", "USO"),
    "cash": ("Cash (T-Bill)", "BIL"),
}

US_ASSETS = {
    "spy": ("US Large Cap (SPY)", "SPY"),
    "qqq": ("US Tech (QQQ)", "QQQ"),
    "iwm": ("US Small Cap (IWM)", "IWM"),
    "efa": ("Int'l Dev (EFA)", "EFA"),
    "tlt": ("LT Treasuries (TLT)", "TLT"),
    "lqd": ("Corp Bonds (LQD)", "LQD"),
    "hyg": ("HY Bonds (HYG)", "HYG"),
    "gld": ("Gold (GLD)", "GLD"),
    "vnq": ("REITs (VNQ)", "VNQ"),
    "dbc": ("Commodities (DBC)", "DBC"),
}


def compute_market_sentiment(selected_assets: list[str] | None = None, window: int = 4) -> dict:
    selected_assets = selected_assets or ["spy", "qqq", "tlt", "gld", "hyg"]
    all_tickers = [v[1] for v in GLOBAL_MARKETS.values()] + [v[1] for v in US_ASSETS.values()]
    prices = to_weekly_prices(all_tickers).tail(575)
    returns = prices.pct_change().dropna(how="all")

    global_cards = []
    for key, (name, ticker) in GLOBAL_MARKETS.items():
        s = prices[ticker].dropna()
        ret = s.pct_change().dropna()
        recent = ret.tail(window)
        cum = (1 + recent).prod() - 1 if not recent.empty else np.nan
        global_cards.append(
            {
                "id": key,
                "name": name,
                "price": round(float(s.iloc[-1]), 2),
                "change": round(float(cum * 100), 2),
            }
        )

    us_price_df = prices[[US_ASSETS[k][1] for k in selected_assets if k in US_ASSETS]].dropna()
    us_norm = us_price_df / us_price_df.iloc[0] * 100
    us_norm.columns = [k for k in selected_assets if k in US_ASSETS]

    win_ret = returns[[US_ASSETS[k][1] for k in selected_assets if k in US_ASSETS]].tail(window).dropna()
    cov = win_ret.cov().values
    corr = cov_to_corr(cov)

    fg_resp = Fetcher()()
    fg_now = fg_resp["fear_and_greed"]
    fg_hist = fg_resp["fear_and_greed_historical"]["data"]
    fg_series = [
        {
            "date": pd.to_datetime(item["x"], unit="ms").strftime("%Y-%m-%d"),
            "value": round(float(item["y"]), 2),
            "rating": item.get("rating", ""),
        }
        for item in fg_hist[-260:]
    ]

    return {
        "global_cards": global_cards,
        "selected_assets": selected_assets,
        "us_chart": json_multi(us_norm, 2),
        "fear_greed": {
            "value": round(float(fg_now["score"]), 2),
            "rating": str(fg_now["rating"]),
            "last_update": pd.to_datetime(fg_now["timestamp"]).strftime("%Y-%m-%d"),
            "previous_close": round(float(fg_now["previous_close"]), 2),
            "previous_1_week": round(float(fg_now["previous_1_week"]), 2),
            "previous_1_month": round(float(fg_now["previous_1_month"]), 2),
            "previous_1_year": round(float(fg_now["previous_1_year"]), 2),
            "series": fg_series,
        },
        "heatmap": {
            "labels": [k.upper() for k in selected_assets],
            "cov": [[round(float(v), 6) for v in row] for row in cov.tolist()],
            "corr": [[round(float(v), 3) for v in row] for row in corr.tolist()],
        },
        "global_meta": [{"id": k, "name": v[0]} for k, v in GLOBAL_MARKETS.items()],
        "us_meta": [{"id": k, "name": v[0]} for k, v in US_ASSETS.items()],
    }
