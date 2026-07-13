import requests
import json

url = "https://query2.finance.yahoo.com/v1/finance/search?q=나스닥"
headers = {"User-Agent": "Mozilla/5.0"}
res = requests.get(url, headers=headers)
print(json.dumps(res.json(), indent=2, ensure_ascii=False))
