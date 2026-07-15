import os
import time
import datetime
from dotenv import load_dotenv

load_dotenv()
from app.config import get_settings
from app.kis_client import KisClient
from app.analysis import analyze_daily_prices, analyze_daily_prices_by_regime
from notifier import TelegramNotifier

def run_bot():
    # 봇은 무조건 모의투자(MOCK_APP_KEY) 환경으로 구동
    settings = get_settings(force_mock=True)
    client = KisClient(settings)
    notifier = TelegramNotifier()
    
    print("=" * 50)
    print("🤖 StockPro 나스닥 자동 매매 봇 작동 시작 (모의투자)")
    print("=" * 50)
    notifier.send_message("🚀 StockPro 나스닥 자동 매매 봇이 정상적으로 시작되었습니다. (모의투자)")
    
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
            
        # 나스닥 주식 시장 정규장 시간 (썸머타임 기준 KST 22:30 ~ 05:00)
        # 썸머타임 미적용 시 23:30 ~ 06:00 이나, 우선 22:30 ~ 05:00 범위로 러프하게 설정
        if current_time >= datetime.time(5, 0) and current_time < datetime.time(22, 30):
            print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 🛑 정규장 시간이 아닙니다. (미국 나스닥 운영 시간: 22:30 ~ 05:00 KST)")
            print("💤 10분 후 다시 확인합니다...\n")
            time.sleep(600)
            continue

        print(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S')}] 나스닥 잔고 및 시장 모니터링 중...")
        
        try:
            # 1. 해외 계좌 잔고 및 보유 주식 확인
            balance = client.get_nasdaq_balance()
            cash = balance.get("orderable_cash", 0) # USD
            holdings = balance.get("stocks", [])
            daily_loss_percent = client.risk_manager.update_equity(
                "NASD", balance.get("total_evaluated_amount", 0)
            )
            
            print(f"💰 주문 가능 현금: ${cash:,.2f} | 📦 보유 종목 수: {len(holdings)}개 | 당일 손익: {daily_loss_percent:.2f}%")
            
            # 2. 매도 로직 (보유 종목 검사)
            for stock in holdings:
                symbol = stock["symbol"]
                name = stock["name"]
                qty = stock["quantity"]
                current_price = stock["current_price"]
                
                # 차트 분석 가져오기
                prices = client.get_daily_prices("NAS", symbol)
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
                    client.place_order("NASD", symbol, "sell", qty, current_price, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                    notifier.send_message(f"📈 [미국장 목표가 익절] {name}({symbol})\n수량: {qty}주\n가격: ${current_price:,.2f}")
                elif current_price <= stop_loss:
                    print(f"  👉 📉 손절가 이탈! {name} {qty}주 시장가 매도 (손절) 실행!")
                    client.place_order("NASD", symbol, "sell", qty, current_price, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                    notifier.send_message(f"📉 [미국장 손절가 이탈] {name}({symbol})\n수량: {qty}주\n가격: ${current_price:,.2f}")
                elif action == "매도 검토":
                    print(f"  👉 ⚠️ 위험 신호 포착! {name} {qty}주 시장가 매도 실행!")
                    client.place_order("NASD", symbol, "sell", qty, current_price, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                    notifier.send_message(f"⚠️ [미국장 위험 신호 매도] {name}({symbol})\n수량: {qty}주\n가격: ${current_price:,.2f}")
                
            
            # 3. 매수 로직 (현금이 있을 때만, 달러 기준)
            if cash > 100: # 최소 $100 이상 있을 때만 스캔
                print("\n📉 나스닥 100 지수(QQQ) 조회 중...")
                try:
                    market_index_prices = client.get_daily_prices("NAS", "QQQ")
                except Exception:
                    market_index_prices = []
                
                print("\n🔎 신규 매수 유망 나스닥 우량주 스캔 중...")
                
                # 나스닥 우량주 고정 리스트 (필수 분석)
                final_candidates = [
                    {"symb": "AAPL", "name": "Apple"},
                    {"symb": "MSFT", "name": "Microsoft"},
                    {"symb": "NVDA", "name": "NVIDIA"},
                    {"symb": "AMZN", "name": "Amazon"},
                    {"symb": "GOOGL", "name": "Alphabet Class A"},
                    {"symb": "META", "name": "Meta Platforms"},
                    {"symb": "TSLA", "name": "Tesla"},
                    {"symb": "AVGO", "name": "Broadcom"},
                    {"symb": "COST", "name": "Costco"},
                    {"symb": "NFLX", "name": "Netflix"},
                    {"symb": "AMD", "name": "AMD"},
                    {"symb": "INTC", "name": "Intel"},
                    {"symb": "QCOM", "name": "Qualcomm"},
                    {"symb": "ADBE", "name": "Adobe"},
                    {"symb": "CSCO", "name": "Cisco"}
                ]
                
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
                        prices = client.get_daily_prices("NAS", symbol)
                        if not prices:
                            fail_list.append(f"{name}({symbol}): 가격 데이터 없음")
                            continue
                            
                        analysis = analyze_daily_prices_by_regime(prices, market_index_prices=market_index_prices)
                        client.risk_manager.record_analysis("NASD", symbol, analysis)
                        success_list.append(f"{name}")
                        
                        action = analysis.get("action")
                        score = analysis.get("buy_score", 0)
                        current_price = analysis.get("price", 0)
                        
                        if action == "매수 검토" and score >= 2:
                            # 1. 점수에 비례한 목표 매수 금액 설정 (1점당 150달러)
                            target_amount = score * 150.0
                            
                            # 2. 현재 계좌의 주문 가능 현금을 초과하지 않도록 보정
                            target_amount = min(target_amount, cash)
                            
                            # 3. 목표 금액으로 살 수 있는 수량 계산
                            qty = int(target_amount // current_price)
                            
                            if qty > 0:
                                buy_msg = f"🎯 매수 포착! {name}({symbol}): 점수 {score}점 -> 목표금액 ${target_amount:,.2f} ({qty}주) 매수 실행!"
                                try:
                                    client.risk_manager.assert_portfolio_capacity(len(holdings))
                                    client.place_order("NASD", symbol, "buy", qty, current_price, "market", reference_price=current_price, daily_loss_percent=daily_loss_percent)
                                    cash -= (current_price * qty) # 가계산
                                    buy_msg += " ✅ 완료"
                                    notifier.send_message(f"🔥 [미국장 강력 매수] {name}({symbol})\n점수: {score}점\n매수가: ${current_price:,.2f}\n수량: {qty}주")
                                except Exception as e:
                                    buy_msg += f" ❌ 실패 ({e})"
                                buy_logs.append(buy_msg)
                                
                            # 한 번 루프에 최대 1종목만 새로 사도록 제한
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
