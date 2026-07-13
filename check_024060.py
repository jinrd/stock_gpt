from app.config import get_settings
from app.kis_client import KisClient
from app.analysis import analyze_daily_prices
import json

client = KisClient(get_settings())
daily_prices = client.get_krx_daily_prices(symbol="024060")
analysis = analyze_daily_prices(daily_prices)
print(json.dumps(analysis, indent=2, ensure_ascii=False))
