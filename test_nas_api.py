from app.config import get_settings
from app.kis_client import KisClient
import requests

client = KisClient(get_settings())
url = f"{client.settings.kis_base_url}/uapi/overseas-price/v1/quotations/inquire-search"
params = {
    "AUTH": "",
    "KEYB": "",
    "EXCD": "NAS",
    "CO_YN_VOLUME": "1",
    "CO_ST_VOLUME": "1000000",
    "CO_EN_VOLUME": "999999999999",
    "CO_YN_PRICECUR": "1",
    "CO_ST_PRICECUR": "5",
    "CO_EN_PRICECUR": "1000",
}
res = requests.get(url, headers=client._get_headers("HHDFS76410000"), params=params)
data = res.json()
print("rt_cd:", data.get("rt_cd"))
print("msg1:", data.get("msg1"))
print("output len:", len(data.get("output", [])) if data.get("output") else 0)
print("output2 len:", len(data.get("output2", [])) if data.get("output2") else 0)
