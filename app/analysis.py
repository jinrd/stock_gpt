from typing import Any, Dict, List, Optional
import pandas as pd
from dataclasses import dataclass

@dataclass
class StrategyConfig:
    volume_surge_ratio: float = 1.5
    volume_low_ratio: float = 0.7
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    atr_risk_percent: float = 6.0
    disparity_caution: float = 115.0
    disparity_overheated: float = 120.0
    vp_lookback_days: int = 55
    vp_bin_count: int = 20
    buy_min_score: int = 5
    sell_risk_score: int = 3
    max_stop_loss_percent: float = 10.0

def _to_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(str(value).replace(",", ""))

def _round_or_none(value: Any, digits: int = 2):
    if pd.isna(value):
        return None
    return round(float(value), digits)

def _create_indicator_frame(daily_prices: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "date": item.get("xymd"),
            "open": _to_number(item.get("open")),
            "high": _to_number(item.get("high")),
            "low": _to_number(item.get("low")),
            "close": _to_number(item.get("clos")),
            "volume": _to_number(item.get("tvol")),
        }
        for item in daily_prices
    ]

    frame = pd.DataFrame(rows)
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["date_dt"] = pd.to_datetime(frame["date"], format="%Y%m%d")

    # 추세
    frame["sma_20"] = frame["close"].rolling(window=20).mean()
    frame["sma_60"] = frame["close"].rolling(window=60).mean()
    frame["sma_20_slope_5d"] = (frame["sma_20"] / frame["sma_20"].shift(5) - 1) * 100

    # 거래량
    frame["volume_avg_20"] = frame["volume"].rolling(window=20).mean()
    frame["volume_ratio"] = frame["volume"] / frame["volume_avg_20"]

    # RSI
    change = frame["close"].diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)

    average_gain = gain.ewm(alpha=1 / 14, min_periods=14).mean()
    average_loss = loss.ewm(alpha=1 / 14, min_periods=14).mean()

    relative_strength = average_gain / average_loss
    frame["rsi_14"] = 100 - (100 / (1 + relative_strength))

    # MACD
    ema_12 = frame["close"].ewm(span=12, adjust=False).mean()
    ema_26 = frame["close"].ewm(span=26, adjust=False).mean()

    frame["macd"] = ema_12 - ema_26
    frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False).mean()

    # 볼린저 밴드
    frame["bb_middle"] = frame["close"].rolling(window=20).mean()
    frame["bb_std"] = frame["close"].rolling(window=20).std()
    frame["bb_upper"] = frame["bb_middle"] + 2 * frame["bb_std"]
    frame["bb_lower"] = frame["bb_middle"] - 2 * frame["bb_std"]

    # ATR(14)
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    frame["atr_14"] = true_range.rolling(window=14).mean()
    frame["atr_percent"] = (frame["atr_14"] / frame["close"]) * 100

    # 지지·저항 및 전고점 돌파
    frame["support_20"] = frame["low"].rolling(window=20).min().shift(1)
    frame["resistance_20"] = frame["high"].rolling(window=20).max().shift(1)
    frame["resistance_55"] = frame["high"].rolling(window=55).max().shift(1)

    # 이격도
    frame["disparity_20"] = (frame["close"] / frame["sma_20"]) * 100

    return frame


def _calculate_volume_profile(frame: pd.DataFrame, config: StrategyConfig) -> Dict[str, Any]:
    if frame.empty or len(frame) < config.vp_lookback_days:
        return {
            "status": "insufficient_data",
            "lookback_days": config.vp_lookback_days,
            "bin_count": config.vp_bin_count,
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "current_price_position": None,
            "is_approximation": True,
        }
    
    recent_frame = frame.tail(config.vp_lookback_days).copy()
    recent_frame["typical_price"] = (recent_frame["high"] + recent_frame["low"] + recent_frame["close"]) / 3
    
    min_price = recent_frame["typical_price"].min()
    max_price = recent_frame["typical_price"].max()
    
    if min_price == max_price:
        return {
            "status": "zero_range",
            "lookback_days": config.vp_lookback_days,
            "bin_count": config.vp_bin_count,
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "current_price_position": None,
            "is_approximation": True,
        }
        
    bins = pd.cut(recent_frame["typical_price"], bins=config.vp_bin_count)
    vp = recent_frame.groupby(bins, observed=False)["volume"].sum()
    
    poc_bin = vp.idxmax()
    if pd.isna(poc_bin):
        poc_price, poc_low, poc_high = None, None, None
    elif isinstance(poc_bin, pd.Interval):
        poc_price = poc_bin.mid
        poc_low = poc_bin.left
        poc_high = poc_bin.right
    elif isinstance(poc_bin, str) and ',' in poc_bin:
        try:
            clean_str = poc_bin.strip("()[] ")
            parts = clean_str.split(',')
            poc_low = float(parts[0])
            poc_high = float(parts[1])
            poc_price = (poc_low + poc_high) / 2
        except:
            poc_price, poc_low, poc_high = None, None, None
    else:
        try:
            poc_price = float(poc_bin)
            poc_low = poc_price
            poc_high = poc_price
        except:
            poc_price, poc_low, poc_high = None, None, None
            
    current_price = frame.iloc[-1]["close"]
    if poc_high is None or poc_low is None:
        position = None
    elif current_price > poc_high:
        position = "above"
    elif current_price < poc_low:
        position = "below"
    else:
        position = "inside"
        
    return {
        "status": "success",
        "lookback_days": config.vp_lookback_days,
        "bin_count": config.vp_bin_count,
        "poc_price": poc_price,
        "poc_low": poc_low,
        "poc_high": poc_high,
        "current_price_position": position,
        "is_approximation": True
    }


def _get_weekly_trend(frame: pd.DataFrame, is_current_week_closed: bool = False) -> Dict[str, Any]:
    if frame.empty:
        return {
            "status": "insufficient_data",
            "is_bullish": None,
            "required_weeks": 7,
            "available_weeks": 0,
            "close": None,
            "sma_5": None,
            "sma_5_slope": None,
            "current_week_excluded": False,
            "latest_completed_week": None,
        }

    weekly = (
        frame.set_index("date_dt")
        .resample("W-FRI")
        .agg({"close": "last"})
        .dropna()
    )
    
    if weekly.empty:
        return {
            "status": "insufficient_data",
            "is_bullish": None,
            "required_weeks": 7,
            "available_weeks": 0,
            "close": None,
            "sma_5": None,
            "sma_5_slope": None,
            "current_week_excluded": False,
            "latest_completed_week": None,
        }

    last_daily_date = frame["date_dt"].iloc[-1]
    last_week_end = weekly.index[-1]
    
    current_week_excluded = False
    
    is_incomplete = False
    if last_daily_date < last_week_end:
        is_incomplete = True
    elif last_daily_date == last_week_end and not is_current_week_closed:
        is_incomplete = True

    if is_incomplete:
        current_week_excluded = True
        weekly = weekly.iloc[:-1]

    available_weeks = len(weekly)

    if available_weeks < 7:
        return {
            "status": "insufficient_data",
            "is_bullish": None,
            "required_weeks": 7,
            "available_weeks": available_weeks,
            "close": None,
            "sma_5": None,
            "sma_5_slope": None,
            "current_week_excluded": current_week_excluded,
            "latest_completed_week": None,
        }

    weekly["sma_5"] = weekly["close"].rolling(window=5).mean()
    weekly["sma_5_slope"] = (weekly["sma_5"] / weekly["sma_5"].shift(2) - 1) * 100

    latest = weekly.iloc[-1]
    if hasattr(latest.name, "strftime"):
        latest_completed_week = latest.name.strftime("%Y-%m-%d")
    else:
        latest_completed_week = str(latest.name) if pd.notna(latest.name) else None
    if pd.isna(latest["sma_5"]) or pd.isna(latest["sma_5_slope"]):
        status = "insufficient_data"
        is_bullish = None
    elif latest["close"] > latest["sma_5"] and latest["sma_5_slope"] > 0:
        status = "bullish"
        is_bullish = True
    elif latest["close"] < latest["sma_5"] and latest["sma_5_slope"] < 0:
        status = "bearish"
        is_bullish = False
    else:
        status = "neutral"
        is_bullish = None

    return {
        "status": status,
        "is_bullish": is_bullish,
        "required_weeks": 7,
        "available_weeks": available_weeks,
        "close": _round_or_none(latest["close"]),
        "sma_5": _round_or_none(latest["sma_5"]),
        "sma_5_slope": _round_or_none(latest["sma_5_slope"], 2),
        "current_week_excluded": current_week_excluded,
        "latest_completed_week": latest_completed_week,
    }


def analyze_daily_prices(
    daily_prices: List[Dict[str, Any]], 
    config: Optional[StrategyConfig] = None,
    is_market_open: bool = False,
    use_latest_incomplete_candle: bool = False
) -> Dict[str, Any]:
    if config is None:
        config = StrategyConfig()
        
    candle_status = "completed"
    
    # 1. 일봉 데이터 완성 여부(장중 처리)
    if is_market_open and not use_latest_incomplete_candle:
        if len(daily_prices) > 1:
            daily_prices = daily_prices[:-1]
            candle_status = "incomplete_filtered"
        else:
            raise ValueError("분석에 필요한 충분한 일봉 데이터가 없습니다 (장중 데이터 제외됨).")
    elif is_market_open and use_latest_incomplete_candle:
        candle_status = "incomplete_included"

    if len(daily_prices) < 60:
        raise ValueError("확장 분석에는 최소 60일치 일봉이 필요합니다.")

    frame = _create_indicator_frame(daily_prices)
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    
    is_current_week_closed = not is_market_open
    weekly_trend = _get_weekly_trend(frame, is_current_week_closed=is_current_week_closed)
    
    vp_data = _calculate_volume_profile(frame, config)

    score_breakdown = []
    
    def add_score(type_: str, name: str, delta: int, reason: str):
        score_breakdown.append({
            "type": type_,
            "name": name,
            "delta": delta,
            "reason": reason
        })

    # [1] 가격 위치와 이평선 기울기
    if latest["close"] > latest["sma_20"]:
        add_score("buy", "price_above_sma20", 1, "현재가가 20일 이동평균선 위에 있습니다.")
    else:
        add_score("sell_risk", "price_below_sma20", 1, "현재가가 20일 이동평균선 아래에 있습니다.")

    if latest["sma_20"] > latest["sma_60"] and latest["sma_20_slope_5d"] > 0:
        add_score("buy", "sma20_above_sma60_rising", 2, "20일선이 60일선 위에서 상승 기울기를 유지합니다.")
    elif latest["close"] < latest["sma_60"]:
        add_score("sell_risk", "price_below_sma60", 2, "현재가가 60일 이동평균선을 이탈했습니다.")
    else:
        add_score("caution", "weak_medium_trend", 0, "중기 이동평균 추세가 충분히 강하지 않습니다.")

    # [2] 거래량 검증
    if latest["volume_ratio"] >= config.volume_surge_ratio:
        add_score("buy", "volume_surge", 1, f"거래량이 20일 평균의 {latest['volume_ratio']:.2f}배입니다.")
    elif latest["volume_ratio"] < config.volume_low_ratio:
        add_score("caution", "low_volume", 0, "거래량이 평균보다 낮아 신호의 신뢰도가 약합니다.")

    # [3] MACD 및 RSI
    if latest["macd"] > latest["macd_signal"]:
        add_score("buy", "macd_above_signal", 1, "MACD가 신호선 위에 있어 단기 모멘텀이 우세합니다.")
    else:
        add_score("sell_risk", "macd_below_signal", 1, "MACD가 신호선 아래에 있습니다.")

    if 50 <= latest["rsi_14"] < config.rsi_overbought:
        add_score("buy", "rsi_momentum", 1, "RSI가 과열 전의 상승 모멘텀 구간에 있습니다.")
    elif latest["rsi_14"] >= config.rsi_overbought:
        add_score("caution", "rsi_overbought", 0, f"RSI가 {config.rsi_overbought} 이상으로 단기 과열 가능성이 있습니다.")
        if latest["close"] < previous["close"]:
            add_score("sell_risk", "rsi_reversal", 1, "과열 구간에서 가격 하락 반전이 나타났습니다.")
    elif latest["rsi_14"] <= config.rsi_oversold:
        add_score("caution", "rsi_oversold", 0, f"RSI가 {config.rsi_oversold} 이하로 강한 하락 추세일 수 있습니다.")

    # [4] 전고점 돌파와 볼린저 밴드
    is_breakout = pd.notna(latest["resistance_55"]) and latest["close"] > latest["resistance_55"]

    if is_breakout and latest["volume_ratio"] >= config.volume_surge_ratio:
        add_score("buy", "resistance55_breakout", 2, "55일 전고점 돌파와 거래량 증가가 동시에 확인됩니다.")
    elif pd.notna(latest["resistance_20"]) and latest["close"] > latest["resistance_20"]:
        add_score("buy", "resistance20_breakout", 1, "20일 저항선을 상향 돌파했습니다.")

    if latest["close"] > latest["bb_upper"]:
        add_score("caution", "bb_overheated", 0, "볼린저 밴드 상단 위로 올라 단기 과열을 확인해야 합니다.")

    # [5] 지지선 이탈 및 변동성 위험
    if pd.notna(latest["support_20"]) and latest["close"] < latest["support_20"]:
        add_score("sell_risk", "support20_breakdown", 2, "20일 지지선을 이탈했습니다.")

    if latest["atr_percent"] >= config.atr_risk_percent:
        add_score("sell_risk", "high_volatility", 1, f"ATR 기준 일간 변동성이 {latest['atr_percent']:.2f}%로 높습니다.")

    # [6] 매물대 (Volume Profile) 돌파/유지
    poc_breakout = False
    poc_hold_above = False
    poc_breakdown = False
    
    if vp_data["status"] == "success":
        poc_high = vp_data["poc_high"]
        poc_low = vp_data["poc_low"]
        
        poc_breakout = bool(previous["close"] <= poc_high and latest["close"] > poc_high)
        poc_hold_above = bool(previous["close"] > poc_high and latest["close"] > poc_high)
        poc_breakdown = bool(previous["close"] >= poc_low and latest["close"] < poc_low)
        
        if poc_breakout and latest["volume_ratio"] >= config.volume_surge_ratio:
            add_score("buy", "poc_breakout", 1, "최대 매물대(POC)를 대량 거래량과 함께 신규 상향 돌파했습니다.")
        elif poc_hold_above:
            add_score("caution", "poc_hold_above", 0, "최대 매물대(POC) 위에 안착하여 추세를 유지 중입니다.")
        elif poc_breakdown:
            add_score("sell_risk", "poc_breakdown", 1, "최대 매물대(POC) 하단 아래로 무너져 강한 저항이 예상됩니다.")
            
        vp_data["poc_breakout"] = poc_breakout
        vp_data["poc_hold_above"] = poc_hold_above
        vp_data["poc_breakdown"] = poc_breakdown

    # [7] 이격도 (Disparity)
    disparity = latest["disparity_20"]
    if pd.notna(disparity):
        if config.disparity_caution < disparity < config.disparity_overheated:
            add_score("caution", "disparity_caution", 0, f"이격도가 {disparity:.1f}로 주의 구간입니다.")
        elif disparity >= config.disparity_overheated:
            add_score("buy", "disparity_overheated_penalty", -1, "이격도 과열로 인한 매수 점수 페널티입니다.")
            add_score("sell_risk", "disparity_overheated", 1, f"이격도가 {disparity:.1f}로 단기 과열이 심각합니다.")

    # [8] 주봉 추세 확인
    ws = weekly_trend["status"]
    if ws == "bullish":
        add_score("buy", "weekly_bullish", 1, "최근 완성 주봉 기준 뚜렷한 상승세입니다.")
    elif ws == "bearish":
        add_score("caution", "weekly_bearish", 0, "최근 완성 주봉 기준 하락세에 있습니다.")
    elif ws == "neutral":
        add_score("caution", "weekly_neutral", 0, "최근 완성 주봉 기준 횡보장 또는 혼조세입니다.")
    elif ws == "insufficient_data":
        add_score("caution", "weekly_insufficient", 0, "주봉 데이터가 부족해 추세 확인을 제외했습니다.")

    # 총합 계산 (기존 반환값 호환 유지)
    buy_score = 0
    sell_risk_score = 0
    reasons = []
    cautions = []
    sell_signals = []

    for item in score_breakdown:
        if item["type"] == "buy":
            buy_score += item["delta"]
            if item["delta"] > 0:
                reasons.append(item["reason"])
            elif item["delta"] < 0:
                cautions.append(item["reason"])
        elif item["type"] == "sell_risk":
            sell_risk_score += item["delta"]
            if item["delta"] > 0:
                sell_signals.append(item["reason"])
        elif item["type"] == "caution":
            cautions.append(item["reason"])
            
    # buy_score 음수 방지
    buy_score = max(0, buy_score)

    if sell_risk_score >= config.sell_risk_score:
        action = "매도 검토"
    elif buy_score >= config.buy_min_score and sell_risk_score <= 1:
        action = "매수 검토"
    else:
        action = "관망"

    # [9] ATR 손절가 계산
    stop_loss_price = max(0.01, latest["close"] - (2 * latest["atr_14"]))
    atr_stop_loss_percent = ((latest["close"] - stop_loss_price) / latest["close"]) * 100
    
    if atr_stop_loss_percent > config.max_stop_loss_percent:
        cautions.append(f"제시된 손절폭이 현재가 대비 {atr_stop_loss_percent:.1f}%로 매우 큽니다. 비중 조절에 유의하세요.")

    # [10] 권장 매수가 및 목표가 계산
    current_price = latest["close"]
    sma_20 = latest["sma_20"]
    poc_price = vp_data.get("poc_price")
    resistance_20 = latest["resistance_20"]
    
    # 1. 권장 매수가 (눌림목 대기 또는 현재가)
    candidates = []
    if pd.notna(sma_20) and current_price > sma_20:
        candidates.append(sma_20)
    if poc_price and poc_price < current_price:
        candidates.append(poc_price)
        
    if candidates:
        recommended_buy_price = max(candidates) # 가장 가까운 하단 지지선
    else:
        recommended_buy_price = current_price * 0.98 # 지지선이 없으면 2% 조정 시 매수
        
    if recommended_buy_price > current_price or recommended_buy_price < current_price * 0.8:
        recommended_buy_price = current_price
        
    # 2. 1차 목표 매도가 (전고점 또는 10% 수익)
    if pd.notna(resistance_20) and resistance_20 > current_price * 1.03:
        target_price = resistance_20
    else:
        target_price = current_price * 1.10

    return {
        "action": action,
        "score": buy_score,
        "buy_score": buy_score,
        "sell_risk_score": sell_risk_score,
        "latest_date": latest["date"],
        "price": _round_or_none(latest["close"]),
        "recommended_buy_price": _round_or_none(recommended_buy_price),
        "target_price": _round_or_none(target_price),
        "candle_status": candle_status,
        "indicators": {
            "sma_20": _round_or_none(latest["sma_20"]),
            "sma_60": _round_or_none(latest["sma_60"]),
            "sma_20_slope_5d": _round_or_none(latest["sma_20_slope_5d"], 2),
            "volume_avg_20": _round_or_none(latest["volume_avg_20"]),
            "volume_ratio": _round_or_none(latest["volume_ratio"], 2),
            "rsi_14": _round_or_none(latest["rsi_14"]),
            "macd": _round_or_none(latest["macd"], 4),
            "macd_signal": _round_or_none(latest["macd_signal"], 4),
            "bb_upper": _round_or_none(latest["bb_upper"]),
            "bb_middle": _round_or_none(latest["bb_middle"]),
            "bb_lower": _round_or_none(latest["bb_lower"]),
            "atr_14": _round_or_none(latest["atr_14"]),
            "atr_percent": _round_or_none(latest["atr_percent"], 2),
            "support_20": _round_or_none(latest["support_20"]),
            "resistance_20": _round_or_none(latest["resistance_20"]),
            "resistance_55": _round_or_none(latest["resistance_55"]),
            "disparity_20": _round_or_none(latest["disparity_20"], 2),
            "volume_profile_poc": _round_or_none(vp_data.get("poc_price")),
            "volume_profile_low": _round_or_none(vp_data.get("poc_low")),
            "volume_profile_high": _round_or_none(vp_data.get("poc_high")),
        },
        "weekly_trend": weekly_trend,
        "volume_profile": vp_data,
        "stop_loss_price": _round_or_none(stop_loss_price),
        "atr_stop_loss": _round_or_none(stop_loss_price),
        "atr_stop_loss_percent": _round_or_none(atr_stop_loss_percent, 2),
        "score_breakdown": score_breakdown,
        "reasons": reasons,
        "cautions": cautions,
        "sell_signals": sell_signals,
    }

def build_chart_data(daily_prices: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    frame = _create_indicator_frame(daily_prices).tail(100)

    return {
        "labels": frame["date"].tolist(),
        "close": [_round_or_none(value) for value in frame["close"]],
        "sma_20": [_round_or_none(value) for value in frame["sma_20"]],
        "sma_60": [_round_or_none(value) for value in frame["sma_60"]],
        "rsi_14": [_round_or_none(value) for value in frame["rsi_14"]],
    }

def analyze_extra_data(fundamentals: Dict[str, Any], order_book: Dict[str, Any]) -> Dict[str, Any]:
    insights = []
    
    # 1. 펀더멘털 분석 (가치 평가)
    if fundamentals:
        per = fundamentals.get("per", 0)
        pbr = fundamentals.get("pbr", 0)
        eps = fundamentals.get("eps", 0)
        
        if per > 0 and per < 15:
            insights.append({"type": "positive", "msg": f"PER이 {per}배로 시장 평균 대비 저평가 매력이 있습니다."})
        elif per >= 30:
            insights.append({"type": "warning", "msg": f"PER이 {per}배로 다소 고평가되어 있어 주의가 필요합니다."})
            
        if pbr > 0 and pbr < 1:
            insights.append({"type": "positive", "msg": f"PBR이 {pbr}로 청산 가치보다 낮아 안전 마진이 큽니다."})
        elif pbr >= 3:
            insights.append({"type": "warning", "msg": f"PBR이 {pbr}로 자산 가치 대비 높게 평가받고 있습니다."})
            
        if eps > 0:
            insights.append({"type": "positive", "msg": f"EPS가 {eps}로 꾸준한 이익을 내고 있는 흑자 기업입니다."})
        elif eps < 0:
            insights.append({"type": "negative", "msg": "EPS가 적자 상태이므로 펀더멘털 리스크가 존재합니다."})

    # 2. 호가창 분석 (초단기 수급)
    if order_book:
        asks = order_book.get("asks", [])
        bids = order_book.get("bids", [])
        
        total_ask_vol = sum(a["volume"] for a in asks)
        total_bid_vol = sum(b["volume"] for b in bids)
        
        if total_ask_vol > 0 or total_bid_vol > 0:
            ratio = total_bid_vol / total_ask_vol if total_ask_vol > 0 else 999
            
            if ratio < 0.5:
                # 매도 잔량이 2배 이상 많음
                insights.append({"type": "neutral", "msg": "매도 잔량이 많아 위쪽 매물벽이 두터우나, 돌파 시 강한 상승이 나올 수 있습니다."})
            elif ratio > 2.0:
                # 매수 잔량이 2배 이상 많음
                insights.append({"type": "neutral", "msg": "매수 잔량이 많아 하방 지지가 강해 보이나, 주가 하락 시 실망 매물이 나올 수 있습니다."})
            
            if asks:
                max_ask = max(asks, key=lambda x: x["volume"])
                insights.append({"type": "neutral", "msg": f"단기 주요 저항: {max_ask['price']:,}원에 가장 큰 매도 물량이 쌓여있습니다."})
            if bids:
                max_bid = max(bids, key=lambda x: x["volume"])
                insights.append({"type": "neutral", "msg": f"단기 주요 지지: {max_bid['price']:,}원에 가장 큰 매수 대기 물량이 있습니다."})
                
    if not insights:
        insights.append({"type": "neutral", "msg": "충분한 펀더멘털 및 호가 데이터가 없어 분석이 어렵습니다."})
        
    return {"insights": insights}

def analyze_daily_prices_bear_market(
    daily_prices: List[Dict[str, Any]], 
    market_index_prices: Optional[List[Dict[str, Any]]] = None, 
    config: Optional[StrategyConfig] = None,
    is_market_open: bool = False,
    use_latest_incomplete_candle: bool = False
) -> Dict[str, Any]:
    if config is None:
        config = StrategyConfig()
        
    candle_status = "completed"
    
    # 1. 일봉 데이터 완성 여부(장중 처리)
    if is_market_open and not use_latest_incomplete_candle:
        if len(daily_prices) > 1:
            daily_prices = daily_prices[:-1]
            candle_status = "incomplete_filtered"
        else:
            raise ValueError("분석에 필요한 충분한 일봉 데이터가 없습니다 (장중 데이터 제외됨).")
    elif is_market_open and use_latest_incomplete_candle:
        candle_status = "incomplete_included"

    if len(daily_prices) < 60:
        raise ValueError("확장 분석에는 최소 60일치 일봉이 필요합니다.")

    frame = _create_indicator_frame(daily_prices)
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    
    is_current_week_closed = not is_market_open
    weekly_trend = _get_weekly_trend(frame, is_current_week_closed=is_current_week_closed)
    
    vp_data = _calculate_volume_profile(frame, config)

    score_breakdown = []

    # [0] 시장 지수 필터 (Market Filter)
    is_bear_market = False
    if market_index_prices and len(market_index_prices) >= 20:
        index_frame = _create_indicator_frame(market_index_prices)
        if not index_frame.empty:
            idx_latest = index_frame.iloc[-1]
            if idx_latest["close"] < idx_latest["sma_20"]:
                is_bear_market = True
    
    buy_score_threshold = 7 if is_bear_market else config.buy_min_score

    
    def add_score(type_: str, name: str, delta: int, reason: str):
        score_breakdown.append({
            "type": type_,
            "name": name,
            "delta": delta,
            "reason": reason
        })

    # [1] 가격 위치와 이평선 기울기
    if latest["close"] > latest["sma_20"]:
        add_score("buy", "price_above_sma20", 1, "현재가가 20일 이동평균선 위에 있습니다.")
    else:
        add_score("sell_risk", "price_below_sma20", 1, "현재가가 20일 이동평균선 아래에 있습니다.")

    if latest["sma_20"] > latest["sma_60"] and latest["sma_20_slope_5d"] > 0:
        add_score("buy", "sma20_above_sma60_rising", 2, "20일선이 60일선 위에서 상승 기울기를 유지합니다.")
    elif latest["close"] < latest["sma_60"]:
        add_score("sell_risk", "price_below_sma60", 2, "현재가가 60일 이동평균선을 이탈했습니다.")
    else:
        add_score("caution", "weak_medium_trend", 0, "중기 이동평균 추세가 충분히 강하지 않습니다.")

    # [2] 거래량 검증
    if latest["volume_ratio"] >= 2.5:
        add_score("buy", "volume_surge", 1, f"거래량이 20일 평균의 {latest['volume_ratio']:.2f}배입니다.")
    elif latest["volume_ratio"] < config.volume_low_ratio:
        add_score("caution", "low_volume", 0, "거래량이 평균보다 낮아 신호의 신뢰도가 약합니다.")

    # [3] MACD 및 RSI
    if latest["macd"] > latest["macd_signal"]:
        add_score("buy", "macd_above_signal", 1, "MACD가 신호선 위에 있어 단기 모멘텀이 우세합니다.")
    else:
        add_score("sell_risk", "macd_below_signal", 1, "MACD가 신호선 아래에 있습니다.")

    if 50 <= latest["rsi_14"] < config.rsi_overbought:
        add_score("buy", "rsi_momentum", 1, "RSI가 과열 전의 상승 모멘텀 구간에 있습니다.")
    elif latest["rsi_14"] >= config.rsi_overbought:
        add_score("caution", "rsi_overbought", 0, f"RSI가 {config.rsi_overbought} 이상으로 단기 과열 가능성이 있습니다.")
        if latest["close"] < previous["close"]:
            add_score("sell_risk", "rsi_reversal", 1, "과열 구간에서 가격 하락 반전이 나타났습니다.")
    elif latest["rsi_14"] <= config.rsi_oversold:
        add_score("caution", "rsi_oversold", 0, f"RSI가 {config.rsi_oversold} 이하로 강한 하락 추세일 수 있습니다.")

    # [4] 전고점 돌파와 볼린저 밴드
    is_breakout = pd.notna(latest["resistance_55"]) and latest["close"] > latest["resistance_55"]

    if is_breakout and latest["volume_ratio"] >= 2.5:
        add_score("buy", "resistance55_breakout", 1, "55일 전고점 돌파와 대량 거래량(2.5배)이 동시에 확인됩니다.")
    elif pd.notna(latest["resistance_20"]) and latest["close"] > latest["resistance_20"]:
        add_score("buy", "resistance20_breakout", 1, "20일 저항선을 상향 돌파했습니다.")

    if latest["close"] > latest["bb_upper"]:
        add_score("caution", "bb_overheated", 0, "볼린저 밴드 상단 위로 올라 단기 과열을 확인해야 합니다.")

    # [5] 지지선 이탈 및 변동성 위험
    if pd.notna(latest["support_20"]) and latest["close"] < latest["support_20"]:
        add_score("sell_risk", "support20_breakdown", 2, "20일 지지선을 이탈했습니다.")

    if latest["atr_percent"] >= config.atr_risk_percent:
        add_score("sell_risk", "high_volatility", 1, f"ATR 기준 일간 변동성이 {latest['atr_percent']:.2f}%로 높습니다.")

    # [6] 매물대 (Volume Profile) 돌파/유지
    poc_breakout = False
    poc_hold_above = False
    poc_breakdown = False
    
    if vp_data["status"] == "success":
        poc_high = vp_data["poc_high"]
        poc_low = vp_data["poc_low"]
        
        poc_breakout = bool(previous["close"] <= poc_high and latest["close"] > poc_high)
        poc_hold_above = bool(previous["close"] > poc_high and latest["close"] > poc_high)
        poc_breakdown = bool(previous["close"] >= poc_low and latest["close"] < poc_low)
        
        if poc_breakout and latest["volume_ratio"] >= config.volume_surge_ratio:
            add_score("buy", "poc_breakout", 1, "최대 매물대(POC)를 대량 거래량과 함께 신규 상향 돌파했습니다.")
        elif poc_hold_above:
            add_score("caution", "poc_hold_above", 0, "최대 매물대(POC) 위에 안착하여 추세를 유지 중입니다.")
        elif poc_breakdown:
            add_score("sell_risk", "poc_breakdown", 1, "최대 매물대(POC) 하단 아래로 무너져 강한 저항이 예상됩니다.")
            
        vp_data["poc_breakout"] = poc_breakout
        vp_data["poc_hold_above"] = poc_hold_above
        vp_data["poc_breakdown"] = poc_breakdown

    # [7] 이격도 (Disparity)
    disparity = latest["disparity_20"]
    if pd.notna(disparity):
        if config.disparity_caution < disparity < config.disparity_overheated:
            add_score("caution", "disparity_caution", 0, f"이격도가 {disparity:.1f}로 주의 구간입니다.")
        elif disparity >= config.disparity_overheated:
            add_score("buy", "disparity_overheated_penalty", -1, "이격도 과열로 인한 매수 점수 페널티입니다.")
            add_score("sell_risk", "disparity_overheated", 1, f"이격도가 {disparity:.1f}로 단기 과열이 심각합니다.")

    # [8] 주봉 추세 확인 (Hard Filter)
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
        weekly_pass = False

    # 총합 계산 (기존 반환값 호환 유지)
    buy_score = 0
    sell_risk_score = 0
    reasons = []
    cautions = []
    sell_signals = []

    for item in score_breakdown:
        if item["type"] == "buy":
            buy_score += item["delta"]
            if item["delta"] > 0:
                reasons.append(item["reason"])
            elif item["delta"] < 0:
                cautions.append(item["reason"])
        elif item["type"] == "sell_risk":
            sell_risk_score += item["delta"]
            if item["delta"] > 0:
                sell_signals.append(item["reason"])
        elif item["type"] == "caution":
            cautions.append(item["reason"])
            
    # buy_score 음수 방지
    buy_score = max(0, buy_score)

    if sell_risk_score >= config.sell_risk_score:
        action = "매도 검토"
    elif not weekly_pass:
        action = "관망"
        buy_score = 0 # 강제 0점 처리
    elif buy_score >= buy_score_threshold and sell_risk_score <= 1:
        action = "매수 검토"
    else:
        action = "관망"

    # [9] ATR 손절가 계산
    stop_loss_price = max(0.01, latest["close"] - (2 * latest["atr_14"]))
    atr_stop_loss_percent = ((latest["close"] - stop_loss_price) / latest["close"]) * 100
    
    if atr_stop_loss_percent > config.max_stop_loss_percent:
        cautions.append(f"제시된 손절폭이 현재가 대비 {atr_stop_loss_percent:.1f}%로 매우 큽니다. 비중 조절에 유의하세요.")

    # [10] 권장 매수가 및 목표가 계산
    current_price = latest["close"]
    sma_20 = latest["sma_20"]
    poc_price = vp_data.get("poc_price")
    resistance_20 = latest["resistance_20"]
    
    # 1. 권장 매수가 (눌림목 대기 또는 현재가)
    candidates = []
    if pd.notna(sma_20) and current_price > sma_20:
        candidates.append(sma_20)
    if poc_price and poc_price < current_price:
        candidates.append(poc_price)
        
    if candidates:
        recommended_buy_price = max(candidates) # 가장 가까운 하단 지지선
    else:
        recommended_buy_price = current_price * 0.98 # 지지선이 없으면 2% 조정 시 매수
        
    if recommended_buy_price > current_price or recommended_buy_price < current_price * 0.8:
        recommended_buy_price = current_price
        
    # 2. 1차 목표 매도가 (전고점 또는 10% 수익)
    if pd.notna(resistance_20) and resistance_20 > current_price * 1.02:
        target_price = resistance_20
    else:
        target_price = current_price * 1.05 # 하락장 방어: 목표가 +5%로 하향 조정

    return {
        "action": action,
        "score": buy_score,
        "buy_score": buy_score,
        "sell_risk_score": sell_risk_score,
        "latest_date": latest["date"],
        "price": _round_or_none(latest["close"]),
        "recommended_buy_price": _round_or_none(recommended_buy_price),
        "target_price": _round_or_none(target_price),
        "candle_status": candle_status,
        "indicators": {
            "sma_20": _round_or_none(latest["sma_20"]),
            "sma_60": _round_or_none(latest["sma_60"]),
            "sma_20_slope_5d": _round_or_none(latest["sma_20_slope_5d"], 2),
            "volume_avg_20": _round_or_none(latest["volume_avg_20"]),
            "volume_ratio": _round_or_none(latest["volume_ratio"], 2),
            "rsi_14": _round_or_none(latest["rsi_14"]),
            "macd": _round_or_none(latest["macd"], 4),
            "macd_signal": _round_or_none(latest["macd_signal"], 4),
            "bb_upper": _round_or_none(latest["bb_upper"]),
            "bb_middle": _round_or_none(latest["bb_middle"]),
            "bb_lower": _round_or_none(latest["bb_lower"]),
            "atr_14": _round_or_none(latest["atr_14"]),
            "atr_percent": _round_or_none(latest["atr_percent"], 2),
            "support_20": _round_or_none(latest["support_20"]),
            "resistance_20": _round_or_none(latest["resistance_20"]),
            "resistance_55": _round_or_none(latest["resistance_55"]),
            "disparity_20": _round_or_none(latest["disparity_20"], 2),
            "volume_profile_poc": _round_or_none(vp_data.get("poc_price")),
            "volume_profile_low": _round_or_none(vp_data.get("poc_low")),
            "volume_profile_high": _round_or_none(vp_data.get("poc_high")),
        },
        "weekly_trend": weekly_trend,
        "volume_profile": vp_data,
        "stop_loss_price": _round_or_none(stop_loss_price),
        "atr_stop_loss": _round_or_none(stop_loss_price),
        "atr_stop_loss_percent": _round_or_none(atr_stop_loss_percent, 2),
        "score_breakdown": score_breakdown,
        "reasons": reasons,
        "cautions": cautions,
        "sell_signals": sell_signals,
    }
