import requests
import json
from app.config import get_settings
from app.kis_client import KisClient
client = KisClient(get_settings())
url = f"{client.settings.kis_base_url}/uapi/overseas-price/v1/quotations/price-detail"
params = {
    "AUTH": "",
    "EXCD": "NAS",
    "SYMB": "META",
}
response = requests.get(
    url,
    headers=client._get_headers("HHDFS76200200"),
    params=params,
    timeout=10,
)
data = response.json()
print("Keys:", data.keys())
print("output:", json.dumps(data.get("output", {}), indent=2, ensure_ascii=False))
