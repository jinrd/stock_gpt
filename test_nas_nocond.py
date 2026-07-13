from app.config import get_settings
from app.kis_client import KisClient
import requests

client = KisClient(get_settings())
url = f"{client.settings.kis_base_url}/uapi/overseas-price/v1/quotations/inquire-search"
params = {
    "AUTH": "",
    "KEYB": "",
    "EXCD": "NAS",
    "CO_YN_VOLUME": "0",
    "CO_ST_VOLUME": "",
    "CO_EN_VOLUME": "",
    "CO_YN_PRICECUR": "0",
    "CO_ST_PRICECUR": "",
    "CO_EN_PRICECUR": "",
}
res = requests.get(url, headers=client._get_headers("HHDFS76410000"), params=params)
data = res.json()
print("rt_cd:", data.get("rt_cd"))
print("msg1:", data.get("msg1"))
print("output2 len:", len(data.get("output2", [])) if data.get("output2") else 0)
