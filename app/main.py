from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.data import fetch_adjusted_prices, prices_to_returns
from app.metrics import analyze_returns
from app.page_exogenous_risk import compute_exogenous_risk
from app.page_market_sentiment import compute_market_sentiment
from app.page_regime_risk import compute_regime_risk
from app.page_structural_risk import compute_structural_risk
from app.page_trigger_monitor import compute_trigger_monitor


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
PROJECT_ROOT = ROOT.parent

app = FastAPI(title="Risk Change Dashboard")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class AnalysisRequest(BaseModel):
    tickers: list[str] = Field(..., min_length=2)
    frequency: str = Field(..., pattern="^(weekly|monthly)$")
    window_value: int = Field(..., gt=1)


class TriggerMonitorRequest(BaseModel):
    etfs: list[dict]
    params: dict


@app.get("/")
def index() -> FileResponse:
    risk_system = PROJECT_ROOT / "risk_system.html"
    if risk_system.exists():
        return FileResponse(risk_system)
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/analyze")
def analyze(request: AnalysisRequest) -> dict:
    try:
        tickers = [ticker.strip().upper() for ticker in request.tickers if ticker.strip()]
        prices = fetch_adjusted_prices(tickers)
        returns = prices_to_returns(prices, request.frequency)
        result = analyze_returns(returns, request.frequency, request.window_value)
        result["requested_tickers"] = tickers
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


@app.post("/api/risk-system/page0")
def risk_system_page0(request: TriggerMonitorRequest) -> dict:
    try:
        return compute_trigger_monitor(request.etfs, request.params)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/risk-system/page1")
def risk_system_page1(period_weeks: int = 1) -> dict:
    try:
        return compute_exogenous_risk(period_weeks)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/risk-system/page2")
def risk_system_page2(assets: str = "", window: int = 52) -> dict:
    try:
        asset_list = [a.strip().upper() for a in assets.split(",") if a.strip()] or None
        return compute_structural_risk(asset_list, window)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/risk-system/page3")
def risk_system_page3(garch: float = 0.25, eigen: float = 0.25, corr: float = 0.25, exo: float = 0.25) -> dict:
    try:
        return compute_regime_risk({"garch": garch, "eigen": eigen, "corr": corr, "exo": exo})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/risk-system/page4")
def risk_system_page4(assets: str = "", window: int = 4) -> dict:
    try:
        asset_list = [a.strip().lower() for a in assets.split(",") if a.strip()] or None
        return compute_market_sentiment(asset_list, window)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
