from app.config import get_settings
from app.kis_client import KisClient
import requests

settings = get_settings()
client = KisClient(settings)

url = f"{settings.kis_base_url}/uapi/overseas-price/v1/quotations/inquire-search"
params = {
    "AUTH": "",
    "KEYB": "",
    "EXCD": "NAS",
    "CO_YN_VOLUME": "1",
    "CO_ST_VOLUME": "1000",
    "CO_EN_VOLUME": "999999999999",
    "CO_YN_PRICECUR": "1",
    "CO_ST_PRICECUR": "5",
    "CO_EN_PRICECUR": "1000",
}
res = requests.get(url, headers=client._get_headers("HHDFS76410000"), params=params)
data = res.json()
print("Real rt_cd:", data.get("rt_cd"))
print("Real output2 len:", len(data.get("output2", [])) if data.get("output2") else 0)
