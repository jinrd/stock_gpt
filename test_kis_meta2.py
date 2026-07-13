from app.config import get_settings
from app.kis_client import KisClient

client = KisClient(get_settings())
prices = client.get_daily_prices("NAS", "나스닥")
print(len(prices))
print(prices[0])
