from __future__ import annotations

import numpy as np
import pandas as pd

from app.risk_system_sources import (
    json_series,
    quantile_threshold,
    rolling_std,
    to_weekly_returns,
    garch_like_vol,
)


def compute_trigger_monitor(etfs: list[dict], params: dict) -> dict:
    tickers = [e["t"].upper() for e in etfs]
    weights = np.array([float(e["w"]) for e in etfs], dtype=float)
    weights = weights / (weights.sum() or 1.0)

    ret_df = to_weekly_returns(tickers).tail(575)
    ret_df = ret_df.dropna(how="all")
    common = [t for t in tickers if t in ret_df.columns]
    if len(common) < 2:
        raise ValueError("Need at least two valid ETF histories.")

    aligned = ret_df[common].copy()
    valid_counts = aligned.notna().sum()
    min_obs = max(26, int(len(aligned) * 0.35))
    usable = [t for t in common if int(valid_counts.get(t, 0)) >= min_obs]
    if len(usable) < 2:
        raise ValueError("Not enough overlapping ETF history for this portfolio preset.")

    weights = np.array([weights[tickers.index(t)] for t in usable], dtype=float)
    weights = weights / weights.sum()
    ret_df = aligned[usable].dropna()
    if len(ret_df) < 12:
        raise ValueError("Not enough common weekly observations after aligning ETF histories.")

    port = ret_df.mul(weights, axis=1).sum(axis=1)

    sw = int(params["sw"])
    lw = int(params["lw"])
    cw = int(params["cw"])
    tq = float(params["tq"])
    mv = int(params["mv"])
    fw = 8

    fwd_vol = pd.Series(index=port.index, dtype=float)
    for i in range(len(port) - fw + 1):
        sl = port.iloc[i : i + fw]
        fwd_vol.iloc[i] = sl.std() * np.sqrt(52)

    vs = rolling_std(port, sw)
    vl = rolling_std(port, lw)
    vol_ratio = vs / vl
    m1_thresh = quantile_threshold(vol_ratio.iloc[: int(len(vol_ratio) * 0.8)], tq)
    t_m1 = vol_ratio > m1_thresh

    gvol = garch_like_vol(port)
    m2_thresh = quantile_threshold(gvol.iloc[: int(len(gvol) * 0.8)], tq)
    t_m2 = gvol > m2_thresh

    fro = pd.Series(index=port.index, dtype=float)
    conc = pd.Series(index=port.index, dtype=float)
    prev_cov = None
    for end in range(cw, len(ret_df) + 1):
        win = ret_df.iloc[end - cw : end]
        cov = win.cov().values
        if prev_cov is not None and prev_cov.shape == cov.shape:
            diff = cov - prev_cov
            fro.iloc[end - 1] = float(np.sqrt(np.sum(diff ** 2)))
        eigvals = np.sort(np.abs(np.linalg.eigvalsh(cov)))[::-1]
        total = eigvals.sum()
        conc.iloc[end - 1] = float(eigvals[0] / total) if total > 0 else np.nan
        prev_cov = cov

    m3_thresh = quantile_threshold(fro, tq)
    m4_thresh = quantile_threshold(conc, tq)
    t_m3 = fro > m3_thresh
    t_m4 = conc > m4_thresh

    votes = (
        t_m1.astype(int)
        + t_m2.astype(int)
        + t_m3.astype(int)
        + t_m4.astype(int)
    )
    combined = votes >= mv

    events = []
    for dt in port.index[combined.fillna(False)]:
        fired = []
        if bool(t_m1.get(dt, False)):
            fired.append("M1")
        if bool(t_m2.get(dt, False)):
            fired.append("M2")
        if bool(t_m3.get(dt, False)):
            fired.append("M3")
        if bool(t_m4.get(dt, False)):
            fired.append("M4")
        events.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "votes": int(votes.loc[dt]),
                "fired": fired,
                "fwd_vol": None if pd.isna(fwd_vol.loc[dt]) else round(float(fwd_vol.loc[dt]), 4),
            }
        )

    vote_clean = votes.dropna()
    fwd_clean = fwd_vol.dropna()
    if vote_clean.empty or fwd_clean.empty:
        raise ValueError("Not enough observations to compute trigger statistics for this portfolio.")

    last_vote = int(vote_clean.iloc[-1])
    last_fv = float(fwd_clean.iloc[-1])
    med_fv = float(fwd_clean.median())
    last_event = events[-1] if events else None

    return {
        "dates": [d.strftime("%Y-%m-%d") for d in port.index],
        "portfolio": usable,
        "weights": [round(float(w), 4) for w in weights],
        "stats": {
            "risk_state": "TRIGGERED" if last_vote >= mv else "Normal",
            "combined_triggers": len(events),
            "current_fwd_vol": round(last_fv, 4),
            "median_fwd_vol": round(med_fv, 4),
            "last_trigger": last_event["date"] if last_event else "—",
            "last_trigger_detail": "+".join(last_event["fired"]) if last_event else "no recent trigger",
            "nav_state": "red" if last_vote >= mv else ("amber" if last_fv > med_fv * 1.3 else "green"),
            "last_vote": last_vote,
        },
        "series": {
            "forward_vol": json_series(fwd_vol, 4),
            "vol_ratio": json_series(vol_ratio, 4),
            "garch_vol": json_series(gvol, 4),
            "frobenius": json_series(fro, 6),
            "concentration": json_series(conc, 4),
        },
        "thresholds": {
            "m1": round(m1_thresh, 4),
            "m2": round(m2_thresh, 4),
            "m3": round(m3_thresh, 6),
            "m4": round(m4_thresh, 4),
        },
        "triggers": {
            "m1": [bool(x) for x in t_m1.fillna(False)],
            "m2": [bool(x) for x in t_m2.fillna(False)],
            "m3": [bool(x) for x in t_m3.fillna(False)],
            "m4": [bool(x) for x in t_m4.fillna(False)],
            "combined": [bool(x) for x in combined.fillna(False)],
            "votes": [int(x) if pd.notna(x) else 0 for x in votes],
        },
        "events": list(reversed(events[-25:])),
    }
