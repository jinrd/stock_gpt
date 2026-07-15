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
            return {"date": self._today(), "buy_amounts": {}, "orders": {}, "equity_baseline": {}}
        try:
            state = json.loads(self.state_file.read_text(encoding="utf-8"))
            if state.get("date") == self._today():
                return state
        except (OSError, json.JSONDecodeError):
            pass
        return {"date": self._today(), "buy_amounts": {}, "orders": {}, "equity_baseline": {}}

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
                "max_positions": self.settings.max_positions, "max_daily_buy_orders": self.settings.max_daily_buy_orders}

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
