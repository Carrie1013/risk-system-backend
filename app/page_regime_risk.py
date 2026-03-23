from __future__ import annotations

import numpy as np
import pandas as pd

from app.page_exogenous_risk import compute_exogenous_risk
from app.page_structural_risk import DEFAULT_ASSETS
from app.risk_system_sources import garch_like_vol, json_series, to_weekly_returns, cov_to_corr


def compute_regime_risk(weights: dict[str, float] | None = None) -> dict:
    ret = to_weekly_returns(["VTI", "BND", "GLD", "VNQ"]).tail(575).dropna()
    ew = ret.mean(axis=1)
    gvol = garch_like_vol(ew)

    struct = to_weekly_returns(DEFAULT_ASSETS[:4]).tail(575).dropna()
    conc = pd.Series(index=struct.index, dtype=float)
    avg_corr = pd.Series(index=struct.index, dtype=float)
    cw = 52
    for end in range(cw, len(struct) + 1):
        cov = struct.iloc[end - cw : end].cov().values
        eig = np.sort(np.clip(np.linalg.eigvalsh(cov), 0.0, None))[::-1]
        total = eig.sum()
        conc.iloc[end - 1] = eig[0] / total if total > 0 else np.nan
        corr = cov_to_corr(cov)
        tri = corr[np.triu_indices_from(corr, k=1)]
        avg_corr.iloc[end - 1] = np.mean(tri)

    exo = compute_exogenous_risk()
    exo_series = pd.Series(
        [row["value"] for row in exo["series"]["composite"]],
        index=pd.to_datetime([row["date"] for row in exo["series"]["composite"]]),
    )

    df = pd.concat(
        [
            gvol.rename("gvol"),
            conc.rename("conc"),
            avg_corr.rename("avg_corr"),
            exo_series.rename("exo"),
        ],
        axis=1,
    ).dropna()

    norm = (df - df.min()) / (df.max() - df.min() + 1e-12)
    weights = weights or {"garch": 0.25, "eigen": 0.25, "corr": 0.25, "exo": 0.25}
    keys = ["garch", "eigen", "corr", "exo"]
    w = np.array([max(0.0, float(weights.get(k, 0.0))) for k in keys], dtype=float)
    if w.sum() == 0:
        w = np.array([0.25, 0.25, 0.25, 0.25], dtype=float)
    w = w / w.sum()
    weight_map = dict(zip(keys, w.tolist()))
    risk_score = (
        norm["gvol"] * weight_map["garch"]
        + norm["conc"] * weight_map["eigen"]
        + norm["avg_corr"] * weight_map["corr"]
        + norm["exo"] * weight_map["exo"]
    )
    d_risk = risk_score.diff()

    def classify(v: float) -> str:
        if v < 0.25:
            return "low"
        if v < 0.55:
            return "rising"
        if v < 0.8:
            return "crisis"
        return "recovery"

    regimes = risk_score.apply(classify)
    current = regimes.iloc[-1]
    lev_map = {"low": "1.1×", "rising": "0.75×", "crisis": "0.35×", "recovery": "0.55×"}
    exp_map = {"low": "90%", "rising": "60%", "crisis": "25%", "recovery": "45%"}
    counts = regimes.value_counts(normalize=True)

    factor_vals = {
        "GARCH vol": round(float(norm["gvol"].iloc[-1]), 3),
        "Eigenvalue": round(float(norm["conc"].iloc[-1]), 3),
        "Avg corr": round(float(norm["avg_corr"].iloc[-1]), 3),
        "Exogenous": round(float(norm["exo"].iloc[-1]), 3),
    }

    return {
        "stats": {
            "current_regime": current,
            "current_score": round(float(risk_score.iloc[-1]), 3),
            "delta_risk": round(float(d_risk.iloc[-1]), 3),
            "leverage": lev_map[current],
            "exposure": exp_map[current],
            "regime_pcts": {k: f"{round(float(counts.get(k, 0) * 100))}%" for k in ["low", "rising", "crisis", "recovery"]},
        },
        "series": {
            "risk_score": json_series(risk_score, 3),
            "delta_risk": json_series(d_risk, 3),
        },
        "regimes": regimes.tolist(),
        "weights": {k: round(v, 3) for k, v in weight_map.items()},
        "factor_contrib": factor_vals,
        "rules": [
            {"name": "GARCH vol z-score", "weight": f"{round(weight_map['garch'] * 100)}%", "val": factor_vals["GARCH vol"], "contrib": round(factor_vals["GARCH vol"] * weight_map["garch"], 3)},
            {"name": "Eigenvalue concentration", "weight": f"{round(weight_map['eigen'] * 100)}%", "val": factor_vals["Eigenvalue"], "contrib": round(factor_vals["Eigenvalue"] * weight_map["eigen"], 3)},
            {"name": "Avg pairwise correlation", "weight": f"{round(weight_map['corr'] * 100)}%", "val": factor_vals["Avg corr"], "contrib": round(factor_vals["Avg corr"] * weight_map["corr"], 3)},
            {"name": "Exogenous stress", "weight": f"{round(weight_map['exo'] * 100)}%", "val": factor_vals["Exogenous"], "contrib": round(factor_vals["Exogenous"] * weight_map["exo"], 3)},
        ],
    }
