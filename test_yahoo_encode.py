import requests
import urllib.parse
import json

symbol = "나스닥"
encoded = urllib.parse.quote(symbol)
url = f"https://query2.finance.yahoo.com/v1/finance/search?q={encoded}"
headers = {"User-Agent": "Mozilla/5.0"}
res = requests.get(url, headers=headers)
print("status:", res.status_code)
if res.ok:
    quotes = res.json().get('quotes', [])
    for q in quotes:
        print(q.get('symbol'), q.get('shortname'))
