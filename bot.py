import os
import time
import datetime
from dotenv import load_dotenv

load_dotenv()
from app.config import get_settings
from app.kis_client import KisClient
from app.analysis import analyze_daily_prices, analyze_daily_prices_by_regime, detect_market_regime, select_defensive_market_index
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
        # 클라우드 환경(UTC)을 고려하여 강제로 한국 시간(KST)으로 변환
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        current_time = now.time()
        
        # 주말(토=5, 일=6) 체크
        if now.weekday() >= 5:
            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🛑 주말입니다. 장이 열리지 않습니다.")
            print("💤 1시간 후 다시 확인합니다...\n")
            time.sleep(3600)
            continue
            
        # 한국 주식 시장 정규장 시간: 09:00 ~ 15:30
        if current_time < datetime.time(9, 0) or current_time >= datetime.time(15, 30):
            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🛑 정규장 시간이 아닙니다. (운영 시간: 평일 09:00 ~ 15:30)")
            print("💤 10분 후 다시 확인합니다...\n")
            time.sleep(600)
            continue

        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 잔고 및 시장 모니터링 중...")
        
        try:
            # 1. 계좌 잔고 및 보유 주식 확인
            balance = client.get_balance()
            cash = balance.get("orderable_cash", 0)
            holdings = balance.get("stocks", [])
            daily_loss_percent = client.risk_manager.update_equity(
                "KRX", balance.get("total_evaluated_amount", 0)
            )
            
            print(f"💰 주문 가능 현금: {cash:,.0f}원 | 📦 보유 종목 수: {len(holdings)}개 | 당일 손익: {daily_loss_percent:.2f}%")
            try:
                reconciliation = client.reconcile_today_orders("KRX")
                print(f"🧾 주문 대사: 추적 {reconciliation['tracked_orders']}건 / 갱신 {reconciliation['updated_orders']}건")
            except Exception as error:
                print(f"⚠️ 주문 대사 보류: {error}")
            
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
                    client.place_order("KRX", symbol, "sell", qty, 0, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                    notifier.send_message(f"📈 [목표가 익절] {name}({symbol})\n수량: {qty}주\n가격: {current_price:,.0f}원")
                elif current_price <= stop_loss:
                    print(f"  👉 📉 손절가 이탈! {name} {qty}주 시장가 매도 (손절) 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                    notifier.send_message(f"📉 [손절가 이탈] {name}({symbol})\n수량: {qty}주\n가격: {current_price:,.0f}원")
                elif action == "매도 검토":
                    print(f"  👉 ⚠️ 위험 신호 포착! {name} {qty}주 시장가 매도 실행!")
                    client.place_order("KRX", symbol, "sell", qty, 0, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                    notifier.send_message(f"⚠️ [위험 신호 매도] {name}({symbol})\n수량: {qty}주\n가격: {current_price:,.0f}원")
                
            
            # 3. 매수 로직 (현금이 있을 때만)
            if cash > 100000: # 최소 10만원 이상 있을 때만 스캔
                print("\n📉 KOSPI·KOSDAQ 시장 지수 조회 중...")
                index_prices = {
                    "KOSPI": client.get_krx_index_daily_prices("KOSPI"),
                    "KOSDAQ": client.get_krx_index_daily_prices("KOSDAQ"),
                }
                # 모의투자에서는 종목 시장구분 API가 지원되지 않아 두 지수 중 더 보수적인 국면을 적용합니다.
                market_name, market_index_prices = select_defensive_market_index(index_prices)
                print(f"  적용 시장 기준: {market_name} ({detect_market_regime(market_index_prices).name})")
                
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
                
                success_list = []
                fail_list = []
                buy_logs = []
                
                print("  [", end="", flush=True)
                for cand in final_candidates:
                    # KIS API 국내주식 거래량 순위 응답 키 처리
                    symbol = cand.get("mksc_shrn_iscd") or cand.get("symb") or cand.get("pdno")
                    name = cand.get("hts_kor_isnm") or cand.get("knam") or cand.get("name")
                    
                    if not symbol:
                        continue
                        
                    # 이미 보유 중이면 패스
                    if any(h["symbol"] == symbol for h in holdings):
                        continue
                        
                    try:
                        print(".", end="", flush=True)
                        prices = client.get_krx_daily_prices(symbol)
                        if not prices:
                            fail_list.append(f"{name}({symbol}): 가격 데이터 없음")
                            continue
                            
                        analysis = analyze_daily_prices_by_regime(prices, market_index_prices=market_index_prices)
                        client.risk_manager.record_analysis("KRX", symbol, analysis)
                        success_list.append(f"{name}")
                        
                        action = analysis.get("action")
                        score = analysis.get("buy_score", 0)
                        current_price = analysis.get("price", 0)
                        
                        if action == "매수 검토" and score >= 2:
                            sizing = client.risk_manager.calculate_position_size(
                                cash, current_price, analysis.get("stop_loss_price", 0), "KRX"
                            )
                            qty = sizing["quantity"]
                            target_amount = qty * current_price
                            
                            if qty > 0:
                                buy_msg = f"🎯 매수 포착! {name}({symbol}): 점수 {score}점 -> 목표금액 {target_amount:,.0f}원 ({qty}주) 매수 실행!"
                                try:
                                    client.risk_manager.assert_portfolio_capacity(len(holdings))
                                    liquidity = client.risk_manager.assess_liquidity(client.get_order_book("KRX", symbol))
                                    if not liquidity["allowed"]:
                                        raise RuntimeError(liquidity["reason"])
                                    client.place_order("KRX", symbol, "buy", qty, 0, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                                    cash -= (current_price * qty) # 가계산
                                    buy_msg += " ✅ 완료"
                                    notifier.send_message(f"🔥 [강력 매수] {name}({symbol})\n점수: {score}점\n매수가: {current_price:,.0f}원\n수량: {qty}주")
                                except Exception as e:
                                    buy_msg += f" ❌ 실패 ({e})"
                                buy_logs.append(buy_msg)
                                
                            # 한 번 루프에 최대 1종목만 새로 사도록 제한 (모의투자 API 과부하 방지)
                            break 
                            
                    except Exception as e:
                        fail_list.append(f"{name}({symbol}): {e}")
                        continue
                
                print("] 스캔 완료\n")
                
                # 로그 요약 출력
                if success_list:
                    print(f"  ✅ 분석 성공 ({len(success_list)}종목): {', '.join(success_list)}")
                if fail_list:
                    print(f"  ❌ 분석 실패/제외 ({len(fail_list)}종목):")
                    for fail in fail_list:
                        print(f"     - {fail}")
                for blog in buy_logs:
                    print(f"  {blog}")
                    
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
