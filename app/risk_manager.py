"""주문 안전장치와 감사 로그를 관리합니다.

파일 기반 저장소라 단일 프로세스 봇에 적합합니다. 여러 서버 인스턴스로
확장할 경우에는 이 상태를 Redis 또는 DB로 옮겨야 합니다.
"""
import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from app.config import PROJECT_ROOT, Settings


class OrderBlocked(Exception):
    """안전 규칙에 따라 주문이 차단됐습니다."""


class RiskManager:
    _lock = Lock()

    def __init__(self, settings: Settings):
        self.settings = settings
        self.data_dir = PROJECT_ROOT / "runtime"
        self.state_file = self.data_dir / "risk_state.json"
        self.audit_file = self.data_dir / "order_audit.jsonl"
        self.analysis_file = self.data_dir / "analysis_metrics.jsonl"

    @staticmethod
    def _today() -> str:
        return datetime.now().astimezone().date().isoformat()

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"date": self._today(), "buy_amounts": {}, "orders": {}, "equity_baseline": {}, "pending_orders": [], "kill_switch": False}
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if state.get("date") == self._today():
                return state
        except (OSError, json.JSONDecodeError):
            pass
        return {"date": self._today(), "buy_amounts": {}, "orders": {}, "equity_baseline": {}, "pending_orders": [], "kill_switch": False}

    def _write_state(self, state: Dict[str, Any]) -> None:
        self.data_dir.mkdir(exist_ok=True)
        self.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append(self, path: Path, event: Dict[str, Any]) -> None:
        self.data_dir.mkdir(exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False) + "\n")

    def update_equity(self, exchange: str, total_equity: float) -> float:
        """당일 최초 평가액 대비 손실률을 반환합니다."""
        with self._lock:
            state = self._read_state()
            baseline = state["equity_baseline"].setdefault(exchange, total_equity)
            self._write_state(state)
        return 0.0 if baseline <= 0 else (total_equity - baseline) / baseline * 100

    def assert_order_allowed(self, exchange: str, symbol: str, side: str, quantity: int,
                             reference_price: float, daily_loss_percent: Optional[float] = None) -> float:
        if side not in {"buy", "sell"} or quantity <= 0 or reference_price <= 0:
            raise OrderBlocked("주문 방향·수량·기준 가격이 유효하지 않습니다.")
        if not self.settings.kis_is_paper and not self.settings.live_trading_enabled:
            raise OrderBlocked("실전 주문이 차단되어 있습니다. KIS_LIVE_TRADING_ENABLED=true가 필요합니다.")
        amount = quantity * reference_price
        is_krx = exchange == "KRX"
        max_order = self.settings.max_order_amount_krw if is_krx else self.settings.max_order_amount_usd
        daily_limit = self.settings.daily_buy_limit_krw if is_krx else self.settings.daily_buy_limit_usd
        currency = "KRW" if is_krx else "USD"
        key = f"{exchange}:{symbol.upper()}:{side}"
        now = datetime.now().timestamp()
        with self._lock:
            state = self._read_state()
            if state.get("kill_switch"):
                raise OrderBlocked("킬 스위치가 켜져 있어 모든 신규 주문이 중지되었습니다.")
            # 매도는 손실 확대 방지를 위해 금액 한도/일일 손실 한도에서 제외하되 중복은 막습니다.
            last_order = state["orders"].get(key, 0)
            if now - last_order < 300:
                raise OrderBlocked("같은 종목·방향의 주문은 5분 안에 다시 낼 수 없습니다.")
            if side == "buy":
                if daily_loss_percent is not None and daily_loss_percent <= -self.settings.max_daily_loss_percent:
                    raise OrderBlocked(f"당일 손실률 {daily_loss_percent:.2f}%로 신규 매수가 중지되었습니다.")
                if amount > max_order:
                    raise OrderBlocked(f"1회 매수 한도({max_order:,.2f} {currency})를 초과했습니다.")
                spent = float(state["buy_amounts"].get(exchange, 0))
                if spent + amount > daily_limit:
                    raise OrderBlocked(f"일일 매수 한도({daily_limit:,.2f} {currency})를 초과했습니다.")
                buy_count = sum(1 for key in state["orders"] if key.startswith(f"{exchange}:") and key.endswith(":buy"))
                if buy_count >= self.settings.max_daily_buy_orders:
                    raise OrderBlocked(f"일일 신규 매수 횟수({self.settings.max_daily_buy_orders}회)를 초과했습니다.")
            return amount

    def assert_portfolio_capacity(self, holdings_count: int) -> None:
        if holdings_count >= self.settings.max_positions:
            raise OrderBlocked(f"최대 보유 종목 수({self.settings.max_positions}개)에 도달했습니다.")

    def record_order(self, exchange: str, symbol: str, side: str, quantity: int,
                     reference_price: float, result: Dict[str, Any]) -> None:
        amount = quantity * reference_price
        with self._lock:
            state = self._read_state()
            key = f"{exchange}:{symbol.upper()}:{side}"
            state["orders"][key] = datetime.now().timestamp()
            if side == "buy":
                state["buy_amounts"][exchange] = float(state["buy_amounts"].get(exchange, 0)) + amount
            self._write_state(state)
            self._append(self.audit_file, {"at": datetime.now().isoformat(), "exchange": exchange,
                "symbol": symbol.upper(), "side": side, "quantity": quantity,
                "reference_price": reference_price, "amount": amount, "result": result})
            order_no = result.get("output", {}).get("ODNO") or result.get("output", {}).get("odno")
            state.setdefault("pending_orders", []).append({"at": datetime.now().isoformat(), "exchange": exchange,
                "symbol": symbol.upper(), "side": side, "quantity": quantity, "order_no": order_no, "status": "submitted"})
            self._write_state(state)

    def set_kill_switch(self, enabled: bool) -> None:
        with self._lock:
            state = self._read_state()
            state["kill_switch"] = enabled
            self._write_state(state)
            self._append(self.audit_file, {"at": datetime.now().isoformat(), "event": "kill_switch", "enabled": enabled})

    def calculate_position_size(self, cash: float, entry_price: float, stop_price: float, exchange: str) -> Dict[str, Any]:
        """손절가까지의 손실이 가용 현금의 일정 비율을 넘지 않도록 수량을 계산합니다."""
        loss_per_share = max(0.0, entry_price - stop_price)
        if cash <= 0 or entry_price <= 0 or loss_per_share <= 0:
            return {"quantity": 0, "reason": "가격·손절가·가용 현금이 유효하지 않습니다."}
        max_risk = cash * (self.settings.risk_per_trade_percent / 100)
        risk_quantity = int(max_risk // loss_per_share)
        max_order = self.settings.max_order_amount_krw if exchange == "KRX" else self.settings.max_order_amount_usd
        quantity = min(risk_quantity, int(cash // entry_price), int(max_order // entry_price))
        return {"quantity": max(0, quantity), "risk_budget": round(max_risk, 2), "loss_per_share": round(loss_per_share, 4)}

    def assess_liquidity(self, order_book: Dict[str, Any]) -> Dict[str, Any]:
        """최우선 호가 스프레드가 너무 큰 종목의 신규 매수를 막습니다."""
        asks, bids = order_book.get("asks", []), order_book.get("bids", [])
        if not asks or not bids:
            return {"allowed": True, "spread_percent": None, "reason": "호가 데이터가 없어 유동성 필터를 건너뜁니다."}
        best_ask, best_bid = min(item["price"] for item in asks), max(item["price"] for item in bids)
        midpoint = (best_ask + best_bid) / 2
        spread_percent = (best_ask - best_bid) / midpoint * 100 if midpoint else 0.0
        allowed = spread_percent <= self.settings.max_spread_percent
        return {"allowed": allowed, "spread_percent": round(spread_percent, 3),
                "reason": "호가 스프레드가 허용 범위입니다." if allowed else f"호가 스프레드가 {spread_percent:.2f}%로 너무 큽니다."}

    def reconcile_orders(self, fills: list) -> Dict[str, Any]:
        """KIS 체결 조회 결과로 로컬 주문 상태를 갱신합니다."""
        with self._lock:
            state = self._read_state()
            updated = 0
            for order in state.get("pending_orders", []):
                for fill in fills:
                    order_no = str(fill.get("order_no") or "")
                    if order.get("order_no") and order_no == str(order["order_no"]):
                        order["status"] = fill.get("status", "pending")
                        order["filled_quantity"] = fill.get("filled_quantity", 0)
                        updated += 1
            self._write_state(state)
        return {"tracked_orders": len(state.get("pending_orders", [])), "updated_orders": updated}

    def record_analysis(self, exchange: str, symbol: str, analysis: Dict[str, Any]) -> None:
        self._append(self.analysis_file, {"at": datetime.now().isoformat(), "exchange": exchange,
            "symbol": symbol.upper(), "action": analysis.get("action"), "buy_score": analysis.get("buy_score"),
            "sell_risk_score": analysis.get("sell_risk_score"), "price": analysis.get("price"),
            "rsi": analysis.get("indicators", {}).get("rsi_14")})

    def status(self) -> Dict[str, Any]:
        state = self._read_state()
        return {"date": state["date"], "paper_trading": self.settings.kis_is_paper,
                "live_trading_enabled": self.settings.live_trading_enabled,
                "buy_amounts": state["buy_amounts"], "max_daily_loss_percent": self.settings.max_daily_loss_percent,
                "max_positions": self.settings.max_positions, "max_daily_buy_orders": self.settings.max_daily_buy_orders,
                "kill_switch": state.get("kill_switch", False), "pending_orders": len(state.get("pending_orders", []))}

    def analysis_summary(self) -> Dict[str, Any]:
        """저장된 신호의 분포를 제공해 전략 신호를 사후 점검합니다."""
        if not self.analysis_file.exists():
            return {"samples": 0, "actions": {}, "average_buy_score": None, "average_sell_risk_score": None}
        events = []
        try:
            for line in self.analysis_file.read_text(encoding="utf-8").splitlines():
                event = json.loads(line)
                if event.get("at", "")[:10] == self._today():
                    events.append(event)
        except (OSError, json.JSONDecodeError):
            return {"samples": 0, "actions": {}, "average_buy_score": None, "average_sell_risk_score": None}
        actions: Dict[str, int] = {}
        for event in events:
            action = event.get("action") or "unknown"
            actions[action] = actions.get(action, 0) + 1
        def average(key: str) -> Optional[float]:
            values = [float(event[key]) for event in events if event.get(key) is not None]
            return round(sum(values) / len(values), 2) if values else None
        return {"samples": len(events), "actions": actions,
                "average_buy_score": average("buy_score"),
                "average_sell_risk_score": average("sell_risk_score")}
