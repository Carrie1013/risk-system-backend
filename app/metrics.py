from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def resolve_window(frequency: str, window_value: int) -> int:
    if window_value <= 1:
        raise ValueError("Window must be greater than 1.")

    if frequency == "weekly" and window_value > 520:
        raise ValueError("Weekly window is too large. Try 520 or below.")
    if frequency == "monthly" and window_value > 240:
        raise ValueError("Monthly window is too large. Try 240 or below.")
    return int(window_value)


def _series_payload(series: pd.Series) -> list[dict[str, float | str | None]]:
    clean = series.dropna()
    return [
        {"date": idx.strftime("%Y-%m-%d"), "value": None if pd.isna(val) else float(val)}
        for idx, val in clean.items()
    ]


def _rolling_avg_pairwise_corr(df: pd.DataFrame, window: int, min_periods: int) -> pd.Series:
    values = []
    dates = []
    for end in range(window, len(df) + 1):
        block = df.iloc[end - window : end]
        valid = block.dropna(axis=1, thresh=min_periods)
        if valid.shape[1] < 2:
            values.append(np.nan)
            dates.append(df.index[end - 1])
            continue
        corr = valid.corr().values
        tri = corr[np.triu_indices_from(corr, k=1)]
        tri = tri[np.isfinite(tri)]
        values.append(np.nan if len(tri) == 0 else float(np.mean(tri)))
        dates.append(df.index[end - 1])
    return pd.Series(values, index=dates, name="avg_pairwise_corr")


def _eigen_metrics(cov: np.ndarray) -> tuple[float, float]:
    eigvals = np.linalg.eigvalsh(cov)
    eigvals = np.sort(np.clip(eigvals, 0.0, None))[::-1]
    total = eigvals.sum()
    concentration = float(eigvals[0] / total) if total > 0 else np.nan
    entropy = -np.sum(np.where(eigvals > 0, (eigvals / total) * np.log(eigvals / total + 1e-12), 0.0))
    effective_rank = float(np.exp(entropy)) if np.isfinite(entropy) else np.nan
    return concentration, effective_rank


def _fit_garch11(returns: pd.Series) -> tuple[float, float, float]:
    x = returns.dropna().values.astype(float)
    if len(x) < 30:
        return 1e-6, 0.08, 0.90

    def objective(params: np.ndarray) -> float:
        omega, alpha, beta = params
        if omega <= 1e-10 or alpha < 0 or beta < 0 or alpha + beta >= 0.999:
            return 1e12
        var = np.var(x) + 1e-8
        nll = 0.0
        for r in x:
            var = omega + alpha * (r ** 2) + beta * var
            nll += 0.5 * (np.log(var) + (r ** 2) / var)
        return nll

    result = minimize(
        objective,
        x0=np.array([1e-6, 0.08, 0.90]),
        bounds=[(1e-10, 0.1), (1e-6, 0.5), (1e-6, 0.999)],
        method="L-BFGS-B",
    )
    omega, alpha, beta = result.x
    if alpha + beta >= 0.999:
        beta = 0.999 - alpha
    return float(omega), float(alpha), float(beta)


def _garch_series(returns: pd.Series, annualization: float) -> pd.Series:
    train = returns.iloc[: max(30, int(len(returns) * 0.6))]
    omega, alpha, beta = _fit_garch11(train)
    var = max(train.var(), 1e-8)
    values = []
    for r in returns.fillna(0.0).values:
        var = omega + alpha * (r ** 2) + beta * var
        values.append(math.sqrt(max(var, 0.0)) * annualization)
    return pd.Series(values, index=returns.index, name="garch_conditional_vol")


def analyze_returns(returns: pd.DataFrame, frequency: str, window_value: int) -> dict:
    window = resolve_window(frequency, window_value)
    annualization = math.sqrt(52 if frequency == "weekly" else 12)
    min_periods = max(2, math.floor(window * 0.8))

    panel = returns.dropna(axis=1, how="all").copy()
    panel = panel.loc[:, panel.notna().sum() >= window]
    if panel.shape[1] < 2:
        raise ValueError("Need at least two assets with enough data after filtering.")
    if len(panel) < window * 2:
        raise ValueError("Not enough history for the requested window.")

    ew_ret = panel.mean(axis=1, skipna=True).dropna()

    risk_series = ew_ret.rolling(window, min_periods=min_periods).std() * annualization
    risk_recent = float(risk_series.dropna().iloc[-1])
    risk_hist = risk_series.dropna().iloc[:-1]
    risk_percentile = float((risk_hist <= risk_recent).mean() * 100) if not risk_hist.empty else np.nan

    corr_series = _rolling_avg_pairwise_corr(panel, window, min_periods)
    corr_recent = float(corr_series.dropna().iloc[-1])
    corr_hist = corr_series.dropna().iloc[:-1]
    corr_percentile = float((corr_hist <= corr_recent).mean() * 100) if not corr_hist.empty else np.nan

    cov_dates = []
    cov_drift_values = []
    frob_values = []
    eig_conc_values = []
    eig_rank_values = []
    prev_cov = None
    prev_eigs = None

    for end in range(window, len(panel) + 1):
        block = panel.iloc[end - window : end].dropna(axis=1, thresh=min_periods)
        if block.shape[1] < 2:
            continue
        cov = block.cov().values.astype(float)
        cov_dates.append(panel.index[end - 1])

        concentration, eff_rank = _eigen_metrics(cov)
        eig_conc_values.append(concentration)
        eig_rank_values.append(eff_rank)

        if prev_cov is None or prev_cov.shape != cov.shape:
            cov_drift_values.append(np.nan)
            frob_values.append(np.nan)
        else:
            diff = cov - prev_cov
            frob = float(np.sqrt(np.sum(diff ** 2)))
            base = float(np.sqrt(np.sum(prev_cov ** 2)))
            cov_drift_values.append(np.nan if base == 0 else frob / base)
            frob_values.append(frob)
        prev_cov = cov

        eigvals = np.sort(np.clip(np.linalg.eigvalsh(cov), 0.0, None))[::-1]
        if prev_eigs is None or len(prev_eigs) != len(eigvals):
            prev_eigs = eigvals
            continue
        prev_eigs = eigvals

    cov_drift = pd.Series(cov_drift_values, index=cov_dates, name="cov_drift")
    frob_distance = pd.Series(frob_values, index=cov_dates, name="frobenius_distance")
    eig_concentration = pd.Series(eig_conc_values, index=cov_dates, name="eig_concentration")
    eff_rank = pd.Series(eig_rank_values, index=cov_dates, name="effective_rank")
    eig_structure_drift = eig_concentration.diff().abs().rename("eig_structure_drift")

    garch_vol = _garch_series(ew_ret, annualization)
    garch_drift = garch_vol.pct_change().abs().rename("garch_conditional_drift")

    risk_threshold = float(risk_series.dropna().quantile(0.9))
    corr_threshold = float(corr_series.dropna().quantile(0.9))

    metrics = {
        "risk_percentile": {
            "label": "Risk Percentile",
            "value": round(risk_percentile, 2),
            "recent": risk_recent,
            "series": _series_payload(risk_series),
            "threshold": round(risk_threshold, 4),
        },
        "correlation_percentile": {
            "label": "Correlation Percentile",
            "value": round(float((corr_hist <= corr_recent).mean() * 100) if not corr_hist.empty else np.nan, 2),
            "recent": corr_recent,
            "series": _series_payload(corr_series),
            "threshold": round(corr_threshold, 4),
        },
        "cov_matrix_drift": {
            "label": "Covariance Matrix Drift",
            "value": round(float(cov_drift.dropna().iloc[-1]), 4),
            "recent": float(cov_drift.dropna().iloc[-1]),
            "series": _series_payload(cov_drift),
            "threshold": round(float(cov_drift.dropna().quantile(0.9)), 4),
        },
        "eig_value_structure_drift": {
            "label": "Eigenvalue Structure Drift",
            "value": round(float(eig_structure_drift.dropna().iloc[-1]), 4),
            "recent": float(eig_structure_drift.dropna().iloc[-1]),
            "series": _series_payload(eig_structure_drift),
            "threshold": round(float(eig_structure_drift.dropna().quantile(0.9)), 4),
        },
        "f_distance": {
            "label": "F-Distance",
            "value": round(float(frob_distance.dropna().iloc[-1]), 4),
            "recent": float(frob_distance.dropna().iloc[-1]),
            "series": _series_payload(frob_distance),
            "threshold": round(float(frob_distance.dropna().quantile(0.9)), 4),
        },
        "garch_conditional_drift": {
            "label": "GARCH Conditional Drift",
            "value": round(float(garch_drift.dropna().iloc[-1]), 4),
            "recent": float(garch_drift.dropna().iloc[-1]),
            "series": _series_payload(garch_drift),
            "threshold": round(float(garch_drift.dropna().quantile(0.9)), 4),
        },
    }

    trigger_rows = []
    for key, meta in metrics.items():
        trigger_rows.append(
            {
                "metric": key,
                "label": meta["label"],
                "value": meta["value"],
                "threshold": meta["threshold"],
                "triggered": bool(meta["value"] >= meta["threshold"]),
            }
        )

    return {
        "window": window,
        "frequency": frequency,
        "etf_count": int(panel.shape[1]),
        "sample_start": panel.index.min().strftime("%Y-%m-%d"),
        "sample_end": panel.index.max().strftime("%Y-%m-%d"),
        "assets": list(panel.columns),
        "metrics": metrics,
        "triggers": trigger_rows,
        "supporting": {
            "equal_weight_return": _series_payload(ew_ret),
            "avg_pairwise_corr": _series_payload(corr_series),
            "eig_concentration": _series_payload(eig_concentration),
            "effective_rank": _series_payload(eff_rank),
            "garch_vol": _series_payload(garch_vol),
        },
    }
