from __future__ import annotations

import numpy as np
import pandas as pd
from fear_and_greed.cnn import Fetcher

from app.cache import ttl_cache
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


@ttl_cache(ttl_seconds=900, maxsize=8)
def fetch_fear_greed() -> dict:
    return Fetcher()()


@ttl_cache(ttl_seconds=600, maxsize=24)
def compute_market_sentiment(selected_assets: list[str] | None = None, window: int = 4) -> dict:
    selected_assets = selected_assets or ["spy", "qqq", "tlt", "gld", "hyg"]
    window = max(2, min(int(window), 52))
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
                "price": round(float(s.iloc[-1]), 2) if not s.empty else np.nan,
                "change": round(float(cum * 100), 2) if pd.notna(cum) else np.nan,
            }
        )

    selected_pairs = [(k, US_ASSETS[k][1]) for k in selected_assets if k in US_ASSETS]
    usable_pairs = [(k, t) for k, t in selected_pairs if t in prices.columns and prices[t].notna().sum() > 1]
    if len(usable_pairs) < 2:
        usable_pairs = [(k, meta[1]) for k, meta in list(US_ASSETS.items())[:5]]
    usable_pairs = [(k, t) for k, t in usable_pairs if t in prices.columns and prices[t].notna().sum() > 1]
    if len(usable_pairs) < 2:
        raise ValueError("Not enough market data to build the cross-market board.")

    usable_ids = [k for k, _ in usable_pairs]
    usable_tickers = [t for _, t in usable_pairs]

    us_price_df = prices[usable_tickers].copy().ffill()
    us_price_df = us_price_df.dropna(how="all")
    if us_price_df.empty:
        raise ValueError("No valid weekly price history for the selected assets.")

    us_norm = pd.DataFrame(index=us_price_df.index)
    for asset_id, ticker in usable_pairs:
        s = us_price_df[ticker].dropna()
        if s.empty:
            continue
        base = float(s.iloc[0])
        if abs(base) < 1e-12:
            continue
        us_norm[asset_id] = us_price_df[ticker] / base * 100

    us_norm = us_norm.dropna(how="all")
    if us_norm.shape[1] < 2 or us_norm.empty:
        raise ValueError("Not enough normalized market series available for the selected assets.")

    ret_subset = returns[usable_tickers].copy()
    recent_ret = ret_subset.tail(max(window * 3, 26))
    valid_counts = recent_ret.notna().sum()
    min_obs = max(2, min(window, 8))
    matrix_pairs = [(asset_id, ticker) for asset_id, ticker in usable_pairs if int(valid_counts.get(ticker, 0)) >= min_obs]
    if len(matrix_pairs) < 2:
        matrix_pairs = usable_pairs[: max(2, min(len(usable_pairs), 5))]

    matrix_ids = [k for k, _ in matrix_pairs]
    matrix_tickers = [t for _, t in matrix_pairs]
    win_ret = recent_ret[matrix_tickers].tail(window).dropna(how="any")
    if len(win_ret) < 2:
        win_ret = ret_subset[matrix_tickers].dropna(how="any").tail(max(2, window))
    if len(win_ret) < 2:
        raise ValueError("Not enough overlapping weekly returns to compute the market matrix.")

    cov = win_ret.cov().values
    corr = cov_to_corr(cov)

    fg_resp = fetch_fear_greed()
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
        "selected_assets": usable_ids,
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
            "labels": [k.upper() for k in matrix_ids],
            "cov": [[round(float(v), 6) for v in row] for row in cov.tolist()],
            "corr": [[round(float(v), 3) for v in row] for row in corr.tolist()],
        },
        "global_meta": [{"id": k, "name": v[0]} for k, v in GLOBAL_MARKETS.items()],
        "us_meta": [{"id": k, "name": v[0]} for k, v in US_ASSETS.items()],
    }
