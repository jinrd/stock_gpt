"""일봉 종가 신호를 다음 거래일 시가에 체결한다고 가정한 단순 백테스트."""
from typing import Any, Dict, List

import pandas as pd

from app.analysis import analyze_daily_prices


def _number(value: Any) -> float:
    return float(str(value or 0).replace(",", ""))


def run_backtest(daily_prices: List[Dict[str, Any]], commission_bps: float = 10,
                 slippage_bps: float = 5) -> Dict[str, Any]:
    """수수료·슬리피지를 반영해 신호 전략과 단순 보유 수익률을 비교합니다.

    신호는 당일 종가 후 확정하고 주문은 다음 거래일 시가에 낸다고 가정합니다.
    과거 수익이 미래 신호에 섞이지 않도록 각 시점까지의 데이터만 분석합니다.
    """
    if len(daily_prices) < 65:
        raise ValueError("백테스트에는 최소 65일치 일봉이 필요합니다.")
    prices = sorted(daily_prices, key=lambda item: item.get("xymd") or "")
    fee_rate = (commission_bps + slippage_bps) / 10000
    cash, shares, entry_cost = 1.0, 0.0, 0.0
    equity_curve: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []
    pending = None
    win_count = 0

    for index in range(60, len(prices)):
        today = prices[index]
        open_price, close_price = _number(today.get("open")), _number(today.get("clos"))
        if open_price <= 0 or close_price <= 0:
            continue
        # 전일 종가에서 확정한 신호를 오늘 시가에 체결합니다.
        if pending == "buy" and shares == 0:
            execution_price = open_price * (1 + fee_rate)
            shares, cash, entry_cost = cash / execution_price, 0.0, execution_price
            trades.append({"date": today.get("xymd"), "side": "buy", "price": round(execution_price, 4)})
        elif pending == "sell" and shares > 0:
            execution_price = open_price * (1 - fee_rate)
            cash = shares * execution_price
            trade_return = (execution_price / entry_cost - 1) * 100
            win_count += trade_return > 0
            trades.append({"date": today.get("xymd"), "side": "sell", "price": round(execution_price, 4),
                           "return_percent": round(trade_return, 2)})
            shares, entry_cost = 0.0, 0.0
        equity = cash + shares * close_price
        equity_curve.append({"date": today.get("xymd"), "equity": round(equity, 6)})
        try:
            signal = analyze_daily_prices(prices[: index + 1])
            pending = "buy" if signal["action"] == "매수 검토" and shares == 0 else (
                "sell" if signal["action"] == "매도 검토" and shares > 0 else None
            )
        except ValueError:
            pending = None

    if shares > 0 and equity_curve:
        last_close = _number(prices[-1].get("clos"))
        execution_price = last_close * (1 - fee_rate)
        cash = shares * execution_price
        trade_return = (execution_price / entry_cost - 1) * 100
        win_count += trade_return > 0
        trades.append({"date": prices[-1].get("xymd"), "side": "sell", "price": round(execution_price, 4),
                       "return_percent": round(trade_return, 2), "forced_close": True})
        equity_curve[-1]["equity"] = round(cash, 6)

    equities = pd.Series([point["equity"] for point in equity_curve], dtype=float)
    peak = equities.cummax()
    max_drawdown = float(((equities / peak - 1) * 100).min()) if not equities.empty else 0.0
    completed_trades = [trade for trade in trades if trade["side"] == "sell"]
    strategy_return = (cash - 1) * 100
    benchmark_return = ((_number(prices[-1].get("clos")) / _number(prices[60].get("clos"))) - 1) * 100
    return {
        "assumptions": {"execution": "다음 거래일 시가", "commission_bps": commission_bps,
                        "slippage_bps": slippage_bps, "minimum_history_days": 60},
        "period": {"start": prices[60].get("xymd"), "end": prices[-1].get("xymd"), "days": len(equity_curve)},
        "performance": {"strategy_return_percent": round(strategy_return, 2),
                        "benchmark_return_percent": round(benchmark_return, 2),
                        "excess_return_percent": round(strategy_return - benchmark_return, 2),
                        "max_drawdown_percent": round(max_drawdown, 2),
                        "completed_trades": len(completed_trades),
                        "win_rate_percent": round(win_count / len(completed_trades) * 100, 2) if completed_trades else 0.0,
                        "average_trade_return_percent": round(sum(t["return_percent"] for t in completed_trades) / len(completed_trades), 2) if completed_trades else 0.0},
        "trades": trades[-100:],
        "equity_curve": equity_curve,
    }
