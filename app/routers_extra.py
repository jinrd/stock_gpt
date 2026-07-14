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

@router.get("/api/account/balance")
def get_account_balance():
    # 봇 전용 모의투자 계좌의 잔고/포트폴리오를 웹에서 확인하기 위해 force_mock=True 사용
    client = KisClient(get_settings(force_mock=True))
    try:
        balance = client.get_balance()
        return balance
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

