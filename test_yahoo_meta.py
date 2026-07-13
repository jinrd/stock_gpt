import requests
import urllib.parse
url = "https://query2.finance.yahoo.com/v1/finance/search?q=" + urllib.parse.quote("메타")
headers = {"User-Agent": "Mozilla/5.0"}
res = requests.get(url, headers=headers)
if res.ok:
    print(res.json().get('quotes', [])[0].get('symbol'))
