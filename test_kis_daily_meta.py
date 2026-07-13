import requests
from app.config import get_settings
from app.kis_client import KisClient
client = KisClient(get_settings())
url = f"{client.settings.kis_base_url}/uapi/overseas-price/v1/quotations/dailyprice"
params = {
    "AUTH": "",
    "EXCD": "NAS",
    "SYMB": "META",
    "GUBN": "0",
    "BYMD": "",
    "MODP": "1",
}
response = requests.get(
    url,
    headers=client._get_headers("HHDFS76240000"),
    params=params,
    timeout=10,
)
data = response.json()
print("Keys in data:", data.keys())
print("output1:", data.get("output1"))
