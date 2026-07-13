from app.config import get_settings
from app.kis_client import KisClient

client = KisClient(get_settings())
try:
    meta = client.get_meta_info("NAS", "나스닥")
    print("Meta:", meta)
except Exception as e:
    print("Error:", e)
