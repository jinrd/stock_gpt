import os
import time
import datetime
from dotenv import load_dotenv

load_dotenv()
os.environ["KIS_IS_PAPER"] = "true"

from app.config import get_settings
from app.kis_client import KisClient
from app.analysis import analyze_daily_prices

def run_bot():
    settings = get_settings()
    client = KisClient(settings)
    
    print("=" * 50)
    print("🤖 StockPro 자동 매매 봇 작동 시작 (모의투자)")
    print("=" * 50)
    
    while True:
        now = datetime.datetime.now()
        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 잔고 및 시장 모니터링 중...")
        
        try:
            # 1. 계좌 잔고 및 보유 주식 확인
            balance = client.get_balance()
            cash = balance.get("orderable_cash", 0)
            holdings = balance.get("stocks", [])
            
            print(f"💰 주문 가능 현금: {cash:,.0f}원 | 📦 보유 종목 수: {len(holdings)}개")
            
            # 2. 매도 로직 (보유 종목 검사)
            for stock in holdings:
                symbol = stock["symbol"]
                name = stock["name"]
                qty = stock["quantity"]
                current_price = stock["current_price"]
                
                # 차트 분석 가져오기
                prices = client.get_krx_daily_prices(symbol)
                if not prices:
                    continue
                
                analysis = analyze_daily_prices(prices)
                target_price = analysis.get("target_price", current_price * 1.1)
                stop_loss = analysis.get("stop_loss_price", current_price * 0.9)
                action = analysis.get("action")
                
                print(f"  [보유] {name}({symbol}): 현재가 {current_price:,.0f}원 | 목표가 {target_price:,.0f}원 | 손절가 {stop_loss:,.0f}원 | 상태: {action}")
                
                # 매도 조건 (익절 또는 손절)
                if current_price >= target_price:
                    print(f"  👉 📈 목표가 도달! {name} {qty}주 시장가 매도 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market")
                    time.sleep(1.5)
                elif current_price <= stop_loss:
                    print(f"  👉 📉 손절가 이탈! {name} {qty}주 시장가 매도 (손절) 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market")
                    time.sleep(1.5)
                elif action == "매도 검토":
                    print(f"  👉 ⚠️ 위험 신호 포착! {name} {qty}주 시장가 매도 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market")
                    time.sleep(1.5)
                
                time.sleep(0.5) # API 호출 제한 방지
            
            # 3. 매수 로직 (현금이 있을 때만)
            if cash > 100000: # 최소 10만원 이상 있을 때만 스캔
                print("\n🔎 신규 매수 유망 종목 스캔 중...")
                
                # 거래량 100만주 이상, 가격 1000~100000원 종목 검색
                candidates = client.search_krx_stocks(
                    minimum_price=1000,
                    maximum_price=100000,
                    minimum_volume=1000000
                )
                candidates = candidates[:20] # 상위 20개만
                
                for cand in candidates:
                    # KIS API 국내주식 거래량 순위 응답 키 처리
                    symbol = cand.get("mksc_shrn_iscd") or cand.get("symb") or cand.get("pdno")
                    name = cand.get("hts_kor_isnm") or cand.get("knam") or cand.get("name")
                    
                    if not symbol:
                        continue
                        
                    # 이미 보유 중이면 패스
                    if any(h["symbol"] == symbol for h in holdings):
                        continue
                        
                    # API 호출 제한을 막기 위해 3.0초 대기 (모의투자 서버 500 에러 완벽 방지)
                    time.sleep(3.0)
                    
                    try:
                        print(f"  🔍 분석 중: {name}({symbol}) ...")
                        prices = client.get_krx_daily_prices(symbol)
                        if not prices:
                            print(f"     ❌ {name}: 가격 데이터를 불러올 수 없습니다.")
                            continue
                            
                        analysis = analyze_daily_prices(prices)
                        action = analysis.get("action")
                        score = analysis.get("buy_score", 0)
                        current_price = analysis.get("price", 0)
                        
                        if action == "매수 검토" and score >= 2:
                            # 현금 한도 내에서 1주 매수 테스트 (실전에서는 비중 계산 필요)
                            if cash >= current_price:
                                print(f"  🎯 매수 포착! {name}({symbol}): 점수 {score}점 -> 시장가 1주 매수 실행!")
                                try:
                                    client.place_order("KRX", symbol, "buy", 1, 0, "market")
                                    cash -= current_price # 가계산
                                    print(f"     ✅ 매수 완료!")
                                except Exception as e:
                                    print(f"     ❌ 매수 에러: {e}")
                                
                                time.sleep(1.5)
                            
                            # 한 번 루프에 최대 1종목만 새로 사도록 제한 (모의투자 API 과부하 방지)
                            break 
                            
                    except Exception as e:
                        print(f"  ⚠️ {name}({symbol}) 분석 중 에러: {e}")
                        # API 속도 제한에 걸렸을 가능성이 높으므로 5초 추가 휴식
                        time.sleep(5.0)
                        continue
                    
        except Exception as e:
            print(f"⚠️ 봇 실행 중 에러 발생: {e}")
            
        print("💤 30초 대기 후 다시 모니터링합니다...\n")
        time.sleep(30) # 30초마다 루프 (실전에서는 1~5분 권장)

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n🛑 자동 매매 봇이 사용자에 의해 종료되었습니다.")
