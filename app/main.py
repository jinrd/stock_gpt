from fastapi import FastAPI, HTTPException
from functools import lru_cache
from app.config import get_settings
from app.kis_client import KisApiError, KisClient
from app.analysis import analyze_daily_prices, analyze_daily_prices_by_regime, build_chart_data, select_defensive_market_index
import time
from typing import Any, Dict
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import threading
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 웹 서버 시작 시 백그라운드에서 봇들을 함께 구동합니다.
    # 이렇게 하면 웹 서버와 봇들이 완전히 동일한 프로세스에서 돌아가므로,
    # KisClient의 _rate_lock(초당 호출 제한)을 완벽하게 공유하여 HTTP 500 에러를 방지합니다.
    try:
        from bot import run_bot as run_krx_bot
        from bot_nasdaq import run_bot as run_nasdaq_bot
        
        krx_thread = threading.Thread(target=run_krx_bot, daemon=True)
        krx_thread.start()
        
        # 사용자의 요청으로 나스닥 봇은 임시 중단합니다.
        # nas_thread = threading.Thread(target=run_nasdaq_bot, daemon=True)
        # nas_thread.start()
        print("✅ 백그라운드 봇(코스피) 스레드가 성공적으로 시작되었습니다. (나스닥 봇은 중단됨)")
    except Exception as e:
        print(f"⚠️ 백그라운드 봇 시작 실패: {e}")
        
    yield

app = FastAPI(
    title="Stock Trading GPT",
    description="해외주식 분석 및 자동매매 도구",
    version="0.1.0",
    lifespan=lifespan
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

@lru_cache
def get_kis_client() -> KisClient:
    return KisClient(get_settings())

@app.get("/")
def home():
    return {
        "service": "Stock Trading GPT",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/api/config/status")
def config_status():
    settings = get_settings()

    risk_status = KisClient(settings).risk_manager.status()
    return {
        "configured": True,
        "mode": "paper" if settings.kis_is_paper else "live",
        "account_last_four_digits": settings.kis_account_no[-4:],
        "live_trading_enabled": risk_status["live_trading_enabled"],
    }


@app.get("/api/kis/connection")
def kis_connection_check():
    client = get_kis_client()

    try:
        client.get_access_token()
    except KisApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "connected": True,
        "mode": "paper" if client.settings.kis_is_paper else "live",
        "message": "한국투자증권 액세스 토큰 발급에 성공했습니다.",
    }

@app.get("/api/screener")
def run_screener(
    exchange: str = "NAS",
    minimum_price: float = 5,
    maximum_price: float = 1000,
    minimum_volume: int = 1_000_000,
):
    allowed_exchanges = {"NAS", "NYS", "AMS", "KRX"}

    if exchange not in allowed_exchanges:
        raise HTTPException(
            status_code=400,
            detail="exchange는 NAS, NYS, AMS, KRX 중 하나여야 합니다.",
        )

    # KRX일 경우 기본값(USD 기준)이 그대로 넘어왔다면 원화(KRW) 기준으로 스케일링
    if exchange == "KRX":
        if minimum_price == 5: minimum_price = 1000
        if maximum_price == 1000: maximum_price = 3000000

    client = get_kis_client()

    try:
        if exchange == "KRX":
            stocks = client.search_krx_stocks(
                minimum_price=minimum_price,
                maximum_price=maximum_price,
                minimum_volume=minimum_volume,
            )
        else:
            stocks = client.search_stocks(
                exchange=exchange,
                minimum_price=minimum_price,
                maximum_price=maximum_price,
                minimum_volume=minimum_volume,
            )
    except KisApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    # 거래대금(tval)이 있으면 거래대금 순, 없으면 거래량(tvol) 순으로 정렬
    sorted_stocks = sorted(
        stocks,
        key=lambda stock: _to_float(stock.get("tval")) if stock.get("tval", "0") != "0" else _to_float(stock.get("tvol")),
        reverse=True,
    )

    candidates = [
        {
            "symbol": stock.get("mksc_shrn_iscd") or stock.get("symb"),
            "name": stock.get("hts_kor_isnm") or stock.get("knam") or stock.get("name") or stock.get("ename"),
            "price": stock.get("prpr") or stock.get("last"),
            "change_rate": stock.get("prdy_ctrt") or stock.get("rate"),
            "volume": stock.get("acml_vol") or stock.get("tvol"),
        }
        for stock in sorted_stocks
    ]

    return {
        "exchange": exchange,
        "candidate_count": len(candidates),
        "filters": {
            "minimum_price": minimum_price,
            "maximum_price": maximum_price,
            "minimum_volume": minimum_volume,
        },
        "candidates": candidates,
    }

@app.get("/api/analyze/{symbol}")
def analyze_stock(symbol: str, exchange: str = "NAS"):
    allowed_exchanges = {"NAS", "NYS", "AMS", "KRX"}

    if exchange not in allowed_exchanges:
        raise HTTPException(
            status_code=400,
            detail="exchange는 NAS, NYS, AMS, KRX 중 하나여야 합니다.",
        )

    client = get_kis_client()

    try:
        if exchange == "KRX":
            daily_prices = client.get_krx_daily_prices(symbol=symbol)
        else:
            daily_prices = client.get_daily_prices(
                exchange=exchange,
                symbol=symbol,
            )
        if exchange == "KRX":
            market_name, market_prices = select_defensive_market_index({
                "KOSPI": client.get_krx_index_daily_prices("KOSPI"),
                "KOSDAQ": client.get_krx_index_daily_prices("KOSDAQ"),
            })
        else:
            market_prices = client.get_daily_prices("NAS", "QQQ")
            market_name = "QQQ"
        analysis = analyze_daily_prices_by_regime(daily_prices, market_prices)
        analysis["market_filter"]["reference_index"] = market_name
    except KisApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "symbol": symbol.upper(),
        "exchange": exchange,
        "analysis": analysis,
        "disclaimer": "기술지표 기반 참고 정보이며 투자 판단과 주문은 사용자의 책임입니다.",
    }

def _to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0

    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return 0.0


@app.get("/api/today-focus")
def get_today_focus(
    exchange: str = "NAS",
    minimum_price: float = 5,
    maximum_price: float = 1000,
    minimum_volume: int = 1_000_000,
    candidate_limit: int = 5,
):
    allowed_exchanges = {"NAS", "NYS", "AMS", "KRX"}

    if exchange not in allowed_exchanges:
        raise HTTPException(
            status_code=400,
            detail="exchange는 NAS, NYS, AMS, KRX 중 하나여야 합니다.",
        )

    # KRX일 경우 기본값(USD 기준)이 그대로 넘어왔다면 원화(KRW) 기준으로 스케일링
    if exchange == "KRX":
        if minimum_price == 10.0: minimum_price = 1000
        if maximum_price == 1000: maximum_price = 3000000  # 황제주(100만원 이상) 포함을 위해 3,000만 원으로 상향

    if not 1 <= candidate_limit <= 5:
        raise HTTPException(
            status_code=400,
            detail="candidate_limit은 1~5 사이여야 합니다.",
        )

    client = get_kis_client()

    try:
        if exchange == "KRX":
            stocks = client.search_krx_stocks(
                minimum_price=minimum_price,
                maximum_price=maximum_price,
                minimum_volume=minimum_volume,
            )
        else:
            stocks = client.search_stocks(
                exchange=exchange,
                minimum_price=minimum_price,
                maximum_price=maximum_price,
                minimum_volume=minimum_volume,
            )
    except KisApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    # 조건검색 결과 중 거래대금(tval)이 있으면 거래대금 순, 없으면 거래량(tvol) 순으로 정렬하여 우량주(하이닉스 등)가 우선 포함되도록 합니다.
    sorted_stocks = sorted(
        stocks,
        key=lambda stock: _to_float(stock.get("tval")) if stock.get("tval", "0") != "0" else _to_float(stock.get("tvol")),
        reverse=True,
    )

    selected_stocks = sorted_stocks[:candidate_limit]
    focus_stocks: list[Dict[str, Any]] = []
    failed_symbols = []

    # 모의투자 API 호출 제한을 고려해 종목별 요청 간격을 둡니다.
    for stock in selected_stocks:
        symbol = stock.get("mksc_shrn_iscd") or stock.get("symb")

        if not symbol:
            continue


        try:
            if exchange == "KRX":
                daily_prices = client.get_krx_daily_prices(symbol=symbol)
            else:
                daily_prices = client.get_daily_prices(
                    exchange=exchange,
                    symbol=symbol,
                )
            analysis = analyze_daily_prices(daily_prices)
        except (KisApiError, ValueError):
            failed_symbols.append(symbol)
            continue

        focus_stocks.append(
            {
                "symbol": symbol,
                "name": stock.get("hts_kor_isnm") or stock.get("knam") or stock.get("name") or stock.get("ename"),
                "current_price": _to_float(stock.get("prpr") or stock.get("last")),
                "change_rate": _to_float(stock.get("prdy_ctrt") or stock.get("rate")),
                "volume": _to_float(stock.get("acml_vol") or stock.get("tvol")),
                "analysis": analysis,
            }
        )

    # 지표 점수가 높은 종목부터 보여줍니다.
    focus_stocks.sort(
        key=lambda stock: stock["analysis"]["score"],
        reverse=True,
    )

    return {
        "exchange": exchange,
        "requested_candidate_count": candidate_limit,
        "analyzed_count": len(focus_stocks),
        "failed_symbols": failed_symbols,
        "filters": {
            "minimum_price": minimum_price,
            "maximum_price": maximum_price,
            "minimum_volume": minimum_volume,
        },
        "focus_stocks": focus_stocks,
        "disclaimer": (
            "기술지표 기반 참고 정보이며 "
            "투자 판단과 주문은 사용자의 책임입니다."
        ),
    }

@app.get("/api/chart/{symbol}")
def get_chart_data(symbol: str, exchange: str = "NAS"):


    allowed_exchanges = {"NAS", "NYS", "AMS", "KRX"}

    if exchange not in allowed_exchanges:
        raise HTTPException(
            status_code=400,
            detail="exchange는 NAS, NYS, AMS, KRX 중 하나여야 합니다.",
        )

    client = get_kis_client()

    try:
        if exchange == "KRX":
            daily_prices = client.get_krx_daily_prices(symbol=symbol)
        else:
            daily_prices = client.get_daily_prices(
                exchange=exchange,
                symbol=symbol,
            )
        chart_data = build_chart_data(daily_prices)
    except KisApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return {
        "symbol": symbol.upper(),
        "exchange": exchange,
        "chart": chart_data,
    }

@app.get("/api/dashboard/{symbol}")
def get_dashboard_data(symbol: str, exchange: str = "NAS"):
    allowed_exchanges = {"NAS", "NYS", "AMS", "KRX"}

    if exchange not in allowed_exchanges:
        raise HTTPException(
            status_code=400,
            detail="exchange는 NAS, NYS, AMS, KRX 중 하나여야 합니다.",
        )

    client = get_kis_client()

    # 사용자가 APPL, Apple 등 오타나 회사명을 입력했을 경우 정확한 티커로 자동 교정
    symbol = client.resolve_symbol(exchange=exchange, symbol=symbol)

    try:
        if exchange == "KRX":
            daily_prices = client.get_krx_daily_prices(symbol=symbol)
        else:
            daily_prices = client.get_daily_prices(
                exchange=exchange,
                symbol=symbol,
            )
        if exchange == "KRX":
            market_name, market_prices = select_defensive_market_index({
                "KOSPI": client.get_krx_index_daily_prices("KOSPI"),
                "KOSDAQ": client.get_krx_index_daily_prices("KOSDAQ"),
            })
        else:
            market_prices = client.get_daily_prices("NAS", "QQQ")
            market_name = "QQQ"
        analysis = analyze_daily_prices_by_regime(daily_prices, market_prices)
        analysis["market_filter"]["reference_index"] = market_name
        chart = build_chart_data(daily_prices)
        name = client.get_stock_name(exchange=exchange, symbol=symbol)
    except KisApiError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "symbol": symbol.upper(),
        "name": name,
        "exchange": exchange,
        "analysis": analysis,
        "chart": chart,
    }


# 크롬 개발자 도구가 자동으로 요청하는 경로. 404 로그가 남는 것을 방지하기 위해 더미 응답 추가
@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
def chrome_devtools_silencer():
    return {}
# 새로운 라우터 등록
try:
    from app.routers_extra import router as extra_router
    app.include_router(extra_router)
except ImportError:
    pass
