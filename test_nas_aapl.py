from app.config import get_settings
from app.kis_client import KisClient

client = KisClient(get_settings())
try:
    prices = client.get_daily_prices("NAS", "AAPL")
    print("AAPL prices length:", len(prices))
except Exception as e:
    print("Error:", e)
