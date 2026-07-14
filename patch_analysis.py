import re

with open('app/analysis.py', 'r') as f:
    content = f.read()

# Extract analyze_daily_prices
match = re.search(r'def analyze_daily_prices\(.*?\n\s*\}\n', content, re.DOTALL)
if match:
    func_code = match.group(0)
else:
    print("Function not found!")
    exit(1)

# Modify signature
func_code = func_code.replace('def analyze_daily_prices(', 'def analyze_daily_prices_bear_market(')
func_code = func_code.replace('daily_prices: List[Dict[str, Any]], ', 'daily_prices: List[Dict[str, Any]], \n    market_index_prices: Optional[List[Dict[str, Any]]] = None, ')

# Apply Method 1 logic
# 1. Weekly Trend Filter (Hard Filter)
weekly_logic = '''
    if weekly_trend.get("is_bullish") == False or (weekly_trend.get("close") and weekly_trend.get("sma_5") and weekly_trend["close"] < weekly_trend["sma_5"]):
        # 주봉 5주선 아래면 즉시 매수 검토 제외
        pass # Handle this at the end by zeroing out score
'''
# Actually we can do it inside:
# Replace the existing weekly trend scoring:
old_weekly = '''    # [8] 주봉 추세 확인
    ws = weekly_trend["status"]
    if ws == "bullish":
        add_score("buy", "weekly_bullish", 1, "최근 완성 주봉 기준 뚜렷한 상승세입니다.")
    elif ws == "bearish":
        add_score("caution", "weekly_bearish", 0, "최근 완성 주봉 기준 하락세에 있습니다.")
    elif ws == "neutral":
        add_score("caution", "weekly_neutral", 0, "최근 완성 주봉 기준 횡보장 또는 혼조세입니다.")
    elif ws == "insufficient_data":
        add_score("caution", "weekly_insufficient", 0, "주봉 데이터가 부족해 추세 확인을 제외했습니다.")'''

new_weekly = '''    # [8] 주봉 추세 확인 (Hard Filter)
    ws = weekly_trend["status"]
    weekly_pass = False
    if ws == "bullish":
        add_score("buy", "weekly_bullish", 1, "최근 완성 주봉 기준 뚜렷한 상승세입니다.")
        weekly_pass = True
    elif ws == "insufficient_data":
        add_score("caution", "weekly_insufficient", 0, "주봉 데이터가 부족해 추세 확인을 제외했습니다.")
        weekly_pass = True # 데이터가 없으면 일단 통과 (선택)
    else:
        add_score("sell_risk", "weekly_bearish", 99, "주봉 5주선 아래에 위치하므로 매수 검토 대상에서 즉시 제외합니다.")
        weekly_pass = False'''
func_code = func_code.replace(old_weekly, new_weekly)

# 2. Market Index Filter
market_logic = '''
    # [0] 시장 지수 필터 (Market Filter)
    is_bear_market = False
    if market_index_prices and len(market_index_prices) >= 20:
        index_frame = _create_indicator_frame(market_index_prices)
        if not index_frame.empty:
            idx_latest = index_frame.iloc[-1]
            if idx_latest["close"] < idx_latest["sma_20"]:
                is_bear_market = True
    
    buy_score_threshold = 7 if is_bear_market else config.buy_min_score
'''
# Insert after score_breakdown = []
func_code = func_code.replace('    score_breakdown = []\n', '    score_breakdown = []\n' + market_logic + '\n')

# 3. 돌파 매매 가중치 및 거래량 기준 변경
# 거래량: 1.5 -> 2.5
old_vol = 'if latest["volume_ratio"] >= config.volume_surge_ratio:'
new_vol = 'if latest["volume_ratio"] >= 2.5:'
func_code = func_code.replace(old_vol, new_vol)

old_breakout_vol = 'is_breakout and latest["volume_ratio"] >= config.volume_surge_ratio:'
new_breakout_vol = 'is_breakout and latest["volume_ratio"] >= 2.5:'
func_code = func_code.replace(old_breakout_vol, new_breakout_vol)

# 돌파점수: 2 -> 1
old_breakout_score = 'add_score("buy", "resistance55_breakout", 2, "55일 전고점 돌파와 거래량 증가가 동시에 확인됩니다.")'
new_breakout_score = 'add_score("buy", "resistance55_breakout", 1, "55일 전고점 돌파와 대량 거래량(2.5배)이 동시에 확인됩니다.")'
func_code = func_code.replace(old_breakout_score, new_breakout_score)

# 4. 판정 로직
old_decision = '''    if sell_risk_score >= config.sell_risk_score:
        action = "매도 검토"
    elif buy_score >= config.buy_min_score and sell_risk_score <= 1:
        action = "매수 검토"
    else:
        action = "관망"'''
new_decision = '''    if sell_risk_score >= config.sell_risk_score:
        action = "매도 검토"
    elif not weekly_pass:
        action = "관망"
        buy_score = 0 # 강제 0점 처리
    elif buy_score >= buy_score_threshold and sell_risk_score <= 1:
        action = "매수 검토"
    else:
        action = "관망"'''
func_code = func_code.replace(old_decision, new_decision)

# 5. 익절 라인
old_target = 'target_price = current_price * 1.10'
new_target = 'target_price = current_price * 1.05 # 하락장 방어: 목표가 +5%로 하향 조정'
func_code = func_code.replace(old_target, new_target)
func_code = func_code.replace('current_price * 1.03', 'current_price * 1.02') # resistance condition tweak

with open('app/analysis.py', 'a') as f:
    f.write('\n\n' + func_code)

print("Appended analyze_daily_prices_bear_market successfully.")
