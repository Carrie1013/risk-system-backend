from __future__ import annotations

import numpy as np
import pandas as pd

from app.risk_system_sources import json_series, to_weekly_returns, cov_to_corr


DEFAULT_ASSETS = ["VTI", "BND", "GLD", "VNQ", "EWC", "EWL", "GXC", "LQD"]


def compute_structural_risk(assets: list[str] | None = None, window: int = 52) -> dict:
    assets = assets or DEFAULT_ASSETS[:6]
    window = max(12, min(int(window), 156))
    ret = to_weekly_returns(DEFAULT_ASSETS).tail(575).dropna()
    assets = [a for a in assets if a in ret.columns]
    if len(assets) < 2:
        raise ValueError("Need at least two structural assets.")
    ret = ret[assets]
    n = len(ret)
    cw = window

    sri = pd.Series(index=ret.index, dtype=float)
    eff_rank = pd.Series(index=ret.index, dtype=float)
    part_ratio = pd.Series(index=ret.index, dtype=float)
    avg_corr = pd.Series(index=ret.index, dtype=float)
    disp_corr = pd.Series(index=ret.index, dtype=float)

    for end in range(cw, n + 1):
        win = ret.iloc[end - cw : end]
        cov = win.cov().values
        eig = np.sort(np.clip(np.linalg.eigvalsh(cov), 0.0, None))[::-1]
        total = eig.sum()
        if total > 0:
            p = eig / total
            sri.iloc[end - 1] = eig[0] / total
            eff_rank.iloc[end - 1] = float(np.exp(-(p * np.log(p + 1e-12)).sum()))
            part_ratio.iloc[end - 1] = float((total ** 2) / (np.sum(eig ** 2) * len(eig)))

        corr = cov_to_corr(cov)
        tri = corr[np.triu_indices_from(corr, k=1)]
        avg_corr.iloc[end - 1] = float(np.mean(tri))
        disp_corr.iloc[end - 1] = float(np.std(tri))

    cov_last = ret.iloc[-cw:].cov().values
    corr_last = cov_to_corr(cov_last)
    eig_last = np.sort(np.clip(np.linalg.eigvalsh(cov_last), 0.0, None))[::-1]
    cum = np.cumsum(eig_last / eig_last.sum()) if eig_last.sum() > 0 else np.zeros_like(eig_last)

    return {
        "assets_all": DEFAULT_ASSETS,
        "assets_active": assets,
        "window": cw,
        "stats": {
            "sri": round(float(sri.dropna().iloc[-1]), 3),
            "effective_rank": round(float(eff_rank.dropna().iloc[-1]), 2),
            "participation_ratio": round(float(part_ratio.dropna().iloc[-1]), 3),
            "avg_corr": round(float(avg_corr.dropna().iloc[-1]), 3),
        },
        "series": {
            "sri": json_series(sri, 3),
            "effective_rank": json_series(eff_rank, 3),
            "participation_ratio": json_series(part_ratio, 3),
            "avg_corr": json_series(avg_corr, 3),
            "disp_corr": json_series(disp_corr, 3),
        },
        "cum_variance": [round(float(v), 3) for v in cum.tolist()],
        "pcs": [f"PC{i+1}" for i in range(len(cum))],
        "heatmap": {
            "labels": assets,
            "matrix": [[round(float(v), 3) for v in row] for row in corr_last.tolist()],
        },
    }
