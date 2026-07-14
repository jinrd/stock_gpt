import os
import time
import datetime
from dotenv import load_dotenv

load_dotenv()
from app.config import get_settings
from app.kis_client import KisClient
from app.analysis import analyze_daily_prices, analyze_daily_prices_bear_market
from notifier import TelegramNotifier

def run_bot():
    # 봇은 무조건 모의투자(MOCK_APP_KEY) 환경으로 구동
    settings = get_settings(force_mock=True)
    client = KisClient(settings)
    notifier = TelegramNotifier()
    
    print("=" * 50)
    print("🤖 StockPro 자동 매매 봇 작동 시작 (모의투자)")
    print("=" * 50)
    notifier.send_message("🚀 StockPro 자동 매매 봇이 정상적으로 시작되었습니다. (모의투자)")
    
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
                    notifier.send_message(f"📈 [목표가 익절] {name}({symbol})\n수량: {qty}주\n가격: {current_price:,.0f}원")
                    time.sleep(1.5)
                elif current_price <= stop_loss:
                    print(f"  👉 📉 손절가 이탈! {name} {qty}주 시장가 매도 (손절) 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market")
                    notifier.send_message(f"📉 [손절가 이탈] {name}({symbol})\n수량: {qty}주\n가격: {current_price:,.0f}원")
                    time.sleep(1.5)
                elif action == "매도 검토":
                    print(f"  👉 ⚠️ 위험 신호 포착! {name} {qty}주 시장가 매도 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market")
                    notifier.send_message(f"⚠️ [위험 신호 매도] {name}({symbol})\n수량: {qty}주\n가격: {current_price:,.0f}원")
                    time.sleep(1.5)
                
                time.sleep(0.5) # API 호출 제한 방지
            
            # 3. 매수 로직 (현금이 있을 때만)
            if cash > 100000: # 최소 10만원 이상 있을 때만 스캔
                print("\n📉 KOSDAQ 시장 지수 조회 중...")
                market_index_prices = client.get_krx_index_daily_prices("KOSDAQ")
                time.sleep(2.0)
                
                print("\n🔎 신규 매수 유망 종목 스캔 중...")
                
                # 거래량 100만주 이상, 가격 1000~100000원 종목 검색
                candidates = client.search_krx_stocks(
                    minimum_price=1000,
                    maximum_price=100000,
                    minimum_volume=1000000
                )
                candidates = candidates[:20] # 상위 20개만
                
                # 대장주 고정 리스트 (필수 분석)
                blue_chips = [
                    {"mksc_shrn_iscd": "005930", "hts_kor_isnm": "삼성전자"},
                    {"mksc_shrn_iscd": "000660", "hts_kor_isnm": "SK하이닉스"},
                    {"mksc_shrn_iscd": "373220", "hts_kor_isnm": "LG에너지솔루션"},
                    {"mksc_shrn_iscd": "005490", "hts_kor_isnm": "POSCO홀딩스"},
                    {"mksc_shrn_iscd": "006400", "hts_kor_isnm": "삼성SDI"},
                    {"mksc_shrn_iscd": "005380", "hts_kor_isnm": "현대차"},
                    {"mksc_shrn_iscd": "000270", "hts_kor_isnm": "기아"},
                    {"mksc_shrn_iscd": "207940", "hts_kor_isnm": "삼성바이오로직스"},
                    {"mksc_shrn_iscd": "068270", "hts_kor_isnm": "셀트리온"},
                    {"mksc_shrn_iscd": "035420", "hts_kor_isnm": "NAVER"},
                    {"mksc_shrn_iscd": "035720", "hts_kor_isnm": "카카오"},
                    {"mksc_shrn_iscd": "105560", "hts_kor_isnm": "KB금융"}
                ]
                
                # 기존 검색 결과와 필수 분석 리스트 병합 (중복 제거)
                seen_symbols = set()
                final_candidates = []
                
                for cand in blue_chips + candidates:
                    sym = cand.get("mksc_shrn_iscd") or cand.get("symb") or cand.get("pdno")
                    if sym and sym not in seen_symbols:
                        seen_symbols.add(sym)
                        final_candidates.append(cand)
                
                for cand in final_candidates:
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
                            
                        # 하락장 맞춤형 신규 함수 사용
                        analysis = analyze_daily_prices_bear_market(prices, market_index_prices=market_index_prices)
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
                                    notifier.send_message(f"🔥 [강력 매수] {name}({symbol})\n점수: {score}점\n매수가: {current_price:,.0f}원\n수량: 1주")
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
            notifier.send_message(f"❗ [시스템 에러]\n봇 실행 중 문제가 발생했습니다.\n내용: {e}")
            
        print("💤 30초 대기 후 다시 모니터링합니다...\n")
        time.sleep(30) # 30초마다 루프 (실전에서는 1~5분 권장)

if __name__ == "__main__":
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n🛑 자동 매매 봇이 사용자에 의해 종료되었습니다.")
