from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from app.cache import ttl_cache


ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".yfinance_cache"
CACHE_DIR.mkdir(exist_ok=True)

if hasattr(yf, "set_cache_location"):
    yf.set_cache_location(str(CACHE_DIR))
if hasattr(yf, "set_tz_cache_location"):
    yf.set_tz_cache_location(str(CACHE_DIR / "tz"))


@ttl_cache(ttl_seconds=900, maxsize=64)
def fetch_adjusted_prices(tickers: list[str]) -> pd.DataFrame:
    if not tickers:
        raise ValueError("At least one ticker is required.")

    tickers = [str(t).upper() for t in tickers]
    raw = yf.download(
        tickers=tickers,
        period="max",
        interval="1d",
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    if raw.empty:
        raise ValueError("No price history returned from yfinance.")

    prices = pd.DataFrame()
    if len(tickers) == 1:
        prices[tickers[0]] = raw["Close"]
    else:
        available = set(raw.columns.get_level_values(0))
        for ticker in tickers:
            if ticker in available:
                prices[ticker] = raw[ticker]["Close"]

    prices = prices.sort_index().dropna(how="all")
    if prices.empty:
        raise ValueError("No usable close prices were returned.")
    return prices


def prices_to_returns(prices: pd.DataFrame, frequency: str) -> pd.DataFrame:
    rule = {"weekly": "W-FRI", "monthly": "ME"}[frequency]
    sampled = prices.resample(rule).last()
    returns = sampled.pct_change().dropna(how="all")
    return returns
