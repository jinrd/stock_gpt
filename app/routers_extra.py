from fastapi import APIRouter, HTTPException
from app.kis_client import KisClient
from app.config import get_settings
from app.analysis import analyze_extra_data

router = APIRouter()

@router.get("/api/dashboard/{symbol}/extra")
def get_dashboard_extra(symbol: str, exchange: str = "NAS"):
    allowed_exchanges = {"NAS", "NYS", "AMS", "KRX"}
    if exchange not in allowed_exchanges:
        raise HTTPException(
            status_code=400,
            detail="exchange는 NAS, NYS, AMS, KRX 중 하나여야 합니다.",
        )
    
    client = KisClient(get_settings())
    # 자동 교정 (필요 시)
    symbol = client.resolve_symbol(exchange=exchange, symbol=symbol)
    
    fundamentals = client.get_fundamentals(exchange=exchange, symbol=symbol)
    order_book = client.get_order_book(exchange=exchange, symbol=symbol)
    
    extra_analysis = analyze_extra_data(fundamentals, order_book)
    
    return {
        "symbol": symbol.upper(),
        "exchange": exchange,
        "fundamentals": fundamentals,
        "order_book": order_book,
        "extra_analysis": extra_analysis
    }

from app.analysis import analyze_daily_prices
from app.backtest import run_backtest

@router.get("/api/risk/status")
def get_risk_status():
    """현재 주문 한도와 당일 누적 매수액을 반환합니다."""
    return KisClient(get_settings()).risk_manager.status()

@router.get("/api/analysis/summary")
def get_analysis_summary():
    """오늘 기록된 분석 신호의 분포와 평균 점수를 반환합니다."""
    return KisClient(get_settings()).risk_manager.analysis_summary()

@router.get("/api/backtest/{symbol}")
def get_backtest(symbol: str, exchange: str = "KRX", commission_bps: float = 10, slippage_bps: float = 5):
    if exchange not in {"NAS", "NYS", "AMS", "KRX"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 거래소입니다.")
    if not 0 <= commission_bps <= 100 or not 0 <= slippage_bps <= 100:
        raise HTTPException(status_code=400, detail="수수료와 슬리피지는 0~100bp 범위여야 합니다.")
    client = KisClient(get_settings())
    try:
        prices = client.get_krx_daily_prices(symbol) if exchange == "KRX" else client.get_daily_prices(exchange, symbol)
        return {"symbol": symbol.upper(), "exchange": exchange,
                "backtest": run_backtest(prices, commission_bps, slippage_bps),
                "disclaimer": "과거 성과는 미래 수익을 보장하지 않으며, 세금·호가 단위·체결 실패는 반영되지 않습니다."}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@router.get("/api/account/balance")
def get_account_balance(exchange: str = "KRX"):
    # 봇 전용 모의투자 계좌의 잔고/포트폴리오를 웹에서 확인하기 위해 force_mock=True 사용
    client = KisClient(get_settings(force_mock=True))
    try:
        if exchange == "KRX":
            balance = client.get_balance()
        else:
            balance = client.get_nasdaq_balance()
        
        # 보유 종목들에 대해 일봉 조회 후 매도 예상가(목표가) 계산 추가
        for stock in balance.get("stocks", []):
            symbol = stock["symbol"]
            try:
                if exchange == "KRX":
                    prices = client.get_krx_daily_prices(symbol)
                else:
                    prices = client.get_daily_prices("NAS", symbol)
                    
                if prices:
                    analysis = analyze_daily_prices(prices)
                    stock["target_price"] = analysis.get("target_price", 0.0)
                else:
                    stock["target_price"] = 0.0
            except Exception:
                stock["target_price"] = 0.0
                
        return balance
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
