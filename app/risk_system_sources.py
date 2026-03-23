from __future__ import annotations

from functools import lru_cache
from io import StringIO
from urllib.request import urlopen

import numpy as np
import pandas as pd

from app.data import fetch_adjusted_prices


WEEKLY_POINTS = 575


def to_weekly_prices(tickers: list[str]) -> pd.DataFrame:
    prices = fetch_adjusted_prices(tickers)
    weekly = prices.resample("W-FRI").last().dropna(how="all")
    return weekly


def to_weekly_returns(tickers: list[str]) -> pd.DataFrame:
    return to_weekly_prices(tickers).pct_change().dropna(how="all")


@lru_cache(maxsize=32)
def fred_series(series_id: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = urlopen(url, timeout=20).read().decode("utf-8")
    df = pd.read_csv(StringIO(raw))
    df.columns = [str(c).strip() for c in df.columns]
    date_col = next((c for c in df.columns if c.upper() == "DATE"), df.columns[0])
    val_col = next((c for c in df.columns if c != date_col), None)
    if val_col is None:
        raise ValueError(f"Unexpected FRED format for {series_id}")
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    series = pd.to_numeric(df[val_col], errors="coerce")
    return pd.Series(series.values, index=df[date_col], name=series_id).dropna()


def weekly_fred(series_id: str) -> pd.Series:
    series = fred_series(series_id)
    weekly = series.resample("W-FRI").last().dropna()
    return weekly


def stale_weeks(series: pd.Series) -> int:
    if series.dropna().empty:
        return 10**9
    latest = pd.Timestamp.today().normalize()
    return int((latest - series.dropna().index.max()).days // 7)


def align_weekly(series_map: dict[str, pd.Series]) -> pd.DataFrame:
    df = pd.concat(series_map, axis=1).sort_index()
    return df.tail(WEEKLY_POINTS)


def json_series(series: pd.Series, digits: int = 4) -> list[dict[str, float | str | None]]:
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            "value": None if pd.isna(val) else round(float(val), digits),
        }
        for idx, val in series.items()
    ]


def json_multi(df: pd.DataFrame, digits: int = 4) -> dict[str, list[dict[str, float | str | None]]]:
    return {col: json_series(df[col], digits=digits) for col in df.columns}


def rolling_std(series: pd.Series, window: int, annualization: float = np.sqrt(52)) -> pd.Series:
    return series.rolling(window, min_periods=max(2, int(window * 0.8))).std() * annualization


def garch_like_vol(series: pd.Series, annualization: float = np.sqrt(52)) -> pd.Series:
    x = series.fillna(0.0).values.astype(float)
    alpha, beta, omega = 0.08, 0.90, 1e-6
    var = max(np.var(x[:52]), 1e-8)
    vals = []
    for r in x:
        vals.append(np.sqrt(max(var, 0.0)) * annualization)
        var = omega + alpha * (r ** 2) + beta * var
    return pd.Series(vals, index=series.index)


def quantile_threshold(series: pd.Series, q: float) -> float:
    clean = series.replace([np.inf, -np.inf], np.nan).dropna()
    return float(clean.quantile(q)) if not clean.empty else np.nan


def cov_to_corr(cov: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    return cov / np.outer(d, d)
