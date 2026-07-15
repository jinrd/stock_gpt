import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    kis_app_key: str
    kis_app_secret: str
    kis_account_no: str
    kis_account_product_code: str
    kis_is_paper: bool
    live_trading_enabled: bool
    max_order_amount_krw: float
    max_order_amount_usd: float
    daily_buy_limit_krw: float
    daily_buy_limit_usd: float
    max_daily_loss_percent: float
    max_positions: int
    max_daily_buy_orders: int

    @property
    def kis_base_url(self) -> str:
        if self.kis_is_paper:
            return "https://openapivts.koreainvestment.com:29443"
        return "https://openapi.koreainvestment.com:9443"


def get_settings(force_mock: bool = False) -> Settings:
    is_paper = True if force_mock else os.getenv("KIS_IS_PAPER", "true").lower() == "true"
    prefix = "MOCK_" if is_paper and os.getenv("MOCK_APP_KEY") else "KIS_"

    required_keys = [
        f"{prefix}APP_KEY",
        f"{prefix}APP_SECRET",
        f"{prefix}ACCOUNT_NO",
        f"{prefix}ACCOUNT_PRODUCT_CODE",
    ]

    missing_keys = [key for key in required_keys if not os.getenv(key)]

    if missing_keys:
        missing_text = ", ".join(missing_keys)
        raise RuntimeError(f"환경 변수 설정이 필요합니다: {missing_text}")

    return Settings(
        kis_app_key=os.environ[f"{prefix}APP_KEY"],
        kis_app_secret=os.environ[f"{prefix}APP_SECRET"],
        kis_account_no=os.environ[f"{prefix}ACCOUNT_NO"],
        kis_account_product_code=os.environ[f"{prefix}ACCOUNT_PRODUCT_CODE"],
        kis_is_paper=is_paper,
        # 실전 주문은 KIS_IS_PAPER=false와 이 값이 모두 설정된 경우에만 허용됩니다.
        live_trading_enabled=os.getenv("KIS_LIVE_TRADING_ENABLED", "false").lower() == "true",
        max_order_amount_krw=float(os.getenv("MAX_ORDER_AMOUNT_KRW", "1000000")),
        max_order_amount_usd=float(os.getenv("MAX_ORDER_AMOUNT_USD", "1000")),
        daily_buy_limit_krw=float(os.getenv("DAILY_BUY_LIMIT_KRW", "3000000")),
        daily_buy_limit_usd=float(os.getenv("DAILY_BUY_LIMIT_USD", "3000")),
        max_daily_loss_percent=float(os.getenv("MAX_DAILY_LOSS_PERCENT", "3")),
        max_positions=int(os.getenv("MAX_POSITIONS", "10")),
        max_daily_buy_orders=int(os.getenv("MAX_DAILY_BUY_ORDERS", "3")),
    )
