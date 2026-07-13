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

    @property
    def kis_base_url(self) -> str:
        if self.kis_is_paper:
            return "https://openapivts.koreainvestment.com:29443"
        return "https://openapi.koreainvestment.com:9443"


def get_settings() -> Settings:
    required_keys = [
        "KIS_APP_KEY",
        "KIS_APP_SECRET",
        "KIS_ACCOUNT_NO",
        "KIS_ACCOUNT_PRODUCT_CODE",
    ]

    missing_keys = [key for key in required_keys if not os.getenv(key)]

    if missing_keys:
        missing_text = ", ".join(missing_keys)
        raise RuntimeError(f"환경 변수 설정이 필요합니다: {missing_text}")

    return Settings(
        kis_app_key=os.environ["KIS_APP_KEY"],
        kis_app_secret=os.environ["KIS_APP_SECRET"],
        kis_account_no=os.environ["KIS_ACCOUNT_NO"],
        kis_account_product_code=os.environ["KIS_ACCOUNT_PRODUCT_CODE"],
        kis_is_paper=os.getenv("KIS_IS_PAPER", "true").lower() == "true",
    )