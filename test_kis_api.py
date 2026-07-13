import requests
import json
from app.config import get_settings
from app.kis_client import KisClient
client = KisClient(get_settings())

# 1. KRX 주식현재가 호가 예상체결 (FHKST01010200)
url_krx_ob = f"{client.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
res_krx_ob = requests.get(url_krx_ob, headers=client._get_headers("FHKST01010200"), params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"})
print("KRX Order Book Keys:", res_krx_ob.json().keys() if res_krx_ob.ok else res_krx_ob.text)

# 2. KRX 주식현재가 시세 (FHKST01010100) -> for Fundamentals (PER, PBR, etc)
url_krx_fund = f"{client.settings.kis_base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
res_krx_fund = requests.get(url_krx_fund, headers=client._get_headers("FHKST01010100"), params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"})
print("KRX Funda Keys:", res_krx_fund.json().get('output').keys() if res_krx_fund.ok and res_krx_fund.json().get('output') else res_krx_fund.text)

# 3. Overseas 호가 (HHDFS76200100)
url_ov_ob = f"{client.settings.kis_base_url}/uapi/overseas-price/v1/quotations/inquire-asking-price"
res_ov_ob = requests.get(url_ov_ob, headers=client._get_headers("HHDFS76200100"), params={"AUTH": "", "EXCD": "NAS", "SYMB": "AAPL"})
print("Overseas OB Keys:", res_ov_ob.json().keys() if res_ov_ob.ok else res_ov_ob.text)

# 4. Overseas 현재가 상세 (HHDFS76200200) -> for Fundamentals
url_ov_fund = f"{client.settings.kis_base_url}/uapi/overseas-price/v1/quotations/price-detail"
res_ov_fund = requests.get(url_ov_fund, headers=client._get_headers("HHDFS76200200"), params={"AUTH": "", "EXCD": "NAS", "SYMB": "AAPL"})
print("Overseas Funda Keys:", res_ov_fund.json().get('output').keys() if res_ov_fund.ok and res_ov_fund.json().get('output') else res_ov_fund.text)
